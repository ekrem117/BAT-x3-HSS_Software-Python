"""Sentetik test karesi ureticisi.

Kamera yokken veya video zincirini kameradan bagimsiz test ederken
kullanilir. Hareketli ogeler icerir; akisin canli oldugunu gozle
dogrulamayi saglar.
"""

import cv2
import numpy as np

BOX_WIDTH = 100
BOX_HEIGHT = 100
BOX_SPEED = 8


def make_frame(counter, width, height):
    """Sentetik bir test karesi uretir.

    Args:
        counter: Kare sayaci — hareketli ogelerin konumunu belirler
        width: Kare genisligi (piksel)
        height: Kare yuksekligi (piksel)

    Returns:
        BGR NumPy dizisi, sekil (height, width, 3), tip uint8
    """
    frame = np.zeros((height, width, 3), dtype=np.uint8)

    gradient = np.linspace(20, 60, height, dtype=np.uint8)
    frame[:, :, :] = gradient[:, np.newaxis, np.newaxis]

    x = (counter * BOX_SPEED) % (width - BOX_WIDTH)
    y = (height - BOX_HEIGHT) // 2
    cv2.rectangle(frame, (x, y), (x + BOX_WIDTH, y + BOX_HEIGHT),
                  (0, 255, 0), -1)

    cv2.putText(frame, "SENTETIK", (20, 100),
                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 200, 255), 2)

    return frame