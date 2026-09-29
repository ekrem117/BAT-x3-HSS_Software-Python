"""Sentetik tespit ureticisi.

Gercek model yokken veya YOLO devre disi birakildiginda arayuz tarafinin
gelistirilebilmesi icin hareketli sahte tespitler uretir.

settings.USE_YOLO = False yapildiginda devreye girer.

Cikti formati (docs/protocol_spec.md Bolum 11):
    {"id": int, "x": int, "y": int, "w": int, "h": int,
     "cls": int, "team": int, "conf": float, "parent_id": int|None}
"""

import math
import random

from config import settings
from core.enums import TargetClass, Team


class _FakeTarget:
    """Ekranda dairesel hareket eden sahte bir hedef."""

    def __init__(self, track_id, cls, team, cx, cy, radius, speed, size):
        self.track_id = track_id
        self.cls = cls
        self.team = team
        self.cx = cx
        self.cy = cy
        self.radius = radius
        self.speed = speed
        self.size = size
        self.phase = random.uniform(0, 2 * math.pi)

    def position(self, t):
        """Verilen zamandaki kutu konumunu hesaplar.

        Args:
            t: Zaman parametresi (kare sayaci)

        Returns:
            (x, y, w, h) — sol ust kose ve boyut
        """
        angle = self.phase + t * self.speed
        x = self.cx + self.radius * math.cos(angle) - self.size // 2
        y = self.cy + self.radius * math.sin(angle) * 0.5 - self.size // 2

        x = max(0, min(settings.FRAME_WIDTH - self.size, int(x)))
        y = max(0, min(settings.FRAME_HEIGHT - self.size, int(y)))

        return x, y, self.size, self.size


_targets = [
    _FakeTarget(1, TargetClass.DRONE, Team.ENEMY, 400, 300, 200, 0.03, 80),
    _FakeTarget(2, TargetClass.BALLOON, Team.ENEMY, 800, 400, 150, 0.02, 60),
    _FakeTarget(3, TargetClass.F16, Team.FRIEND, 300, 500, 120, 0.04, 100),
    _FakeTarget(4, TargetClass.HELICOPTER, Team.UNKNOWN, 950, 200, 100,
                0.025, 70),
]

_tick = 0


def get_detections():
    """Sahte tespit listesi uretir.

    Hedefler dairesel hareket eder ve arada bir kaybolur; gercek model
    davranisini taklit eder. Alici tarafin kaybolan hedefleri dogru ele
    aldigini test etmeyi saglar.

    Returns:
        list[dict] — protokol formatinda tespitler
    """
    global _tick
    _tick += 1

    detections = []

    for target in _targets:
        if (_tick // 90 + target.track_id) % 7 == 0:
            continue

        x, y, w, h = target.position(_tick)
        conf = 0.75 + 0.2 * abs(math.sin(_tick * 0.05 + target.track_id))

        detections.append({
            "id": target.track_id,
            "x": x,
            "y": y,
            "w": w,
            "h": h,
            "cls": target.cls,
            "team": target.team,
            "conf": round(conf, 2),
            "parent_id": None,
        })

    return detections