"""Mesafe kestirimi.

Hedefin bilinen gercek boyutu ile goruntudeki piksel boyutunu
karsilastirarak mesafeyi hesaplar:

    mesafe = f_px * gercek_boyut / piksel_boyut

f_px degeri kameranin goruş alanindan turetilir. Bu yaklasim %5-15
hata payi tasir; lens toleransi ve distorsiyon hesaba katilmaz.
Ampirik duzeltme carpani (RANGE_CALIBRATION_FACTOR) bu hatayi
azaltir.

Yonelim uyarisi: ucak ve helikopter maketleri onden ve yandan
bakildiginda farkli genislikte gorunur; bu iki kat hataya yol
acabilir. Balonlar kuredir ve her acidan ayni capta gorunur, bu
nedenle mesafe kestiriminde guvenilir referanstir.

Menzil kusagi (yakin/orta/uzak) sinifi, ham mesafeden daha
dayaniklidir: yarisma mesafeleri 5/10/15 m olarak ayrik oldugundan
kusaklar arasinda genis bosluk vardir.
"""

import logging
import math

from config import settings

log = logging.getLogger("ranging")

BAND_NEAR = 0
BAND_MID = 1
BAND_FAR = 2
BAND_OUT_OF_RANGE = 3

BAND_NAMES = {
    BAND_NEAR: "YAKIN",
    BAND_MID: "ORTA",
    BAND_FAR: "UZAK",
    BAND_OUT_OF_RANGE: "MENZIL_DISI",
}

_focal_px = None


def focal_length_px(width=None, height=None):
    """Piksel cinsinden odak uzakligini hesaplar.

    FOV capraz olarak verilmisse once yatay FOV'a cevrilir.

    Args:
        width: Kare genisligi. None ise settings.FRAME_WIDTH.
        height: Kare yuksekligi. None ise settings.FRAME_HEIGHT.

    Returns:
        float — odak uzakligi (piksel)
    """
    global _focal_px

    if width is None:
        width = settings.FRAME_WIDTH
    if height is None:
        height = settings.FRAME_HEIGHT

    if _focal_px is not None:
        return _focal_px

    fov_rad = math.radians(settings.CAMERA_FOV_DEG)

    if settings.CAMERA_FOV_IS_DIAGONAL:
        diagonal_px = math.hypot(width, height)
        _focal_px = (diagonal_px / 2.0) / math.tan(fov_rad / 2.0)
    else:
        _focal_px = (width / 2.0) / math.tan(fov_rad / 2.0)

    log.info("Odak uzakligi: %.1f px (FOV=%.0f deg, %s, %dx%d)",
             _focal_px, settings.CAMERA_FOV_DEG,
             "capraz" if settings.CAMERA_FOV_IS_DIAGONAL else "yatay",
             width, height)

    return _focal_px


def estimate(detection):
    """Bir tespitin mesafesini kestirir.

    Kutunun buyuk kenari referans alinir; bu, yonelim degisimlerine
    kismen dayaniklidir.

    Args:
        detection: Tespit sozlugu — cls, w, h alanlari kullanilir

    Returns:
        (mesafe_m, band, guvenilir) — kestirilemezse (None, BAND_OUT_OF_RANGE, False)
    """
    cls = detection.get("cls")
    real_size = settings.TARGET_REAL_SIZE.get(cls)

    if real_size is None:
        return None, BAND_OUT_OF_RANGE, False

    pixel_size = max(detection.get("w", 0), detection.get("h", 0))

    if pixel_size <= 0:
        return None, BAND_OUT_OF_RANGE, False

    f_px = focal_length_px()
    distance = (f_px * real_size / pixel_size) * settings.RANGE_CALIBRATION_FACTOR

    reliable = cls in settings.RANGE_RELIABLE_CLASSES

    if distance < settings.RANGE_MIN_M or distance > settings.RANGE_MAX_M:
        return round(distance, 2), BAND_OUT_OF_RANGE, False

    return round(distance, 2), classify_band(distance), reliable


def classify_band(distance):
    """Mesafeyi menzil kusagina cevirir.

    Args:
        distance: Mesafe (metre)

    Returns:
        int — BAND_NEAR, BAND_MID, BAND_FAR veya BAND_OUT_OF_RANGE
    """
    near_limit, mid_limit, far_limit = settings.RANGE_BAND_LIMITS

    if distance < near_limit:
        return BAND_NEAR
    if distance < mid_limit:
        return BAND_MID
    if distance < far_limit:
        return BAND_FAR
    return BAND_OUT_OF_RANGE


def annotate(detections):
    """Tespit listesine mesafe alanlarini ekler.

    Girdi listesi yerinde degistirilir.

    Eklenen alanlar:
        dist        Kestirilen mesafe (metre) veya None
        band        Menzil kusagi kodu
        band_name   Kusak adi (gosterim icin)
        dist_ok     Kestirimin guvenilir olup olmadigi

    Args:
        detections: Tespit sozlukleri listesi

    Returns:
        list[dict] — ayni liste
    """
    for det in detections:
        distance, band, reliable = estimate(det)

        det["dist"] = distance
        det["band"] = band
        det["band_name"] = BAND_NAMES.get(band, "?")
        det["dist_ok"] = reliable

    return detections


def reset():
    """Onbellege alinmis odak uzakligini temizler.

    Cozunurluk veya FOV ayari degistiginde cagrilmalidir.
    """
    global _focal_px
    _focal_px = None