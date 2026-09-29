"""Arduino ile seri port haberlesmesi.

Sistemdeki TEK seri port sahibi bu moduldur (Referans Belgesi ilke 4).

Sorumluluklar:
    - Portu ac/kapat, kopmada otomatik yeniden baglan
    - Gonderilen SON baytlari HEARTBEAT_INTERVAL_S'de bir tekrarla
      (Arduino'nun 500 ms'lik watchdog'unu besler, Referans Belgesi Bolum 7)
    - Baglanti durumunu (LinkState) disariya bildir

Bu modul KARAR VERMEZ. Hangi baytin ne zaman gonderilecegine
control/system_manager.py karar verir; burasi yalnizca tasima katmanidir.
"""

import logging
import threading
import time

import serial

from config import settings
from core.enums import LinkState
from hardware import serial_protocol

log = logging.getLogger("arduino_link")

# Firmware watchdog'unu (500 ms) rahat besleyecek kadar sik.
HEARTBEAT_INTERVAL_S = 0.15

# Baglanti kesildiginde yeniden deneme araligi.
RECONNECT_INTERVAL_S = 1.0


class ArduinoLink:
    """Arduino'ya tek noktadan seri erisim saglar.

    Thread-guvenlidir: send() cagrilari ve arka plan heartbeat thread'i
    ayni kilidi paylasir.
    """

    def __init__(self, port=None, baudrate=None):
        self._port = port or settings.SERIAL_PORT
        self._baudrate = baudrate or settings.BAUD_RATE

        self._serial = None
        self._lock = threading.Lock()
        self._last_payload = bytes([serial_protocol.CMD_STOP])
        self._link_state = LinkState.DISCONNECTED

        self._running = False
        self._thread = None

    # -----------------------------------------------------------------
    # Yasam dongusu
    # -----------------------------------------------------------------

    def start(self):
        """Arka plan heartbeat/yeniden-baglanma thread'ini baslatir."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._run, name="arduino_link", daemon=True,
        )
        self._thread.start()

    def stop(self):
        """Thread'i durdurur ve portu kapatir."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=settings.SHUTDOWN_TIMEOUT)
        with self._lock:
            self._close_locked()

    # -----------------------------------------------------------------
    # Disariya acik durum
    # -----------------------------------------------------------------

    def get_link_state(self):
        """Guncel baglanti durumunu dondurur (LinkState.*)."""
        with self._lock:
            return self._link_state

    # -----------------------------------------------------------------
    # Gonderim
    # -----------------------------------------------------------------

    def send(self, payload):
        """Bayt dizisini Arduino'ya yazar ve heartbeat icin saklar.

        Basarisiz yazma sessizce DISCONNECTED durumuna gecirir; hata
        yukariya firlatilmaz cunku cagiran taraf (SystemManager) her
        WASD karesinde try/except yonetmek zorunda kalmamalidir.

        Args:
            payload: hardware.protocol ile kodlanmis bytes

        Returns:
            bool — yazma basarili mi
        """
        with self._lock:
            self._last_payload = payload
            return self._write_locked(payload)

    # -----------------------------------------------------------------
    # Ic calisma
    # -----------------------------------------------------------------

    def _run(self):
        """Heartbeat + yeniden baglanma dongusu (arka plan thread)."""
        while self._running:
            with self._lock:
                connected = self._serial is not None

            if not connected:
                self._try_connect()
                time.sleep(RECONNECT_INTERVAL_S)
                continue

            with self._lock:
                payload = self._last_payload
                # Cok baytli cerceveler tekrarlanmaz: tekrar, devam eden
                # bir cercevenin ortasina denk gelirse senkron kayar ve
                # veri baytlari komut olarak yorumlanir (ornegin 0xFC
                # kazara ates tetikler). Cerceve akisi zaten 50 Hz
                # oldugu icin watchdog beslemesine gerek yoktur.
                if len(payload) == 1:
                    self._write_locked(payload)

            time.sleep(HEARTBEAT_INTERVAL_S)

    def _try_connect(self):
        """Portu acmayi dener; basarisizsa sessizce loglar ve devam eder."""
        try:
            ser = serial.Serial(
                self._port, self._baudrate, timeout=settings.SERIAL_TIMEOUT,
            )
        except serial.SerialException as exc:
            with self._lock:
                self._serial = None
                self._link_state = LinkState.DISCONNECTED
            log.warning("Arduino baglanamadi: %s", exc)
            return

        with self._lock:
            self._serial = ser
            self._link_state = LinkState.CONNECTED
        log.info("Arduino baglandi: %s @ %d", self._port, self._baudrate)

    def _write_locked(self, payload):
        """Kilit alinmisken gercek yazmayi yapar. Cagiran kilidi tutmalidir."""
        if self._serial is None:
            self._link_state = LinkState.DISCONNECTED
            return False

        try:
            self._serial.write(payload)
            self._link_state = LinkState.CONNECTED
            return True
        except serial.SerialException as exc:
            log.warning("Yazma hatasi, baglanti kapatiliyor: %s", exc)
            self._close_locked()
            return False

    def _close_locked(self):
        """Kilit alinmisken portu kapatir. Cagiran kilidi tutmalidir."""
        if self._serial is not None:
            try:
                self._serial.close()
            except serial.SerialException:
                pass
        self._serial = None
        self._link_state = LinkState.DISCONNECTED