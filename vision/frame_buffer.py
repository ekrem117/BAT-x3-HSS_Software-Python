"""Paylasilan son kare tamponu.

Tek bir yakalama thread'i surekli kare uretir ve son kareyi burada tutar.
Tum tuketiciler (UDP video, tespit yayini, HTTP sunucu) ayni kareyi okur;
kamera kac tuketici olursa olsun bir kez okunur.

Yavas bir tuketici kare atlar ancak uretimi yavaslatmaz.
"""

import logging
import threading
import time

from config import settings
from core import state
from vision import frame_source

log = logging.getLogger("frame_buffer")

_lock = threading.Lock()
_latest_frame = None
_latest_id = 0
_running = False
_thread = None


def _capture_loop():
    """Surekli kare uretip son kare degiskenini gunceller.

    Olculen kare hizini state.PARAM_VALUES uzerinden arayuze bildirir.
    """
    global _latest_frame, _latest_id

    log.info("Yakalama dongusu basladi (hedef %d fps)", settings.TARGET_FPS)

    fps_samples = 0
    fps_window_start = time.perf_counter()

    # DIKKAT: bu try/except olmadan, frame_source.get_frame() icinde
    # cikan HERHANGI bir istisna yakalama thread'ini sessizce oldurur —
    # _latest_frame/_latest_id son degerinde donar kalir, diger
    # tuketiciler (video_server, detection_buffer) bunu fark etmeden
    # eski/donmus kareyi islemeye devam edebilir. Ayni sinif hata
    # tracking_loop._loop()'ta yasanmisti.
    try:
        while _running:
            start = time.perf_counter()

            frame, frame_id = frame_source.get_frame()

            with _lock:
                _latest_frame = frame
                _latest_id = frame_id

            fps_samples += 1
            elapsed_window = start - fps_window_start
            if elapsed_window >= 1.0:
                state.PARAM_VALUES["system.fps"] = round(
                    fps_samples / elapsed_window, 1
                )
                fps_samples = 0
                fps_window_start = start

            if not settings.USE_CAMERA:
                elapsed = time.perf_counter() - start
                if elapsed < settings.FRAME_INTERVAL:
                    time.sleep(settings.FRAME_INTERVAL - elapsed)
    except Exception:
        log.exception("Yakalama dongusu coktu")

    log.info("Yakalama dongusu durdu")


def start():
    """Yakalama thread'ini baslatir."""
    global _running, _thread

    if _running:
        log.warning("Yakalama zaten calisiyor")
        return

    _running = True
    _thread = threading.Thread(target=_capture_loop, name="capture",
                               daemon=True)
    _thread.start()


def stop():
    """Yakalama thread'ini durdurur ve kamerayi serbest birakir."""
    global _running

    _running = False
    if _thread is not None:
        _thread.join(timeout=settings.SHUTDOWN_TIMEOUT)

    frame_source.release_camera()


def get_latest():
    """En son uretilen kareyi dondurur.

    Returns:
        (frame, frame_id) — henuz kare uretilmediyse (None, 0)
    """
    with _lock:
        return _latest_frame, _latest_id