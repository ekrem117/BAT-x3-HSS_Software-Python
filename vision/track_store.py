"""Iz deposu ve hareket tahmini yonetimi.

Her track_id icin bir MotionModel tutar. Tespit geldiginde filtreyi
gunceller, tespit yokken tahmine devam eder.

Cikarim ~10 Hz, kontrol dongusu 50 Hz calisir. Bu modul sayesinde
kontrol dongusu tespiti beklemez; predict_all() ile hedeflerin o anki
tahmini konumunu alir.

Kaybolan izler hemen silinmez; belirli bir sure tahmin edilmeye devam
eder. Angajman katmani bu tahminleri kullanarak hedefi yeniden
eslestirebilir.
"""

import logging
import threading
import time

from config import settings
from vision.motion import MotionModel

from core import ego_motion, state


def _turret_pan():
    return float(state.PARAM_VALUES.get("system.pan_angle", 0.0))


def _turret_tilt():
    return float(state.PARAM_VALUES.get("system.tilt_angle", 0.0))

log = logging.getLogger("track_store")

_lock = threading.Lock()
_tracks = {}


class Track:

    def predict_compensated(self, timestamp):
        """Konumu tahmin eder ve taret hareketini telafi eder.

        Tespit geldigi an konum guncel kamera cercevesindedir. Tespit
        kesildikten sonra kamera donmeye devam eder; telafi olmadan
        tahmin ekranda donmus kalir ve gercek hedeften uzaklasir.

        Args:
            timestamp: Hedef zaman (saniye)

        Returns:
            (x, y, vx, vy)
        """
        cx, cy, vx, vy = self.motion.predict(timestamp)

        cx, cy = ego_motion.compensate_position(
            (cx, cy),
            self.pan_at_seen, self.tilt_at_seen,
            _turret_pan(), _turret_tilt(),
        )

        return cx, cy, vx, vy

    """Tek bir hedefin izleme kaydi."""

    def __init__(self, track_id, detection, timestamp):
        """Yeni bir iz olusturur.

        Args:
            track_id: Takipci tarafindan atanan kimlik
            detection: Tespit sozlugu
            timestamp: Olusturma zamani (saniye)
        """
        cx = detection["x"] + detection["w"] / 2
        cy = detection["y"] + detection["h"] / 2

        self.track_id = track_id
        self.motion = MotionModel(cx, cy, timestamp)

        self.width = detection["w"]
        self.height = detection["h"]
        self.cls = detection["cls"]
        self.team = detection["team"]
        self.conf = detection["conf"]
        self.parent_id = detection.get("parent_id")
        # ranging.annotate() tarafindan eklenir; her tespitte bulunur ama
        # kestirilemediyse None olabilir (bkz. vision/ranging.py).
        self.dist = detection.get("dist")
        self.band = detection.get("band")
        self.band_name = detection.get("band_name")
        self.dist_ok = detection.get("dist_ok", False)

        self.created_at = timestamp
        self.last_seen = timestamp
        self.hit_count = 1

        self.pan_at_seen = _turret_pan()
        self.tilt_at_seen = _turret_tilt()

    def update(self, detection, timestamp):
        """Izi yeni tespitle gunceller.

        Args:
            detection: Tespit sozlugu
            timestamp: Olcum zamani (saniye)
        """
        cx = detection["x"] + detection["w"] / 2
        cy = detection["y"] + detection["h"] / 2

        self.motion.update(cx, cy, timestamp)

        self.width = detection["w"]
        self.height = detection["h"]
        self.cls = detection["cls"]
        self.team = detection["team"]
        self.conf = detection["conf"]
        self.parent_id = detection.get("parent_id")
        self.dist = detection.get("dist")
        self.band = detection.get("band")
        self.band_name = detection.get("band_name")
        self.dist_ok = detection.get("dist_ok", False)

        self.last_seen = timestamp
        self.hit_count += 1

        self.pan_at_seen = _turret_pan()
        self.tilt_at_seen = _turret_tilt()

    def age(self, timestamp):
        """Son gorulmeden bu yana gecen sureyi dondurur.

        Args:
            timestamp: Simdiki zaman (saniye)

        Returns:
            float — saniye
        """
        return timestamp - self.last_seen

    def is_confirmed(self):
        """Izin yeterince kararli ve guvenilir olup olmadigini bildirir.

        Tek karelik yanlis pozitiflerin ve dusuk guvenli tespitlerin
        angajmana girmesini engeller.

        Returns:
            bool
        """
        return (self.hit_count >= settings.TRACK_MIN_HITS
                and self.conf >= settings.TRACK_MIN_CONFIDENCE)

    def to_detection(self, timestamp):
        """Izi tespit sozlugu formatina cevirir.

        Konum, verilen zamana gore tahmin edilir; son olcum degil.

        Args:
            timestamp: Hedef zaman (saniye)

        Returns:
            dict — protokol formatinda tespit
        """
        cx, cy, vx, vy = self.motion.predict(timestamp)

        return {
            "id": self.track_id,
            "x": int(cx - self.width / 2),
            "y": int(cy - self.height / 2),
            "w": self.width,
            "h": self.height,
            "cls": self.cls,
            "team": self.team,
            "conf": self.conf,
            "parent_id": self.parent_id,
            "vx": round(vx, 1),
            "vy": round(vy, 1),
            "age": round(self.age(timestamp), 2),
            "predicted": self.age(timestamp) > settings.TRACK_FRESH_WINDOW,
            "dist": self.dist,
            "band": self.band,
            "band_name": self.band_name,
            "dist_ok": self.dist_ok,
        }


def update(detections, timestamp=None):
    """Tespit listesiyle izleri gunceller.

    Yeni track_id'ler icin iz olusturur, mevcut olanlari gunceller,
    suresi dolanlari siler.

    track_id degeri -1 olan tespitler (takipci tarafindan onaylanmamis)
    yok sayilir.

    Args:
        detections: Tespit sozlukleri listesi
        timestamp: Olcum zamani. None ise su an kullanilir.

    Returns:
        int — aktif iz sayisi
    """
    if timestamp is None:
        timestamp = time.time()

    with _lock:
        seen_ids = set()

        for det in detections:
            track_id = det.get("id", -1)
            if track_id < 0:
                continue

            seen_ids.add(track_id)

            if track_id in _tracks:
                _tracks[track_id].update(det, timestamp)
            else:
                _tracks[track_id] = Track(track_id, det, timestamp)
                log.debug("Yeni iz: id=%d cls=%d", track_id, det["cls"])

        _prune(timestamp)
        return len(_tracks)


def _prune(timestamp):
    """Suresi dolan izleri siler.

    Kilit disaridan alinmis olmalidir.

    Args:
        timestamp: Simdiki zaman (saniye)
    """
    expired = [
        track_id for track_id, track in _tracks.items()
        if track.age(timestamp) > settings.TRACK_MAX_AGE
    ]

    for track_id in expired:
        log.debug("Iz suresi doldu: id=%d yas=%.2f s",
                  track_id, _tracks[track_id].age(timestamp))
        del _tracks[track_id]


def predict_all(timestamp=None):
    """Tum izlerin verilen andaki tahmini durumunu dondurur.

    Kontrol dongusu ve yayin katmani bu fonksiyonu kullanir; cikarim
    beklenmez.

    Args:
        timestamp: Hedef zaman. None ise su an kullanilir.

    Returns:
        list[dict] — protokol formatinda tespitler
    """
    if timestamp is None:
        timestamp = time.time()

    with _lock:
        return [
            track.to_detection(timestamp)
            for track in _tracks.values()
            if track.is_confirmed()
            and track.age(timestamp) <= settings.TRACK_PUBLISH_MAX_AGE
        ]


def get_track(track_id):
    """Belirli bir izi dondurur.

    Angajman katmani kilitli hedefi bu fonksiyonla takip eder.

    Args:
        track_id: Aranan iz kimligi

    Returns:
        Track nesnesi veya bulunamazsa None
    """
    with _lock:
        return _tracks.get(track_id)


def all_tracks():
    """Tum izleri dondurur (onaylanmamis olanlar dahil).

    Returns:
        list[Track]
    """
    with _lock:
        return list(_tracks.values())


def clear():
    """Tum izleri siler. Mod gecislerinde kullanilir."""
    with _lock:
        count = len(_tracks)
        _tracks.clear()
        log.info("Tum izler temizlendi (%d iz)", count)