"""Tehdit onceliklendirme ve hedef secimi.

Angajman yokken kilitlenilecek hedefi belirler. Yalnizca dusman olarak
siniflandirilmis hedefler degerlendirilir; dost ve belirsiz hedefler
angajmana girmez (gereksinim GV-06).

Tehdit skoru su bilesenlerden olusur:

  Yakinlik   Kutu buyuklugu mesafeyle ters orantilidir; buyuk kutu
             yakin hedef demektir. Mesafe kestirimi guvenilir oldugunda
             (balon tespitlerinde) dogrudan mesafe kullanilir.

  Hiz        Hizli hareket eden hedef daha az sure icinde menzil disina
             cikar; onceligi yuksektir.

  Merkeze    Ekran merkezine yakin hedefe donmek daha kisa surer.
  yakinlik

  Guven      Dusuk guvenli tespitlere kilitlenmek riskli oldugu icin
             skor guven ile carpilir.

Balonlar dogrudan secilmez: angajman makete kilitlenir, nisan noktasi
balona kaydirilir (bkz. control/aiming.py). Boylece maket kaybolsa bile
hangi balonun hedef oldugu bilinir.
"""

import logging
import math

from config import settings
from core.enums import TargetClass, Team
from vision import track_store

log = logging.getLogger("threat")


def select_target(timestamp, frame_width=None, frame_height=None):
    """Kilitlenilecek en yuksek tehditli hedefi secer.

    Args:
        timestamp: Simdiki zaman (saniye)
        frame_width: Kare genisligi. None ise settings.FRAME_WIDTH.
        frame_height: Kare yuksekligi. None ise settings.FRAME_HEIGHT.

    Returns:
        vision.track_store.Track veya uygun hedef yoksa None
    """
    if frame_width is None:
        frame_width = settings.FRAME_WIDTH
    if frame_height is None:
        frame_height = settings.FRAME_HEIGHT

    candidates = _eligible_targets(timestamp)

    if not candidates:
        return None

    best = None
    best_score = None

    for track in candidates:
        score = _score(track, timestamp, frame_width, frame_height)

        if best_score is None or score > best_score:
            best = track
            best_score = score

    if best is not None:
        log.debug("Hedef secildi: id=%d cls=%d skor=%.2f (%d aday)",
                  best.track_id, best.cls, best_score, len(candidates))

    return best


def _eligible_targets(timestamp):
    """Angajmana uygun hedefleri suzer.

    Elenme nedenleri: onaylanmamis iz, bayat iz, dost veya belirsiz
    takim, balon sinifi, balonu tespit edilemeyen maket.

    Args:
        timestamp: Simdiki zaman (saniye)

    Returns:
        list[Track]
    """
    eligible = []

    for track in track_store.all_tracks():
        if not track.is_confirmed():
            continue

        if track.age(timestamp) > settings.TRACK_FRESH_WINDOW:
            continue

        if track.team != Team.ENEMY:
            continue

        if track.cls == TargetClass.BALLOON:
            continue

        if settings.THREAT_REQUIRE_BALLOON and not _has_balloon(track, timestamp):
            continue

        eligible.append(track)

    return eligible

def _has_balloon(track, timestamp):
    """Makete bagli taze bir balon izi olup olmadigini bildirir.

    Balonu patlatilmis maketler yeniden angajmana girmemelidir;
    vurulacak hedef kalmamistir.

    Args:
        track: Maket izi
        timestamp: Simdiki zaman (saniye)

    Returns:
        bool
    """
    for candidate in track_store.all_tracks():
        if candidate.cls != TargetClass.BALLOON:
            continue

        if candidate.parent_id != track.track_id:
            continue

        if candidate.age(timestamp) > settings.TRACK_FRESH_WINDOW:
            continue

        return True

    return False


def _score(track, timestamp, frame_width, frame_height):
    """Bir hedefin tehdit skorunu hesaplar.

    Args:
        track: Degerlendirilecek iz
        timestamp: Simdiki zaman (saniye)
        frame_width: Kare genisligi
        frame_height: Kare yuksekligi

    Returns:
        float — yuksek deger yuksek oncelik
    """
    x, y, vx, vy = track.motion.predict(timestamp)

    proximity = _proximity_score(track, frame_width, frame_height)
    speed = _speed_score(vx, vy, frame_width)
    centrality = _centrality_score(x, y, frame_width, frame_height)

    score = (settings.THREAT_W_PROXIMITY * proximity
             + settings.THREAT_W_SPEED * speed
             + settings.THREAT_W_CENTRALITY * centrality)

    return score * track.conf


def _proximity_score(track, frame_width, frame_height):
    """Yakinlik skorunu hesaplar.

    Kutu alaninin kare alanina orani kullanilir; buyuk kutu yakin
    hedef demektir. Kok alinarak dogrusal olceklenir.

    Args:
        track: Degerlendirilecek iz
        frame_width: Kare genisligi
        frame_height: Kare yuksekligi

    Returns:
        float — 0.0 ile 1.0 arasi
    """
    frame_area = frame_width * frame_height

    if frame_area <= 0:
        return 0.0

    box_area = track.width * track.height
    ratio = box_area / frame_area

    return min(1.0, math.sqrt(ratio) * settings.THREAT_PROXIMITY_SCALE)


def _speed_score(vx, vy, frame_width):
    """Hiz skorunu hesaplar.

    Hiz kare genisligine gore normalize edilir; boylece cozunurlukten
    bagimsiz olur.

    Args:
        vx: Yatay hiz (piksel/saniye)
        vy: Dikey hiz (piksel/saniye)
        frame_width: Kare genisligi

    Returns:
        float — 0.0 ile 1.0 arasi
    """
    if frame_width <= 0:
        return 0.0

    speed = math.hypot(vx, vy) / frame_width

    return min(1.0, speed / settings.THREAT_SPEED_REFERENCE)


def _centrality_score(x, y, frame_width, frame_height):
    """Merkeze yakinlik skorunu hesaplar.

    Merkezdeki hedef 1.0, kosedeki 0.0 alir.

    Args:
        x: Hedef merkezi, yatay
        y: Hedef merkezi, dikey
        frame_width: Kare genisligi
        frame_height: Kare yuksekligi

    Returns:
        float — 0.0 ile 1.0 arasi
    """
    cx = frame_width / 2.0
    cy = frame_height / 2.0

    max_distance = math.hypot(cx, cy)

    if max_distance <= 0:
        return 0.0

    distance = math.hypot(x - cx, y - cy)

    return max(0.0, 1.0 - distance / max_distance)