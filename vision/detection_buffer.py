"""Tespit tamponu ve cikarim thread'i.

Tek bir cikarim thread'i frame_buffer'dan kare alir, nesne tespiti
yapar, renk analizi ve balon eslestirmesi uygular; sonucu burada tutar.

Bu ayrim gereklidir: model cikarimi 15-300 ms surebilir. Cikarim ag
dongusunun icinde yapilirsa gonderim hizi modele baglanir. Ayri thread
sayesinde video 30 fps akmaya devam eder; yalnizca kutular daha seyrek
guncellenir.

Tespit ureticisi settings.USE_YOLO ile secilir; model yuklenemezse
sentetik ureticiye dusulur.
"""

import logging
import threading
import time

from config import settings
from core import state
from core.enums import TargetClass
from vision import association, classifier, detector, frame_buffer, ranging, track_store
from vision import (association, classifier, color_detector, detector,
                    frame_buffer, ranging, track_store)

log = logging.getLogger("detection_buffer")

_lock = threading.Lock()
_latest_detections = []
_latest_frame_id = 0
_running = False
_thread = None


def _inference_loop():
    """Surekli cikarim yapip son tespit listesini gunceller."""
    global _latest_detections, _latest_frame_id

    log.info("Cikarim dongusu basladi (YOLO=%s)", settings.USE_YOLO)

    last_processed_id = 0

    # DIKKAT: bu try/except olmadan, dongu icindeki HERHANGI bir istisna
    # (model, track_store, ranging, association...) daemon thread'i
    # sessizce oldurur — vision.inference_ms sonsuza kadar son degerinde
    # takili kalir, hicbir hata log'a duşmez. Ayni sinif hata daha once
    # tracking_loop._loop()'ta yasanmisti.
    try:
        while _running:
            frame, frame_id = frame_buffer.get_latest()

            if frame is None or frame_id == last_processed_id:
                time.sleep(settings.INFERENCE_IDLE_SLEEP)
                continue

            last_processed_id = frame_id

            detections, inference_ms = _run_detection(frame)
            track_count = track_store.update(detections)
            published = len(track_store.predict_all())

            log.debug("model=%d iz=%d yayin=%d sure=%.0fms",
                      len(detections), track_count, published, inference_ms)

            # Izleri guncelle; kontrol dongusu ve yayin katmani artik
            # track_store uzerinden okur.
            track_store.update(detections)

            with _lock:
                _latest_detections = detections
                _latest_frame_id = frame_id

            state.PARAM_VALUES["vision.detection_count"] = len(detections)
            state.PARAM_VALUES["vision.inference_ms"] = round(inference_ms, 1)
    except Exception:
        log.exception("Cikarim dongusu coktu")

    log.info("Cikarim dongusu durdu")


def _run_detection(frame):
    """Tek bir kare uzerinde tam tespit hattini calistirir.

    Tespit kaynagi yapilandirmaya gore secilir:
        USE_COLOR_DETECTOR  renk tabanli (model yerine test icin)
        USE_YOLO            model tabanli
        digeri              sentetik ureticiler

    Args:
        frame: BGR NumPy dizisi

    Returns:
        (detections, inference_ms)
    """
    if settings.USE_COLOR_DETECTOR:
        start = time.perf_counter()
        detections = color_detector.get_detections(frame)
        inference_ms = (time.perf_counter() - start) * 1000

        ranging.annotate(detections)
        return detections, inference_ms

    if settings.USE_YOLO:
        detections, inference_ms = detector.detect(frame)
    else:
        from vision import synthetic_detector
        detections = synthetic_detector.get_detections()
        inference_ms = 0.0

    if settings.USE_COLOR_CLASSIFIER:
        _classify_models(frame, detections)
        association.associate(detections)

    ranging.annotate(detections)

    return detections, inference_ms


def _classify_models(frame, detections):
    """Maket tespitlerine renk analizi uygular.

    Balonlar atlanir; takimlarini association asamasinda bagli
    olduklari maketten devralirlar.

    Args:
        frame: BGR NumPy dizisi
        detections: Tespit sozlukleri listesi (yerinde degistirilir)
    """
    for det in detections:
        if det["cls"] == TargetClass.BALLOON:
            continue
        det["team"] = classifier.classify(frame, det)


def start():
    """Cikarim thread'ini baslatir."""
    global _running, _thread

    if _running:
        log.warning("Cikarim zaten calisiyor")
        return

    _running = True
    _thread = threading.Thread(target=_inference_loop, name="inference",
                               daemon=True)
    _thread.start()


def stop():
    """Cikarim thread'ini durdurur."""
    global _running

    _running = False
    if _thread is not None:
        _thread.join(timeout=settings.SHUTDOWN_TIMEOUT)

    track_store.clear()


def get_latest():
    """En son uretilen tespit listesini dondurur.

    Returns:
        (detections, frame_id) — henuz cikarim yapilmadiysa ([], 0)
    """
    with _lock:
        return list(_latest_detections), _latest_frame_id