"""Arayuz taklidi — oyun kolu ile manuel ve otonom kontrol.

manual_wasd_v2.py ile ayni UDP paketlerini gonderir; tek fark girdi
kaynagidir. Sistem tarafinda hicbir degisiklik gerektirmez, cunku alt
katmanlar girdinin klavyeden mi koldan mi geldigini bilmez.

Analog eksenler oransal olarak gonderilir (motion.analog.pan/tilt);
aci hesabi ve yumusatma SystemManager tarafinda yapilir.

AUTO modunda analog eksenler GONDERILMEZ. param_bridge o modda
motion.auto.* degerlerini okur; kol girdisi gonderilirse iki yazici
ayni hedefe yazmaya calisir. Tek yazici ilkesi korunur.

main.py AYRI bir terminalde calisir durumda olmalidir.

Gereksinim:
    pip install pygame

Kullanim:
    py -m tools.manual_gamepad
"""

import json
import os
import socket
import time

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

import pygame

from config import settings

# ---------------------------------------------------------------------------
# Sistem modu kodlari
# ---------------------------------------------------------------------------
# core/enums.py ile birebir eslesmelidir. Sabit isim kullanilir cunku
# ciplak sayilar (0..4) kodun her yerine dagildiginda mod sirasi
# degistiginde sessizce yanlis mod secilir.

MODE_IDLE = 0
MODE_MANUAL = 1
MODE_AUTO = 2
MODE_LOOP_DEMO = 3
MODE_ESTOP = 4

# Calisma modlari arasinda DOGRUDAN gecis yasaktir; once IDLE'a donulur.
# Iki paket arasinda bekleme gerekir: param_bridge modu 50 Hz'de tarar
# ve ayni tarama turunda gelen iki mod degisikliginden ilki kaybolur.
# 0.1 s, 50 Hz tarama periyodunun (20 ms) bes katidir; UDP jitter'ina
# ve paket kaybina pay birakir.
MODE_TRANSITION_DELAY_S = 0.1

# ---------------------------------------------------------------------------
# Kol yapilandirmasi
# ---------------------------------------------------------------------------
# Bu degerler gamepad_probe.py ciktisina gore ayarlanir. Asagidakiler
# yaygin PlayStation benzeri kollar icin tipik degerlerdir.

AXIS_X = 0          # Sol analog yatay
AXIS_Y = 1          # Sol analog dikey

# Cogu kolda dikey eksende yukari NEGATIF deger uretir. Kolun tersse
# bunu False yap.
INVERT_Y = True

AXIS_PRECISION = None
BUTTON_PRECISION = 7  # R2
PRECISION_DEBOUNCE = 3

PRECISION_THRESHOLD = -0.5

BUTTON_FIRE = 5       # R1
BUTTON_ARM = 4        # L1
BUTTON_MANUAL = 9     # Start
BUTTON_IDLE = 8       # Select
BUTTON_ESTOP = 1      # Daire / B

# YENI: otonom takip ve acil durdurdan toparlanma.
# Ates butonundan (5) ve acil durdurdan (1) uzak secildi; kazara
# basma riskini azaltir.
BUTTON_AUTO = 3       # Ucgen / Y — otonom takip
BUTTON_RECOVER = 2    # Kare / X  — ESTOP'tan MANUAL'e donus

# Olu bolge. Ucuz kollarda merkez tam sifirda durmaz; bu esigin altindaki
# sapmalar yok sayilir. Taret kendiliginden suruklenirse degeri yukselt.
DEADZONE = 0.08

# AUTO modundayken kol bu esigin uzerinde oynatilirsa operator devralmak
# istiyor demektir; sistem guvenli tarafa (IDLE) cekilir. Esik olu
# bolgeden belirgin buyuk secildi ki merkez gurultusu modu dusurmesin.
AUTO_TAKEOVER_THRESHOLD = 0.5

FIRE_MIN_INTERVAL_S = 1.0

LOOP_HZ = 100.0

STATUS_KEYS = ("system.mode", "system.link", "weapon.armed", "weapon.ammo")

MOTION_PARAMS = (
    "motion.manual.up",
    "motion.manual.down",
    "motion.manual.left",
    "motion.manual.right",
)

ANALOG_PARAMS = ("motion.analog.pan", "motion.analog.tilt")


def _scale(value):
    """Olu bolgeyi cikarip degeri 0..1 araligina yeniden olcekler.

    Args:
        value: Ham eksen degeri

    Returns:
        float — olceklenmis deger, isaret korunur
    """
    magnitude = abs(value)
    if magnitude < DEADZONE:
        return 0.0

    scaled = (magnitude - DEADZONE) / (1.0 - DEADZONE)
    return scaled if value >= 0 else -scaled


class GamepadController:
    """Kol girdisini UDP komut paketlerine ceviren test istemcisi."""

    def __init__(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setblocking(False)
        self._addr = (settings.COMMAND_UDP_HOST, settings.COMMAND_UDP_PORT)
        self._msg_id = 0

        self._sent = {}          # parametre -> son gonderilen deger
        self._prev_buttons = {}  # buton -> onceki durum (kenar algilama)
        self._armed = 0
        self._pad = None
        self._last_fire_ts = 0.0

        self._precision_candidate = False
        self._precision_stable = 0

        # Bu aracin gonderdigi son mod. Sistemin GERCEK modu degildir;
        # yalnizca analog gonderimini kapatmak icin kullanilir. Gercek
        # modu ogrenmek icin "p" (GET) benzeri sorgu gerekir.
        self._mode = MODE_IDLE

    # -----------------------------------------------------------------
    # Gonderim
    # -----------------------------------------------------------------

    def _send(self, packet):
        """Paketi JSON olarak gonderir."""
        self._msg_id += 1
        packet["messageID"] = self._msg_id
        self._sock.sendto(json.dumps(packet).encode(), self._addr)

    def _set(self, key, value):
        """Tek parametre SET eder."""
        self._send({"Method": "SET", key: value})

    def _set_if_changed(self, key, value):
        """Deger degistiyse SET eder.

        Her turda gondermek agi gereksiz doldurur; yon durumu zaten
        sistem tarafinda korunur.
        """
        if self._sent.get(key) != value:
            self._sent[key] = value
            self._set(key, value)

    def _drain(self):
        """Gelen yanitlari okur; yalnizca hata ve GET yanitlarini yazar."""
        while True:
            try:
                data, _ = self._sock.recvfrom(settings.UDP_BUFFER_SIZE)
            except (BlockingIOError, OSError):
                return
            text = data.decode(errors="replace")
            if "ERR" in text or "GETRSP" in text:
                print("  <-", text)

    # -----------------------------------------------------------------
    # Mod gecisleri
    # -----------------------------------------------------------------

    def _zero_analog(self):
        """Analog eksenleri sifirlar ve onbellegi temizler.

        Mod degisiminde cagrilir. Onbellek temizlenmezse _set_analog
        "deger degismedi" diye dusunup sifiri gondermez ve taret eski
        girdiyle surunmeye devam eder.
        """
        for param in ANALOG_PARAMS:
            self._sent[param] = None
            self._set(param, 0.0)

    def _enter_mode(self, mode, label):
        """Dogrudan mod degisimi (IDLE ve MANUAL icin gecerli)."""
        self._zero_analog()
        self._set("system.mode", mode)
        self._mode = mode
        print(f"  -> {label}")

    def _enter_via_idle(self, mode, label):
        """IDLE uzerinden mod degisimi.

        Calisma modlari (MANUAL/AUTO/LOOP_DEMO) arasinda dogrudan gecis
        SystemManager tarafindan reddedilir. Gerekce: operator manuel
        nisan alirken sistemin aniden kendi hedefine donmesi tehlikelidir.
        """
        self._zero_analog()
        self._set("system.mode", MODE_IDLE)
        time.sleep(MODE_TRANSITION_DELAY_S)
        self._set("system.mode", mode)
        self._mode = mode
        print(f"  -> {label}")

    # -----------------------------------------------------------------
    # Girdi okuma
    # -----------------------------------------------------------------

    def _read_axes(self):
        """Analog eksenleri okuyup oransal girdi olarak gonderir.

        Olu bolge cikarildiktan sonra deger 0..1 araligina yeniden
        olceklenir; boylece esigin hemen ustunde ani sicrama olmaz ve
        kol yavas cekildiginde taret gercekten yavas hareket eder.

        AUTO modunda gonderim yapilmaz; bkz. modul aciklamasi.
        """
        x = self._pad.get_axis(AXIS_X)
        y = self._pad.get_axis(AXIS_Y)

        if INVERT_Y:
            y = -y

        if self._mode == MODE_AUTO:
            # Kol belirgin sekilde oynatildiysa operator devralmak
            # istiyordur. Otonom takibi zorla surdurmek yerine guvenli
            # tarafa cekilir; operator MANUAL'e kendisi gecer.
            if max(abs(x), abs(y)) > AUTO_TAKEOVER_THRESHOLD:
                self._enter_mode(MODE_IDLE, "IDLE (kol mudahalesi)")
            return

        self._set_analog("motion.analog.pan", _scale(x))
        self._set_analog("motion.analog.tilt", _scale(y))
        self._read_precision()

    def _read_precision(self):
        """Hassas mod tetigini okur ve degistiyse gonderir.

        Ucuz kollarda buton durumu titreyebilir. Ard arda birkac tur
        ayni deger okunmadan mod degistirilmez; bu, tek turluk
        gurultuyu filtreler.
        """
        active = False

        if AXIS_PRECISION is not None and AXIS_PRECISION < self._pad.get_numaxes():
            active = self._pad.get_axis(AXIS_PRECISION) > PRECISION_THRESHOLD
        elif BUTTON_PRECISION < self._pad.get_numbuttons():
            active = bool(self._pad.get_button(BUTTON_PRECISION))

        if active == self._precision_candidate:
            self._precision_stable += 1
        else:
            self._precision_candidate = active
            self._precision_stable = 1

        if self._precision_stable < PRECISION_DEBOUNCE:
            return

        value = 1 if active else 0
        if self._sent.get("motion.analog.precision") != value:
            self._sent["motion.analog.precision"] = value
            self._set("motion.analog.precision", value)
            print(f"  -> HASSAS MOD = {value}")

    def _set_analog(self, key, value):
        """Analog degeri yeterince degistiyse gonderir.

        Sifira DONUS her zaman gonderilir: kol birakildiginda taretin
        aninda durmasi, esik yuzunden bir paketin atlanmasindan daha
        onemlidir.

        Args:
            key: Parametre adi
            value: -1.0 ... 1.0 arasi deger
        """
        previous = self._sent.get(key)

        if previous is not None:
            durus = value == 0.0 and previous != 0.0
            if not durus and abs(previous - value) < 0.01:
                return

        self._sent[key] = value
        self._set(key, round(value, 3))

    def _pressed_now(self, button):
        """Butonun bu turda YENI basilip basilmadigini dondurur.

        Kenar algilama: buton basili tutuldugunda tek sefer True doner.
        Ates ve mod tuslarinin tekrarlanmamasi icin gereklidir.

        Args:
            button: Buton numarasi

        Returns:
            bool — yeni basildi mi
        """
        if button >= self._pad.get_numbuttons():
            return False

        current = bool(self._pad.get_button(button))
        previous = self._prev_buttons.get(button, False)
        self._prev_buttons[button] = current

        return current and not previous

    def _read_buttons(self):
        """Butonlari okur ve karsilik gelen komutlari gonderir."""
        if self._pressed_now(BUTTON_FIRE):
            now = time.monotonic()
            if now - self._last_fire_ts >= FIRE_MIN_INTERVAL_S:
                self._last_fire_ts = now
                self._set("weapon.fire", 1)
                print("  -> ATES")

        if self._pressed_now(BUTTON_ARM):
            self._armed = 0 if self._armed else 1
            self._set("weapon.armed", self._armed)
            print(f"  -> ARM = {self._armed}")

        if self._pressed_now(BUTTON_MANUAL):
            self._enter_via_idle(MODE_MANUAL, "MANUAL")

        if self._pressed_now(BUTTON_IDLE):
            self._enter_mode(MODE_IDLE, "IDLE")

        # YENI: otonom takip
        if self._pressed_now(BUTTON_AUTO):
            self._enter_via_idle(MODE_AUTO, "AUTO (otonom takip)")

        # YENI: acil durdurdan toparlanma.
        # Onceki surumde kol ESTOP'a girebiliyor ama cikamiyordu;
        # operator klavye aracina gecmek zorunda kaliyordu.
        if self._pressed_now(BUTTON_RECOVER):
            self._enter_via_idle(MODE_MANUAL, "TOPARLANDI (MANUAL)")

        if self._pressed_now(BUTTON_ESTOP):
            # ESTOP dogrudan gonderilir; IDLE uzerinden gecirilmez.
            # Acil durdurun her kosulda en kisa yoldan gitmesi gerekir.
            self._set("system.mode", MODE_ESTOP)
            self._mode = MODE_ESTOP
            print("  -> ACIL DURDUR  (toparlanmak icin Kare/X)")

    # -----------------------------------------------------------------
    # Ana dongu
    # -----------------------------------------------------------------

    def run(self):
        """Kolu baslatir ve gonderim dongusunu calistirir."""
        pygame.init()
        pygame.joystick.init()

        if pygame.joystick.get_count() == 0:
            print("Kol bulunamadi. USB baglantisini kontrol et.")
            return

        self._pad = pygame.joystick.Joystick(0)
        self._pad.init()

        print(f"Kol: {self._pad.get_name()}")
        print("Sol analog : hareket")
        print(f"Buton {BUTTON_FIRE}   : ATES")
        print(f"Buton {BUTTON_ARM}   : ARM ac/kapa")
        print(f"Buton {BUTTON_MANUAL}   : MANUAL")
        print(f"Buton {BUTTON_IDLE}   : IDLE")
        print(f"Buton {BUTTON_AUTO}   : AUTO (otonom takip)")
        print(f"Buton {BUTTON_RECOVER}   : ESTOP'tan toparlan")
        print(f"Buton {BUTTON_ESTOP}   : ACIL DURDUR")
        print("Ctrl+C ile cik.\n")

        period = 1.0 / LOOP_HZ

        try:
            while True:
                pygame.event.pump()

                self._read_axes()
                self._read_buttons()
                self._drain()

                time.sleep(period)

        except KeyboardInterrupt:
            pass
        finally:
            # Cikista once girdileri sifirla, sonra IDLE'a al.
            # Arac kapandiginda taretin AUTO modunda kendi basina
            # kalmasi kabul edilemez.
            for param in MOTION_PARAMS:
                self._set(param, 0)
            for param in ANALOG_PARAMS:
                self._set(param, 0.0)
            self._set("motion.analog.precision", 0)
            self._set("system.mode", MODE_IDLE)
            pygame.quit()
            print("\nCikildi, girdiler sifirlandi ve IDLE'a alindi.")


if __name__ == "__main__":
    GamepadController().run()