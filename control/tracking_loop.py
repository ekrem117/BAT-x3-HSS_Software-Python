"""Takip ve angajman kontrol dongusu.

Cikarim ~10 Hz calisirken bu dongu 50 Hz'de doner. Kalman tahmini
sayesinde tespiti beklemez; hedefin o anki konumunu tahmin ederek
angajman durumunu tazeler.

Su asamada hedef secimi basittir: angajman yokken onaylanmis ilk iz
kilitlenir. Tehdit onceliklendirmesi (control/threat.py) hazir
oldugunda bu secim oraya devredilecektir.
"""

import logging
import threading
import time

from config import settings
from control import aiming, engagement, threat, turret_driver
from core.enums import EngagementState

log = logging.getLogger("tracking_loop")

_running = False
_thread = None


_last_fire_ts = 0.0


def _try_fire(aim_info, current, timestamp):
    """Nisan oturmussa ve izin varsa ates eder.

    Ates uc kosula baglidir: kilit LOCKED durumda, nisan olu bant
    icinde, silah yetkili. Ardisik atislar FIRE_COOLDOWN_S ile
    sinirlanir; firmware tetigi geri cekmeden ikinci komut gonderilirse
    mekanizma takilir.
    """
    global _last_fire_ts

    if aim_info is None or current is None:
        return

    if not aim_info["on_target"]:
        return

    if current["state"] != EngagementState.LOCKED:
        return

    if timestamp - _last_fire_ts < settings.FIRE_COOLDOWN_S:
        return

    manager = turret_driver.get_backend()
    if manager is None:
        return

    ok, reason = manager.fire()

    if not ok:
        log.debug("Otonom ates reddedildi: %s", reason)
        return

    _last_fire_ts = timestamp
    engagement.register_shot(timestamp)

    log.info("Otonom ates: track_id=%d hata=%.1f px atis=%d",
             current["track_id"], aim_info["distance"],
             current["shots_fired"] + 1)

def _loop():
    """Angajman durumunu duzenli araliklarla gunceller."""
    log.info("Takip dongusu basladi (%d Hz)", settings.TRACKING_LOOP_HZ)
    period = 1.0 / settings.TRACKING_LOOP_HZ

    try:
        while _running:
            start = time.perf_counter()
            now = time.time()

            engagement.update(now)

            current = engagement.current(now)
            if current and current["state"] in (EngagementState.DESTROYED,
                                                EngagementState.ABANDONED):
                engagement.release()
                current = None

            if settings.AUTO_LOCK and not engagement.is_active():
                _auto_select(now)
                current = engagement.current(now)

            if settings.ENABLE_TURRET_DRIVE:
                aim_info = aiming.solve(current)
                turret_driver.drive(aim_info, current)
                _try_fire(aim_info, current, now)

            elapsed = time.perf_counter() - start
            if elapsed < period:
                time.sleep(period - elapsed)
    except Exception:
        log.exception("Takip dongusu coktu")

    log.info("Takip dongusu durdu")


def _auto_select(timestamp):
    """Angajman yokken en yuksek tehditli hedefe kilitlenir.

    Hedef secimi control/threat.py'ye devredilmistir; yalnizca dusman
    hedefler degerlendirilir.

    Args:
        timestamp: Simdiki zaman (saniye)
    """
    target = threat.select_target(timestamp)

    if target is None:
        return

    engagement.lock(target.track_id, timestamp)


def start():
    """Kontrol thread'ini baslatir."""
    global _running, _thread

    if _running:
        log.warning("Takip dongusu zaten calisiyor")
        return

    _running = True
    _thread = threading.Thread(target=_loop, name="tracking", daemon=True)
    _thread.start()


def stop():
    """Kontrol thread'ini durdurur ve kilidi birakir."""
    global _running

    _running = False
    if _thread is not None:
        _thread.join(timeout=settings.SHUTDOWN_TIMEOUT)

    turret_driver.stop()
    engagement.release()