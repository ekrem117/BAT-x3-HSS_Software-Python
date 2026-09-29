"""Arayuz taklidi v3 — klavye ile analog (mutlak aci) kontrol.

manual_wasd_v2.py bitmask yon bitleri gonderiyordu; bu surum
manual_gamepad.py ile ayni analog yolu kullanir. Fark girdi kaynagidir.

Klavyede ara deger yoktur: tus ya basili ya degil. Bu yuzden girdi
dogrudan 1.0 yapilmaz, RAMPA ile yukseltilir. Kisa dokunus kucuk bir
hareket, basili tutmak tam hiz uretir; bu, kolun az/cok itilmesinin
klavye karsiligidir.

main.py AYRI bir terminalde calisir durumda olmalidir.

Gereksinim:
    pip install pynput

Tuslar:
    W A S D   yon (birlikte basilabilir - capraz hareket)
    SHIFT     basili tutuldugunda HASSAS MOD
    J         ates
    K         ARM ac/kapa
    M         MANUAL moda gec
    I         IDLE moda gec
    L         sunum: yatay tarama + capraz (IDLE uzerinden)
    V         sunum: elips (IDLE uzerinden)
    1 / 2     elips zamanlamasi: pan'i daha gec / daha erken sur (0.02 s)
    T         ACIL DURDUR
    Y         ESTOP'tan toparlan (IDLE -> MANUAL)
    P         durum sorgula
    ESC       cikis

Kullanim:
    py -m tools.manual_analog_wasd
"""

import json
import socket
import threading
import time

from pynput import keyboard

from config import settings

# Gonderim dongusu hizi. param_bridge ile ayni hizda calismak faz
# kaymasini onler.
LOOP_HZ = 100.0

# Elips zamanlamasi ayarinin tus basina adimi (s): param_bridge'in bir
# turu.
PAN_LEAD_STEP_S = 0.02


# Tusa basildigi anda girdinin aninda ulastigi deger. Rampa bu
# noktadan devam eder. Kisa dokunusun gorunur bir hareket uretmesini
# saglar; sifirdan baslarsa 50 ms'lik bir dokunus fark edilmez.
KICK_INPUT = 0.18


# Tus basiliyken girdinin 0'dan 1'e cikma suresi. Kisa dokunusun kucuk
# hareket uretmesini saglar; joystikte kolun yavas itilmesine karsilik
# gelir.
RAMP_UP_S = 1.2

# Tus birakildiginda girdinin sifira inme suresi. Yukselisten hizli
# olmali: birakinca taret hemen durmalidir.
RAMP_DOWN_S = 0.10

# Klavyede tam hiza cikmaya gerek yok: tarama icin bu yeterli, ince
# ayar zaten SHIFT ile yapiliyor.
MAX_INPUT = 0.6

# Bu esigin altindaki girdi sifir kabul edilir.
MIN_INPUT = 0.01

DIRECTION_KEYS = ("w", "a", "s", "d")

STATUS_KEYS = ("system.mode", "system.link", "weapon.armed", "weapon.ammo")

ANALOG_PARAMS = ("motion.analog.pan", "motion.analog.tilt")


class KeyboardAnalogController:
    """Klavye girdisini analog UDP paketlerine ceviren test istemcisi."""

    def __init__(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setblocking(False)
        self._addr = (settings.COMMAND_UDP_HOST, settings.COMMAND_UDP_PORT)
        self._msg_id = 0

        # Basili tuslar. pynput dinleyici thread'i yazar, ana dongu
        # okur; bu yuzden kilit gerekir.
        self._pressed = set()
        self._precision = False
        self._lock = threading.Lock()

        self._sent = {}
        self._armed = 0
        # Elips zamanlamasi. Sunucudaki deger okunmaz; settings'teki
        # varsayilandan baslanir.
        self._pan_lead = float(settings.DEMO_ELLIPSE_PAN_LEAD_S)
        self._running = True

        # Rampa durumu: her eksen icin -1.0 ... 1.0 arasi guncel girdi.
        self._pan_value = 0.0
        self._tilt_value = 0.0
        self._last_tick = None

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

    def _set_analog(self, key, value):
        """Analog degeri yeterince degistiyse gonderir.

        Sifira DONUS her zaman gonderilir: tus birakildiginda taretin
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
    # Klavye olaylari (pynput dinleyici thread'inde calisir)
    # -----------------------------------------------------------------

    def _key_char(self, key):
        """Tus nesnesinden kucuk harf karakteri cikarir.

        Returns:
            str veya None — ozel tuslar icin None
        """
        try:
            return key.char.lower()
        except AttributeError:
            return None

    def _is_shift(self, key):
        """Tusun SHIFT olup olmadigini bildirir."""
        return key in (keyboard.Key.shift, keyboard.Key.shift_l,
                       keyboard.Key.shift_r)

    def on_press(self, key):
        """Tusa basildiginda cagrilir."""
        if key == keyboard.Key.esc:
            self._running = False
            return False

        if self._is_shift(key):
            with self._lock:
                self._precision = True
            return

        char = self._key_char(key)
        if char is None:
            return

        if char in DIRECTION_KEYS:
            with self._lock:
                self._pressed.add(char)
        else:
            self._handle_command(char)

    def on_release(self, key):
        """Tus birakildiginda cagrilir."""
        if self._is_shift(key):
            with self._lock:
                self._precision = False
            return

        char = self._key_char(key)
        if char in DIRECTION_KEYS:
            with self._lock:
                self._pressed.discard(char)

    def _handle_command(self, char):
        """Yon disindaki tuslari isler."""
        if char == "j":
            self._set("weapon.fire", 1)
            print("  -> ATES")
        elif char == "k":
            self._armed = 0 if self._armed else 1
            self._set("weapon.armed", self._armed)
            print(f"  -> ARM = {self._armed}")
        elif char == "m":
            self._set("system.mode", 1)
            print("  -> MANUAL")
        elif char == "i":
            self._set("system.mode", 0)
            print("  -> IDLE")
        elif char == "l":
            self._start_demo(0, "SUNUM: yatay tarama + capraz")
        elif char == "v":
            self._start_demo(1, "SUNUM: elips")
        elif char in ("1", "2"):
            self._adjust_pan_lead(
                PAN_LEAD_STEP_S if char == "2" else -PAN_LEAD_STEP_S)
        elif char == "t":
            self._set("system.mode", 4)
            print("  -> ACIL DURDUR  (toparlanmak icin Y)")
        elif char == "y":
            # ESTOP'tan tek adimda kurtarma. Iki paket arasinda kisa
            # bekleme gerekir: param_bridge modu tarar, ayni turda gelen
            # iki mod degisikliginden ilki kaybolur.
            self._set("system.mode", 0)
            time.sleep(0.1)
            self._set("system.mode", 1)
            print("  -> TOPARLANDI (MANUAL)")
        elif char == "p":
            self._send({"Method": "GET",
                        **{key: "?" for key in STATUS_KEYS}})

    def _start_demo(self, pattern, label):
        """Sunum modunu verilen hareket duzeniyle baslatir.

        Once IDLE'a gecilir: calisma modlari arasinda dogrudan gecis
        yasaktir, ayrica sunum zaten calisiyorsa yeni duzen taretin
        bulundugu yerden temiz baslar. Duzen IDLE komutundan sonra
        yazilir.

        IDLE ile LOOP_DEMO arasinda bekleme gerekir: param_bridge modu
        50 Hz'de tarar, ayni turda gelen iki mod degisikliginden ilki
        kaybolur.

        Args:
            pattern: motion.demo.pattern degeri (0=tarama, 1=elips)
            label: Ekrana yazilacak aciklama
        """
        self._set("system.mode", 0)
        self._set("motion.demo.pattern", pattern)
        time.sleep(0.1)
        self._set("system.mode", 3)
        print(f"  -> {label}")

    def _adjust_pan_lead(self, step):
        """Elipste pan'in tilt'ten onde surulme suresini degistirir.

        Elips donerken canli ve yumusakca uygulanir. Bulunan deger kalici
        olmasi icin settings.DEMO_ELLIPSE_PAN_LEAD_S'e yazilmalidir.

        Args:
            step: Eklenecek sure (s), negatif olabilir
        """
        self._pan_lead = float(max(-1.0, min(1.0, round(self._pan_lead + step, 3))))
        self._set("motion.demo.pan_lead", self._pan_lead)
        print(f"  -> elips: pan {self._pan_lead:+.2f} s onde"
              "  (kalici: settings.DEMO_ELLIPSE_PAN_LEAD_S)")

    # -----------------------------------------------------------------
    # Rampa
    # -----------------------------------------------------------------

    def _target_for(self, negative_key, positive_key, snapshot):
        """Iki tusun durumundan hedef girdi degerini bulur.

        Zit tuslar birlikte basiliysa sifir dondurulur.

        Args:
            negative_key: Negatif yon tusu
            positive_key: Pozitif yon tusu
            snapshot: Basili tuslarin kopyasi

        Returns:
            float — -1.0, 0.0 veya 1.0
        """
        negative = negative_key in snapshot
        positive = positive_key in snapshot

        if negative == positive:
            return 0.0
        return 1.0 if positive else -1.0

    def _ramp(self, current, target, dt):
        """Guncel degeri hedefe dogru rampa ile yaklastirir.

        Yukselis ve inis farkli hizdadir: tus birakildiginda taret hemen
        durmali, basildiginda ise kademeli hizlanmalidir.

        Duran bir eksende tusa basildiginda deger once KICK_INPUT'a
        atlar. Sifirdan rampa baslarsa kisa dokunuslar gorunmeyecek
        kadar kucuk hareket uretir.

        Args:
            current: Guncel deger
            target: Hedef deger (-1, 0 veya 1)
            dt: Gecen sure

        Returns:
            float — yeni deger
        """
        if target == 0.0:
            step = dt / RAMP_DOWN_S
            if abs(current) <= step:
                return 0.0
            return current - step if current > 0 else current + step

        # Yon degistiyse once sifira inilir; boylece taret ters yone
        # aniden firlamaz.
        if current * target < 0:
            step = dt / RAMP_DOWN_S
            if abs(current) <= step:
                return 0.0
            return current - step if current > 0 else current + step

        # Duruyorken basildi: hemen kullanilabilir bir degere atla.
        if abs(current) < KICK_INPUT:
            return KICK_INPUT * target

        step = dt / RAMP_UP_S
        new_value = current + step * target

        return max(-MAX_INPUT, min(MAX_INPUT, new_value))

        
    # -----------------------------------------------------------------
    # Ana dongu
    # -----------------------------------------------------------------

    def _tick(self):
        """Bir tur rampa hesabi yapip paketleri gonderir."""
        now = time.monotonic()

        if self._last_tick is None:
            dt = 0.0
        else:
            dt = min(now - self._last_tick, 0.1)
        self._last_tick = now

        with self._lock:
            snapshot = set(self._pressed)
            precision = self._precision

        pan_target = self._target_for("a", "d", snapshot)
        tilt_target = self._target_for("s", "w", snapshot)

        self._pan_value = self._ramp(self._pan_value, pan_target, dt)
        self._tilt_value = self._ramp(self._tilt_value, tilt_target, dt)

        pan = self._pan_value if abs(self._pan_value) > MIN_INPUT else 0.0
        tilt = self._tilt_value if abs(self._tilt_value) > MIN_INPUT else 0.0

        self._set_analog("motion.analog.pan", pan)
        self._set_analog("motion.analog.tilt", tilt)

        value = 1 if precision else 0
        if self._sent.get("motion.analog.precision") != value:
            self._sent["motion.analog.precision"] = value
            self._set("motion.analog.precision", value)
            print(f"  -> HASSAS MOD = {value}")

    def run(self):
        """Dinleyiciyi baslatir ve gonderim dongusunu calistirir."""
        print(__doc__)

        listener = keyboard.Listener(
            on_press=self.on_press, on_release=self.on_release,
        )
        listener.start()

        period = 1.0 / LOOP_HZ

        try:
            while self._running:
                self._tick()
                self._drain()
                time.sleep(period)
        except KeyboardInterrupt:
            pass
        finally:
            # Cikista tum girdileri sifirla: taret basili tusla kalmasin.
            for param in ANALOG_PARAMS:
                self._set(param, 0.0)
            self._set("motion.analog.precision", 0)
            listener.stop()
            print("\nCikildi, tum girdiler sifirlandi.")


if __name__ == "__main__":
    KeyboardAnalogController().run()