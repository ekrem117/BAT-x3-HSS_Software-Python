"""Kare kodlama.

Ham BGR kareleri ag uzerinden gonderilebilir formata cevirir.
"""

import logging

import cv2

from config import settings

log = logging.getLogger("encoder")


def encode_jpeg(frame, quality=None):
    """Kareyi JPEG baytlarina cevirir.

    Args:
        frame: BGR NumPy dizisi
        quality: JPEG kalitesi (0-100). None ise settings.JPEG_QUALITY.

    Returns:
        bytes — JPEG verisi. Kodlama basarisizsa None.
    """
    if quality is None:
        quality = settings.JPEG_QUALITY

    params = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
    ok, buffer = cv2.imencode(".jpg", frame, params)

    if not ok:
        log.error("JPEG kodlama basarisiz")
        return None

    return buffer.tobytes()


def encode_jpeg_bounded(frame, quality=None):
    """Kareyi boyut sinirini asmayacak sekilde JPEG'e cevirir.

    Sinir asilirsa kalite kademeli dusurulur. UDP datagram siniri
    (65507 bayt) icin gereklidir; MAX_JPEG_BYTES guvenlik payi birakir.

    TCP tabanli tuketiciler (MJPEG) bu fonksiyona ihtiyac duymaz;
    encode_jpeg yeterlidir.

    Args:
        frame: BGR NumPy dizisi
        quality: Baslangic JPEG kalitesi. None ise settings.JPEG_QUALITY.

    Returns:
        (bytes, quality) — kullanilan son kalite ile birlikte.
        Kodlama basarisizsa (None, 0).
    """
    if quality is None:
        quality = settings.JPEG_QUALITY

    q = quality
    jpg = None

    while q >= settings.MIN_JPEG_QUALITY:
        jpg = encode_jpeg(frame, q)

        if jpg is None:
            return None, 0

        if len(jpg) <= settings.MAX_JPEG_BYTES:
            return jpg, q

        q -= settings.JPEG_QUALITY_STEP

    log.warning("Kare %d bayta sigdirilamadi, kalite=%d boyut=%d",
                settings.MAX_JPEG_BYTES,
                q + settings.JPEG_QUALITY_STEP,
                len(jpg))
    return jpg, q + settings.JPEG_QUALITY_STEP

def resize_for_stream(frame, width=None, height=None):
    """Kareyi yayin cozunurluguna kucultur.

    Yakalama cozunurlugu model dogrulugu icin yuksek tutulabilir;
    yayin icin UDP datagram sinirina sigacak boyuta indirilir.

    Args:
        frame: BGR NumPy dizisi
        width: Hedef genislik. None ise settings.STREAM_WIDTH.
        height: Hedef yukseklik. None ise settings.STREAM_HEIGHT.

    Returns:
        BGR NumPy dizisi — gerekli degilse ayni nesne
    """
    if width is None:
        width = settings.STREAM_WIDTH
    if height is None:
        height = settings.STREAM_HEIGHT

    if frame.shape[1] <= width and frame.shape[0] <= height:
        return frame

    return cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)