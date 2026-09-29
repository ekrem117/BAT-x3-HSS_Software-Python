"""Parametre katalogu ile SystemManager arasindaki iki yonlu kopru.

Iki gorevi vardir:
    Asagi  PARAM_VALUES ve COMMAND_QUEUE okunur, SystemManager'a uygulanir
    Yukari SystemManager'in durumu RO parametrelere yazilir

Sunum modu koreografisi (control/loop_demo.py) da bu dongunun her
turunda ilerletilir; kendi thread'i yoktur.

Bu dosya control/ altindadir cunku core/'u okur ve control/'u cagirir,
ikisi de asagi yon. protocols/ altinda olsaydi ag katmani control/'u
import etmis olurdu; bu yatay bagimlilik olur ve mimariyi bozar.

Kural icermez: neyin izinli oldugunu SystemManager belirler, burasi
yalnizca tasir ve reddedilen istekleri loglar.
"""

import logging
import threading
import time
from queue import Empty

from config import settings
from control.loop_demo import LoopDemoController
from core import state

log = logging.getLogger("param_bridge")

# RO durum guncellemesi her N dongude bir yapilir. Kontrol dongusu 50 Hz,
# arayuze 10 Hz durum yeterli; her karede sozluk yazmanin anlami yok.
_STATUS_EVERY_N = 5
# AUTO modu kodu. core/enums.py'deki SystemMode metin tabanli oldugu
# icin katalogdaki sayisal kod burada tanimlanir.
_MODE_AUTO = 2

# Katalogdaki manuel yon anahtarlari -> SystemManager parametre adlari
_MOTION_KEYS = {
    "motion.manual.up": "up",
    "motion.manual.down": "down",
    "motion.manual.left": "left",
    "motion.manual.right": "right",
}

# Hareket girdisi kaynaklari. SystemManager'da bitmask ve mutlak aci
# bicimleri birbirini disladigi ve gecerli olan SON CAGRILAN girdi
# metoduna gore belirlendigi icin her turda yalnizca biri uygulanir.
_SRC_MANUAL = "manual"
_SRC_ANALOG = "analog"


class ParamBridge:
    """Katalog <-> SystemManager senkronizasyon dongusu."""

    def __init__(self, manager):
        self._manager = manager
        self._running = False
        self._thread = None
        self._period = 1.0 / settings.CONTROL_LOOP_HZ

        # Etkin hareket girdisi kaynagi. Klavye ile analog kol ayni anda
        # uygulanamaz; hangisinin gecerli oldugu burada tutulur.
        self._source = _SRC_MANUAL

        # Son uygulanan mod kodu. Arayuz her SET'te ayni degeri
        # gonderebilir; degisim olmadan set_mode cagirmak gereksiz log
        # uretir ve manuel girdileri sifirlar.
        self._last_mode_code = None
        self._last_armed = None

        # Sunum koreografisi. Bu dongude ilerletilir; boylece sistemde
        # tek bir zaman kaynagi kalir.
        self._demo = LoopDemoController()

    def start(self):
        """Kontrol dongusu thread'ini baslatir."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._run, name="param_bridge", daemon=True,
        )
        self._thread.start()
        log.info("ParamBridge basladi (%.0f Hz)", settings.CONTROL_LOOP_HZ)

    def stop(self):
        """Dongoyu durdurur."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=settings.SHUTDOWN_TIMEOUT)
        log.info("ParamBridge durdu")

    # -----------------------------------------------------------------
    # Ana dongu
    # -----------------------------------------------------------------

    def _run(self):
        """50 Hz sabit periyotlu kontrol dongusu."""
        counter = 0
        next_tick = time.monotonic()

        while self._running:
            try:
                self._drain_commands()
                self._apply_params()
                # Mod degisimi uygulandiktan SONRA: LOOP_DEMO'ya girilen
                # turda ilk hedef ayni turda gonderilir.
                self._demo.tick(
                    self._manager,
                    int(state.PARAM_VALUES.get("motion.demo.pattern", 0)),
                    float(state.PARAM_VALUES.get("motion.demo.pan_lead", 0.0)),
                )
                self._manager.update()
                self._publish_angles()

                counter += 1
                if counter >= _STATUS_EVERY_N:
                    counter = 0
                    self._publish_status()
            except Exception:
                # Dongu asla olmemeli: tek bir hata tum manuel kontrolu
                # sessizce durdurur. Loglayip devam ediyoruz.
                log.exception("Kontrol dongusunde hata")

            next_tick += self._period
            sleep_s = next_tick - time.monotonic()
            if sleep_s > 0:
                time.sleep(sleep_s)
            else:
                # Gecikme birikmesin: saati simdiye sifirla.
                next_tick = time.monotonic()

    # -----------------------------------------------------------------
    # Asagi yon: katalog -> SystemManager
    # -----------------------------------------------------------------



    def _drain_commands(self):
        """Komut kuyrugunu tuketir.

        Kuyruk her dongude BOSALTILIR. Tuketilmezse dolar ve yeni
        komutlar INTERNAL_ERROR ile reddedilir.
        """
        while True:
            try:
                command = state.COMMAND_QUEUE.get_nowait()
            except Empty:
                return

            self._handle_command(command)

    def _handle_command(self, command):
        """Tek bir tetikleyici komutu isler.

        Args:
            command: {"action": str, "value": Any, "ts": float}
        """
        action = command.get("action")

        if action == "weapon.fire":
            ok, reason = self._manager.fire()
        else:
            log.warning("Bilinmeyen komut: %s", action)
            return

        if not ok:
            log.info("Komut reddedildi (%s): %s", action, reason)

    def _apply_params(self):
        """RW parametreleri SystemManager'a uygular."""
        # --- Mod ---
        mode_code = state.PARAM_VALUES.get("system.mode")
        if mode_code != self._last_mode_code:
            ok, reason = self._manager.set_mode_code(mode_code)
            if ok:
                self._last_mode_code = mode_code
                # Mod degisimi SystemManager tarafinda tum girdileri
                # temizler; kaynak secimi de bitmask'e donmelidir.
                self._source = _SRC_MANUAL
            else:
                # Gecis reddedildi: katalogu gercek moda geri al ki
                # arayuz yanlis mod gosterip beklemesin.
                log.info("Mod degisimi reddedildi: %s", reason)
                status = self._manager.get_status()
                state.PARAM_VALUES["system.mode"] = status["system.mode"]
                self._last_mode_code = status["system.mode"]

        # --- ARM ---
        armed = state.PARAM_VALUES.get("weapon.armed")
        if armed != self._last_armed:
            ok, reason = self._manager.set_armed(bool(armed))
            if ok:
                self._last_armed = armed
            else:
                log.info("ARM degisimi reddedildi: %s", reason)
                state.PARAM_VALUES["weapon.armed"] = 0
                self._last_armed = 0

        # --- Hareket girdisi ---
        # SystemManager'da gecerli hareket bicimi SON CAGRILAN girdi
        # metoduna gore belirlenir. Bu yuzden her turda ikisini birden
        # cagirmak YASAKTIR: sonra cagrilan digerini kalicilastirir ve
        # o girdi yolu bir daha calismaz. Kaynak burada secilir, yalnizca
        # secilen metot cagrilir.
        #
        # Kaynak moda gore de degisir: AUTO modunda otonom katmanin
        # urettigi girdi, diger modlarda arayuzden gelen kol girdisi
        # kullanilir. Ikisi ayni hedefe yazamaz; tek yazici ilkesi.
        #
        # Mod, yukaridaki blokta reddedilmis olabilir; katalog o durumda
        # gercek moda geri alindigi icin yeniden okunur.
        mode_code = state.PARAM_VALUES.get("system.mode")

        keys = {
            arg: bool(state.PARAM_VALUES.get(key, 0))
            for key, arg in _MOTION_KEYS.items()
        }

        if mode_code == _MODE_AUTO:
            pan = float(state.PARAM_VALUES.get("motion.auto.pan", 0.0))
            tilt = float(state.PARAM_VALUES.get("motion.auto.tilt", 0.0))
            precision = False
            self._source = _SRC_ANALOG
        else:
            pan = float(state.PARAM_VALUES.get("motion.analog.pan", 0.0))
            tilt = float(state.PARAM_VALUES.get("motion.analog.tilt", 0.0))
            precision = bool(state.PARAM_VALUES.get("motion.analog.precision", 0))

            # Kaynak yalnizca ilgili girdi ETKINKEN degisir. Ikisi de
            # bostayken son kaynak korunur; boylece kol merkeze
            # dondugunde set_analog_input(0, 0) cagrilmaya devam eder.
            # Cagrilmazsa son sifirdan farkli deger hedefte kalir ve
            # taret kol birakilmis olmasina ragmen kaymaya devam eder.
            if any(keys.values()):
                self._source = _SRC_MANUAL
            elif pan or tilt:
                self._source = _SRC_ANALOG

        if self._source == _SRC_ANALOG:
            self._manager.set_analog_input(
                pan=pan, tilt=tilt, precision=precision)
        else:
            # Tus durumu surekli bir sinyaldir: degisim tespiti yapmadan
            # her turda gonderilir, boylece paket kaybina dayanikli olur.
            self._manager.set_manual_input(**keys)


    # -----------------------------------------------------------------
    # Yukari yon: SystemManager -> katalog
    # -----------------------------------------------------------------

    def _publish_status(self):
        """RO parametreleri gercek sistem durumuyla gunceller."""
        status = self._manager.get_status()
        state.PARAM_VALUES.update(status)

        # Yerel onbellegi de senkron tut: SystemManager kendi kararlariyla
        # mod dusurmus olabilir (ornegin ESTOP), arayuzden gelmemis olsa da.
        self._last_mode_code = status["system.mode"]
        self._last_armed = status["weapon.armed"]


    def _publish_angles(self):
        """Taret acilarini her turda yayinlar.

        Ego-motion telafisi bu degerleri kullanir. 10 Hz yetersizdir:
        100 ms icinde taret yuzlerce piksellik kaymaya yol acacak
        kadar donebilir.
        """
        status = self._manager.get_status()
        state.PARAM_VALUES["system.pan_angle"] = status["system.pan_angle"]
        state.PARAM_VALUES["system.tilt_angle"] = status["system.tilt_angle"]