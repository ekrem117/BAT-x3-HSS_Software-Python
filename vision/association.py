"""Balon-maket eslestirmesi.

Balonlar maketlerin altinda asili durur ve hepsi kirmizidir; renk
analiziyle takimlari belirlenemez. Her balon, ustundeki makete gore
takimini devralir.

Eslestirme kriterleri:
    - Balon maketin altinda olmalidir
    - Yatayda hizali olmalidir
    - Dikey mesafe makul sinirlar icinde olmalidir

Eslesme bulunamayan balonlar UNKNOWN olarak isaretlenir ve angajmana
girmez.
"""

import logging

from core.enums import TargetClass, Team

log = logging.getLogger("association")

# Yatay hizalama toleransi — maket genisliginin kaci kati
HORIZONTAL_TOLERANCE = 1.5

# Dikey mesafe siniri — maket yuksekliginin kaci kati
MAX_VERTICAL_DISTANCE = 6.0


def associate(detections):
    """Balonlari maketlerle eslestirir ve takimlarini atar.

    Girdi listesini yerinde degistirir; balon tespitlerinin "team" ve
    "parent_id" alanlari guncellenir.

    Args:
        detections: Tespit sozlukleri listesi

    Returns:
        list[dict] — guncellenmis liste (ayni nesne)
    """
    balloons = [d for d in detections if d["cls"] == TargetClass.BALLOON]
    models = [d for d in detections if d["cls"] != TargetClass.BALLOON]

    if not balloons:
        return detections

    for balloon in balloons:
        parent = _find_parent(balloon, models)

        if parent is None:
            balloon["team"] = Team.UNKNOWN
            balloon["parent_id"] = None
            continue

        balloon["team"] = parent["team"]
        balloon["parent_id"] = parent["id"]

    return detections


def _find_parent(balloon, models):
    """Balonun ustundeki en yakin uygun maketi bulur.

    Args:
        balloon: Balon tespit sozlugu
        models: Maket tespitleri listesi

    Returns:
        dict — eslesen maket veya bulunamazsa None
    """
    balloon_cx = balloon["x"] + balloon["w"] / 2
    balloon_cy = balloon["y"] + balloon["h"] / 2

    best = None
    best_distance = None

    for model in models:
        model_cx = model["x"] + model["w"] / 2
        model_cy = model["y"] + model["h"] / 2

        # Maket balonun ustunde olmali
        if model_cy >= balloon_cy:
            continue

        horizontal_gap = abs(balloon_cx - model_cx)
        if horizontal_gap > model["w"] * HORIZONTAL_TOLERANCE:
            continue

        vertical_gap = balloon_cy - model_cy
        if vertical_gap > model["h"] * MAX_VERTICAL_DISTANCE:
            continue

        if best_distance is None or vertical_gap < best_distance:
            best = model
            best_distance = vertical_gap

    return best