"""Nisan cozumu.

Kilitli hedefin konumundan servo hata sinyali uretir.

Uc bilesen hesaplanir:

1. Ileri ongoru (lead)
   Sistem gecikmesi ~300 ms'dir: kamera, cikarim, seri hat ve servo
   mekanigi. Hedefin su anki konumuna nisan alinirsa taret surekli
   geride kalir. Bu nedenle hedefin gecikme kadar ilerideki tahmini
   konumu kullanilir.

2. Balon ofseti
   Balon maketin altinda sabit bir geometrik oranda asilidir. Maket
   kutusunun yuksekligi mesafeyle olceklendigi icin bu oran mesafeden
   bagimsizdir; mesafe kestirimi gerekmez.

3. Olu bant
   Kucuk hatalarda servo surulmez. Aksi halde taret hedefin uzerinde
   surekli titrer.
"""

import logging
import math

from config import settings
from vision import ballistics, ranging

log = logging.getLogger("aiming")


def solve(lock_info, frame_width=None, frame_height=None):
    """Kilitli hedef icin nisan hatasini hesaplar.

    Args:
        lock_info: control.engagement.current() ciktisi veya None
        frame_width: Kare genisligi. None ise settings.FRAME_WIDTH.
        frame_height: Kare yuksekligi. None ise settings.FRAME_HEIGHT.

    Returns:
        dict veya hedef yoksa None:
            aim_x, aim_y      Nisan noktasi (piksel)
            error_x, error_y  Merkeze gore hata (piksel)
            distance          Hata buyuklugu (piksel)
            on_target         Olu bant icinde mi
    """
    if lock_info is None:
        return None

    if frame_width is None:
        frame_width = settings.FRAME_WIDTH
    if frame_height is None:
        frame_height = settings.FRAME_HEIGHT

    center_x = frame_width / 2.0
    center_y = frame_height / 2.0

    lead_x, lead_y = _apply_lead(lock_info)
    aim_x, aim_y = _apply_balloon_offset(lead_x, lead_y, lock_info)

    dx, dy = ballistics.correction(
        lock_info.get("dist"), ranging.focal_length_px()
    )
    aim_x += dx
    aim_y += dy

    error_x = aim_x - center_x
    error_y = aim_y - center_y

    
    error_x = aim_x - center_x
    error_y = aim_y - center_y
    distance = math.hypot(error_x, error_y)

    return {
        "aim_x": round(aim_x, 1),
        "aim_y": round(aim_y, 1),
        "error_x": round(error_x, 1),
        "error_y": round(error_y, 1),
        "distance": round(distance, 1),
        "on_target": distance <= settings.AIM_DEAD_ZONE_PX,
    }


def _apply_lead(lock_info):
    """Hedefin gecikme kadar ilerideki konumunu tahmin eder.

    Args:
        lock_info: Angajman ozeti

    Returns:
        (x, y) — ongorulen konum (piksel)
    """
    lead = settings.AIM_LEAD_TIME

    x = lock_info["x"] + lock_info["vx"] * lead
    y = lock_info["y"] + lock_info["vy"] * lead

    return x, y


def _apply_balloon_offset(x, y, lock_info):
    """Nisan noktasini maketten balona kaydirir.

    Balon maketin altindadir. Kaydirma miktari maket kutusunun
    yuksekligiyle orantilidir; boylece mesafe degistiginde oran
    korunur.

    Balon hedefin kendisiyse kaydirma yapilmaz.

    Args:
        x: Ongorulen x konumu
        y: Ongorulen y konumu
        lock_info: Angajman ozeti

    Returns:
        (x, y) — nisan noktasi
    """
    if not settings.AIM_BALLOON_OFFSET_ENABLED:
        return x, y

    if lock_info["cls"] == settings.BALLOON_CLASS:
        return x, y

    box_height = lock_info.get("h")
    if not box_height:
        return x, y

    return x, y + box_height * settings.AIM_BALLOON_OFFSET_RATIO