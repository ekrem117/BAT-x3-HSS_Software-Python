"""Dost/dusman renk siniflandirmasi.

Tespit edilen maketlerin bounding box'i icindeki baskin rengi analiz
ederek dost/dusman ayrimi yapar.

Sartname renkleri:
    Dusman  Kirmizi     #F50A0A
    Dost    Camgobegi   #00A3E0

Kirmizi HSV renk cemberinin basinda oldugu icin iki aralikta aranir
(0-10 ve 170-179). Esikler core.state uzerinden calisma sirasinda
ayarlanabilir; koda gomulu degildir (gereksinim GI-11).

Analiz yalnizca kutunun merkez bolgesinde yapilir; kenarlardaki arka
plan pikselleri karari bozmamalidir (gereksinim GI-15).

Balonlar bu modul tarafindan siniflandirilmaz — hepsi kirmizidir ve
takimlarini bagli olduklari maketten devralirlar (bkz. association.py).
"""

import logging

import cv2
import numpy as np

from config import settings
from core import state
from core.enums import Team

log = logging.getLogger("classifier")


def classify(frame, box):
    """Bir tespitin takimini renk analizine gore belirler.

    Args:
        frame: BGR NumPy dizisi (tam kare)
        box: Tespit sozlugu — x, y, w, h alanlari kullanilir

    Returns:
        int — Team.FRIEND, Team.ENEMY veya Team.UNKNOWN
    """
    roi = _extract_roi(frame, box)

    if roi is None or roi.size == 0:
        return Team.UNKNOWN

    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    total_pixels = hsv.shape[0] * hsv.shape[1]

    if total_pixels == 0:
        return Team.UNKNOWN

    enemy_ratio = _mask_ratio(hsv, _enemy_masks(hsv), total_pixels)
    friend_ratio = _mask_ratio(hsv, _friend_masks(hsv), total_pixels)

    min_ratio = settings.COLOR_MIN_PIXEL_RATIO

    if enemy_ratio < min_ratio and friend_ratio < min_ratio:
        return Team.UNKNOWN

    if enemy_ratio > friend_ratio:
        return Team.ENEMY

    return Team.FRIEND


def _extract_roi(frame, box):
    """Kutunun merkez bolgesini kirpar.

    Kenarlardaki arka plan pikselleri renk karari bozdugu icin yalnizca
    merkez bolge kullanilir. Oran settings.COLOR_ROI_RATIO ile belirlenir.

    Args:
        frame: BGR NumPy dizisi
        box: Tespit sozlugu

    Returns:
        BGR NumPy dizisi veya gecersiz kutu icin None
    """
    ratio = settings.COLOR_ROI_RATIO

    cx = box["x"] + box["w"] / 2
    cy = box["y"] + box["h"] / 2
    half_w = box["w"] * ratio / 2
    half_h = box["h"] * ratio / 2

    x1 = max(0, int(cx - half_w))
    y1 = max(0, int(cy - half_h))
    x2 = min(frame.shape[1], int(cx + half_w))
    y2 = min(frame.shape[0], int(cy + half_h))

    if x2 <= x1 or y2 <= y1:
        return None

    return frame[y1:y2, x1:x2]


def _enemy_masks(hsv):
    """Dusman (kirmizi) renk maskesini uretir.

    Kirmizi HSV cemberinin basinda oldugu icin iki aralik birlestirilir.

    Args:
        hsv: HSV NumPy dizisi

    Returns:
        Ikili maske (uint8)
    """
    v = state.PARAM_VALUES

    lower1 = np.array([v["vision.enemy.h_min"],
                       v["vision.enemy.s_min"],
                       v["vision.enemy.v_min"]], dtype=np.uint8)
    upper1 = np.array([v["vision.enemy.h_max"], 255, 255], dtype=np.uint8)

    lower2 = np.array([v["vision.enemy.h_min2"],
                       v["vision.enemy.s_min"],
                       v["vision.enemy.v_min"]], dtype=np.uint8)
    upper2 = np.array([v["vision.enemy.h_max2"], 255, 255], dtype=np.uint8)

    mask1 = cv2.inRange(hsv, lower1, upper1)
    mask2 = cv2.inRange(hsv, lower2, upper2)

    return cv2.bitwise_or(mask1, mask2)


def _friend_masks(hsv):
    """Dost (camgobegi) renk maskesini uretir.

    Args:
        hsv: HSV NumPy dizisi

    Returns:
        Ikili maske (uint8)
    """
    v = state.PARAM_VALUES

    lower = np.array([v["vision.friend.h_min"],
                      v["vision.friend.s_min"],
                      v["vision.friend.v_min"]], dtype=np.uint8)
    upper = np.array([v["vision.friend.h_max"], 255, 255], dtype=np.uint8)

    return cv2.inRange(hsv, lower, upper)


def _mask_ratio(hsv, mask, total_pixels):
    """Maskenin doldurdugu piksel oranini hesaplar.

    Args:
        hsv: HSV NumPy dizisi (imza tutarliligi icin)
        mask: Ikili maske
        total_pixels: Toplam piksel sayisi

    Returns:
        float — 0.0 ile 1.0 arasinda oran
    """
    return int(np.count_nonzero(mask)) / total_pixels