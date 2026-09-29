"""Balistik ve paralaks duzeltmesi.

Kamera ve namlu ayni eksende degildir. Iki bilesen hesaplanir:

1. Paralaks — kamera-namlu ofsetinden dogar, mesafeyle azalir:
       kayma_px = ofset_m * f_px / mesafe_m

2. Mermi dususu — yercekimi etkisi, mesafeyle artar:
       dusus_m = 0.5 * g * (mesafe / hiz)^2

Bu sistemde ofset kucuktur (20-23 mm); toplam duzeltme her mesafede
5-8 piksel civarindadir. Atis testinde bundan belirgin buyuk sapma
gorulurse sebep paralaks degil mekanik hizalamadir ve AIM_ZERO_X/Y
sabitleriyle duzeltilir.
"""

import logging

from config import settings

log = logging.getLogger("ballistics")

GRAVITY = 9.81


def correction(distance_m, focal_px):
    """Nisan noktasi duzeltmesini hesaplar.

    Args:
        distance_m: Hedef mesafesi (metre). None ise varsayilan kullanilir.
        focal_px: Odak uzakligi (piksel)

    Returns:
        (dx, dy) — nisangah otelemesi (piksel).
        Pozitif dx saga, pozitif dy asagi.
    """
    if not settings.BALLISTIC_CORRECTION_ENABLED:
        return settings.AIM_ZERO_X, settings.AIM_ZERO_Y

    if distance_m is None or distance_m <= 0:
        distance_m = settings.BALLISTIC_DEFAULT_RANGE

    # Paralaks: namlu solda ise nisan noktasi saga otelenir
    dx = -settings.MUZZLE_OFFSET_X * focal_px / distance_m

    # Namlu altta ise nisan noktasi yukari otelenir
    dy_parallax = -settings.MUZZLE_OFFSET_Y * focal_px / distance_m

    # Mermi dususu: yukari nisan alinir
    flight_time = distance_m / settings.MUZZLE_VELOCITY
    drop_m = 0.5 * GRAVITY * flight_time * flight_time
    dy_drop = -drop_m * focal_px / distance_m

    return (dx + settings.AIM_ZERO_X,
            dy_parallax + dy_drop + settings.AIM_ZERO_Y)


def describe(focal_px):
    """Farkli mesafelerdeki duzeltmeleri tablo olarak loglar.

    Args:
        focal_px: Odak uzakligi (piksel)
    """
    log.info("Balistik duzeltme (f_px=%.1f, ofset=%.4f/%.4f m):",
             focal_px, settings.MUZZLE_OFFSET_X, settings.MUZZLE_OFFSET_Y)
    log.info("  mesafe |    dx |    dy")

    for distance in (2.0, 3.0, 5.0, 10.0, 15.0):
        dx, dy = correction(distance, focal_px)
        log.info("  %5.1f m | %5.1f | %5.1f px", distance, dx, dy)