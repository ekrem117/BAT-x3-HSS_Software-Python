"""Renk tabanli tespit ureticisi.

YOLO modeli yeterince guvenilir olmadiginda kontrol zincirini test
etmek icin kullanilir: kirmizi bir nesne (balon) HSV renk esikleriyle
bulunur ve tespit formatinda dondurulur.

Model tabanli tespitle ayni cikti formatini uretir; takip, angajman,
nisan ve taret surme katmanlari degismeden calisir. Boylece model
kalitesinden bagimsiz olarak kontrol dongusu ayarlanabilir.

Esikler core.state uzerinden calisma sirasinda degistirilebilir
(vision.enemy.* parametreleri).
"""

import logging

import cv2
import numpy as np

from config import settings
from core import state
from core.enums import TargetClass, Team

log = logging.getLogger("color_detector")

_next_id = 1


def get_detections(frame):
    """Karedeki kirmizi nesneleri tespit eder.

    Args:
        frame: BGR NumPy dizisi

    Returns:
        list[dict] — protokol formatinda tespitler
    """
    global _next_id

    if frame is None:
        return []

    mask = _build_mask(frame)
    contours = _find_contours(mask, frame.shape)

    detections = []

    for i, (x, y, w, h, area_ratio) in enumerate(contours):
        detections.append({
            "id": i + 1,
            "x": x,
            "y": y,
            "w": w,
            "h": h,
            "cls": TargetClass.BALLOON,
            "team": Team.ENEMY,
            "conf": round(min(0.99, 0.5 + area_ratio * 20), 2),
            "parent_id": None,
        })

    return detections


def _build_mask(frame):
    """Kirmizi renk maskesini uretir.

    Kirmizi HSV renk cemberinin basinda oldugu icin iki aralik
    birlestirilir. Gurultu, morfolojik acma/kapama ile temizlenir.

    Args:
        frame: BGR NumPy dizisi

    Returns:
        Ikili maske (uint8)
    """
    blurred = cv2.GaussianBlur(frame, (7, 7), 0)
    hsv = cv2.cvtColor(blurred, cv2.COLOR_BGR2HSV)

    v = state.PARAM_VALUES

    lower1 = np.array([v["vision.enemy.h_min"],
                       v["vision.enemy.s_min"],
                       v["vision.enemy.v_min"]], dtype=np.uint8)
    upper1 = np.array([v["vision.enemy.h_max"], 255, 255], dtype=np.uint8)

    lower2 = np.array([v["vision.enemy.h_min2"],
                       v["vision.enemy.s_min"],
                       v["vision.enemy.v_min"]], dtype=np.uint8)
    upper2 = np.array([v["vision.enemy.h_max2"], 255, 255], dtype=np.uint8)

    mask = cv2.bitwise_or(cv2.inRange(hsv, lower1, upper1),
                          cv2.inRange(hsv, lower2, upper2))

    kernel = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    return mask


def _find_contours(mask, shape):
    """Maskedeki nesneleri kutu olarak dondurur.

    Alan ve en-boy orani filtreleriyle gurultu elenir. Sonuclar
    alana gore buyukten kucuge siralanir.

    Args:
        mask: Ikili maske
        shape: Kare boyutu (yukseklik, genislik, kanal)

    Returns:
        list[tuple] — (x, y, w, h, alan_orani)
    """
    frame_area = shape[0] * shape[1]

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_SIMPLE)

    results = []

    for contour in contours:
        area = cv2.contourArea(contour)
        ratio = area / frame_area

        if ratio < settings.COLOR_MIN_AREA_RATIO:
            continue

        if ratio > settings.COLOR_MAX_AREA_RATIO:
            continue

        x, y, w, h = cv2.boundingRect(contour)

        if h == 0:
            continue

        aspect = w / h

        if not (settings.COLOR_MIN_ASPECT <= aspect <= settings.COLOR_MAX_ASPECT):
            continue

        results.append((x, y, w, h, ratio))

    results.sort(key=lambda r: r[4], reverse=True)

    return results[:settings.COLOR_MAX_TARGETS]