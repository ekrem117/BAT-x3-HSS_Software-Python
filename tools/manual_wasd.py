"""Arayuz taklidi v2 — pynput ile gercek tus durumu okur.

manual_wasd.py'den farki girdi yontemidir: msvcrt yalnizca karakter
akisi gorur ve tus BIRAKMA olayini goremez, bu yuzden Windows'un
otomatik tekrarina bakarak tahmin yurutur. Otomatik tekrar ayni anda
tek tus icin calistigindan capraz hareket (ornegin D+W) uretilemez.

pynput gercek KeyDown/KeyUp olaylarini verir; basili tuslar kumesi
fiziksel gercekligi yansitir. Gercek C# arayuzu de ayni sekilde
calisacaktir.
 

main.py AYRI bir terminalde calisir durumda olmalidir.

Gereksinim:
    pip install pynput

Tuslar:
    W A S D   yon (birlikte basilabilir - capraz hareket)
    J         ates
    K         ARM ac/kapa
    M         MANUAL moda gec
    I         IDLE moda gec
    L         sunum: yatay tarama + capraz (IDLE uzerinden)
    V         sunum: elips (IDLE uzerinden)
    1 / 2     elips zamanlamasi: pan'i daha gec / daha erken sur (0.02 s)
    N         AUTO moda gec (IDLE uzerinden)
    T         ACIL DURDUR
    Y         acil durdurdan cik (MANUAL'e doner)
    P         durum sorgula
    ESC       cikis

Kullanim:
    py -m tools.manual_wasd
"""

import json
import socket
import threading
import time

from pynput import keyboard

from config import settings

# Gonderim dongusu hizi. Yon degisiklikleri kenar tetikli gonderildigi
# icin bu hiz ag yukunu belirlemez, yalnizca tepki gecikmesini belirler.
LOOP_HZ = 50.0

# Elips zamanlamasi ayarinin tus basina adimi (s): param_bridge'in bir
# turu.
PAN_LEAD_STEP_S = 0.02

DIRECTION_KEYS = {
    "w": "motion.manual.up",
    "s": "motion.manual.down",
    "a": "motion.manual.left",
    "d": "motion.manual.right",
}

STATUS_KEYS = ("system.mode", "system.link", "weapon.armed", "weapon.ammo")


class GuiSimulator:
    """Klavye girdisini UDP komut paketlerine ceviren test istemcisi."""

    def __init__(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setblocking(False)
        self._addr = (settings.COMMAND_UDP_HOST, settings.COMMAND_UDP_PORT)
        self._msg_id = 0

        # Basili tuslar. pynput dinleyici thread'i yazar, ana dongu
        # okur; bu yuzden kilit gerekir.
        self._pressed = set()
        self._lock = threading.Lock()

        # En son gonderilen yon degerleri. Yalnizca degisiklikte paket
        # gonderilir; her turda gondermek agi gereksiz doldurur.
        self._sent = {}
        self._armed = 0
        # Elips zamanlamasi. Sunucudaki deger okunmaz; settings'teki
        # varsayilandan baslanir.
        self._pan_lead = float(settings.DEMO_ELLIPSE_PAN_LEAD_S)
        self._running = True

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

    def on_press(self, key):
        """Tusa basildiginda cagrilir."""
        if key == keyboard.Key.esc:
            self._running = False
            return False

        char = self._key_char(key)
        if char is None:
            return

        if char in DIRECTION_KEYS:
            with self._lock:
                self._pressed.add(char)
        else:
            self._handle_command(char)

    def on_release(self, key):
        """Tus birakildiginda cagrilir.

        Bu olay msvcrt surumunde YOKTU; capraz hareketi mumkun kilan
        tek fark budur.
        """
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
            # Acil durdur. Harf WASD ve komut tuslarindan uzak secildi;
            # kazara basma riskini azaltir.
            self._set("system.mode", 4)
            print("  -> ACIL DURDUR  (toparlanmak icin Y)")
        elif char == "y":
            # ESTOP'tan tek adimda kurtarma. Once IDLE (firmware mandali
            # acilir), sonra MANUAL. Iki paket arasinda kisa bir bekleme
            # gerekir: param_bridge modu 50 Hz'de tarar, ayni turda gelen
            # iki mod degisikliginden ilki kaybolur.
            self._set("system.mode", 0)
            time.sleep(0.1)
            self._set("system.mode", 1)
            print("  -> TOPARLANDI (MANUAL)")
        elif char == "p":
            self._send({"Method": "GET",
                        **{key: "?" for key in STATUS_KEYS}})
        elif char == "n":
            # Calisma modlari arasinda dogrudan gecis yasaktir; once
            # IDLE'a donulur. Iki paket arasinda kisa bir gecikme
            # birakilir cunku sunucu her paketi ayri isler.
            self._set("system.mode", 0)
            time.sleep(0.05)
            self._set("system.mode", 2)
            print("  -> AUTO (otonom takip)")
            

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
    # Ana dongu
    # -----------------------------------------------------------------

    def _sync_directions(self):
        """Basili tuslara gore yon parametrelerini gunceller.

        Dort yon her turda birlikte degerlendirilir; boylece D+W gibi
        kombinasyonlar tek bir bitmask'e donusur.
        """
        with self._lock:
            snapshot = set(self._pressed)

        for char, param in DIRECTION_KEYS.items():
            desired = 1 if char in snapshot else 0
            if self._sent.get(param) != desired:
                self._sent[param] = desired
                self._set(param, desired)

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
                self._sync_directions()
                self._drain()
                time.sleep(period)
        except KeyboardInterrupt:
            pass
        finally:
            # Cikista tum yonleri sifirla: taret basili tusla kalmasin.
            for param in DIRECTION_KEYS.values():
                self._set(param, 0)
            listener.stop()
            print("\nCikildi, tum yonler sifirlandi.")


if __name__ == "__main__":
    GuiSimulator().run()