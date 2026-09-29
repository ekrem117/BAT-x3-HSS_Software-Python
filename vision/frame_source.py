"""Kare kaynagi.

Video aktarim zincirine kare saglar. Kamera acilabiliyorsa kamera
karesini, aksi halde sentetik kareyi dondurur. Cagiran taraf hangi
kaynagin kullanildigini bilmek zorunda degildir.

Gercek goruntu isleme entegre edildiginde, islenmis kare bu modulun
disindan verilir; get_frame() imzasi degismez.

Kare formati: NumPy dizisi, sekil (yukseklik, genislik, 3), tip uint8,
kanal sirasi BGR (OpenCV standardi).
"""

import logging

import cv2
import time 

from config import settings
from vision import synthetic

log = logging.getLogger("frame_source")

_counter = 0
_camera = None
_camera_failed = False


# ---------------------------------------------------------------------------
# Kamera
# ---------------------------------------------------------------------------

def open_camera(index=None):
    """Kamerayi acar ve cozunurluk/format ayarlarini uygular.

    MJPG formati tercih edilir: sikistirilmamis formatta USB bant
    genisligi 720p@30 icin yetersiz kalabilir ve kamera sessizce fps
    dusurur.

    Args:
        index: Kamera indeksi. None ise settings.CAMERA_INDEX kullanilir.

    Returns:
        cv2.VideoCapture nesnesi veya acilamadiysa None
    """
    if index is None:
        index = settings.CAMERA_INDEX

    cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)

    if not cap.isOpened():
        log.error("Kamera acilamadi (index=%d)", index)
        return None

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, settings.FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, settings.FRAME_HEIGHT)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FPS, settings.TARGET_FPS)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    if settings.LOCK_EXPOSURE:
        cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)
        cap.set(cv2.CAP_PROP_EXPOSURE, settings.EXPOSURE_VALUE)
        cap.set(cv2.CAP_PROP_GAIN, settings.CAMERA_GAIN)          # YENI
        log.info("Kazanc istendi=%s gercek=%s",
                settings.CAMERA_GAIN, cap.get(cv2.CAP_PROP_GAIN))

    _log_camera_settings(cap)
    return cap


def _log_camera_settings(cap):
    """Kameranin gercek ayarlarini loglar.

    set() cagrilari sessizce basarisiz olabilir; gercek degerleri
    dogrulamak gerekir.
    """
    actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    actual_fps = cap.get(cv2.CAP_PROP_FPS)

    fourcc_int = int(cap.get(cv2.CAP_PROP_FOURCC))
    fourcc = "".join(chr((fourcc_int >> 8 * i) & 0xFF) for i in range(4))

    log.info("Kamera acildi: %dx%d @ %.1f fps, format=%s",
             actual_w, actual_h, actual_fps, fourcc)

    if (actual_w, actual_h) != (settings.FRAME_WIDTH, settings.FRAME_HEIGHT):
        log.warning("Cozunurluk uygulanamadi: istenen=%dx%d gercek=%dx%d",
                    settings.FRAME_WIDTH, settings.FRAME_HEIGHT,
                    actual_w, actual_h)

    if fourcc != "MJPG":
        log.debug("MJPG formati uygulanamadi (format=%s), fps dusebilir",
                    fourcc)


def release_camera():
    """Kamerayi serbest birakir. Program kapanirken cagrilmalidir."""
    global _camera
    if _camera is not None:
        _camera.release()
        _camera = None
        log.info("Kamera serbest birakildi")


# ---------------------------------------------------------------------------
# Kare uretimi
# ---------------------------------------------------------------------------

def get_frame():
    """Yeni bir kare dondurur.

    Kamera acik ve okunabilir durumdaysa kamera karesini, aksi halde
    sentetik kareyi dondurur. Kamera bir kez acilamazsa tekrar denenmez;
    kalan oturum boyunca sentetik kare kullanilir.

    Returns:
        (frame, frame_id) — frame: BGR NumPy dizisi, frame_id: artan sayac
    """
    global _counter, _camera, _camera_failed
    _counter += 1

    frame = None

    if settings.USE_CAMERA and not _camera_failed:
        if _camera is None:
            _camera = open_camera()
            if _camera is None:
                _camera_failed = True
                log.warning("Kamera acilamadi, sentetik kareye gecildi")

        if _camera is not None:
            t0 = time.perf_counter()
            ok, captured = _camera.read()
            if ok:
                frame = captured
            else:
                log.warning("Kare okunamadi, kamera kapatiliyor")
                _camera.release()
                _camera = None
                _camera_failed = True

    if frame is None:
        frame = synthetic.make_frame(_counter,
                                     settings.FRAME_WIDTH,
                                     settings.FRAME_HEIGHT)

    if settings.DEBUG_OVERLAY:
        _draw_debug_overlay(frame, _counter)

    return frame, _counter


def _draw_debug_overlay(frame, counter):
    """Kare uzerine tani bilgisi cizer.

    Kare numarasi ve yanip sonen gosterge, akisin canli olup olmadigini
    gozle dogrulamayi saglar. settings.DEBUG_OVERLAY ile kontrol edilir;
    yarismada kapatilmalidir.
    """
    cv2.putText(frame, f"frame {counter}", (20, 50),
                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)

    if (counter // 15) % 2 == 0:
        cv2.circle(frame, (settings.FRAME_WIDTH - 40, 40), 15, (0, 0, 255), -1)