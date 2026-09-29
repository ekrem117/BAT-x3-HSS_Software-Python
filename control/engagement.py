"""Angajman durum yonetimi.

Kilitli hedefin kimligini takipci ID'sinden bagimsiz olarak korur.

Takipci (ByteTrack) kareler arasi calisir ve iz sik sik duser; hedef
kisa sure gorunmez kaldiginda yeni bir track_id atanir. Angajman ise
saniyeler boyunca surer: "bu hedefe 2 el attim, imha teyidi
bekliyorum, 800 ms'dir gormuyorum ama pes etmedim."

Bu nedenle kilit bir track_id'ye baglidir ancak ona mahkum degildir.
Iz dustugunde konum Kalman ile tahmin edilmeye devam eder; tahmin
edilen konuma yakin, ayni sinif ve takimdan yeni bir iz cikarsa kilit
ona devredilir.

Durum makinesi:
    IDLE -> LOCKED -> LOST -> LOCKED        (yeniden eslestirme)
                        -> ABANDONED        (tolerans doldu)
            LOCKED  -> DESTROYED            (imha teyidi)
"""

import logging
import math
import threading
import time

from config import settings
from vision import track_store
from core.enums import ENGAGEMENT_STATE_NAMES, EngagementState, TargetClass
from core import ego_motion, state

log = logging.getLogger("engagement")

_lock = threading.Lock()
_current = None


class Engagement:
    """Tek bir hedefe yonelik angajman kaydi."""

    def __init__(self, track, timestamp):
        """Yeni angajman baslatir.

        Args:
            track: vision.track_store.Track nesnesi
            timestamp: Baslangic zamani (saniye)
        """
        x, y, vx, vy = track.motion.as_tuple()

        self.balloon_id = None
        self.balloon_lost_since = None

        self.track_id = track.track_id
        self.cls = track.cls
        self.team = track.team

        self.state = EngagementState.LOCKED
        self.started_at = timestamp
        self.last_seen = timestamp
        self.lost_since = None

        self.position = (x, y)
        self.velocity = (vx, vy)
        self.uncertainty = track.motion.position_uncertainty()

        self.shots_fired = 0
        self.reacquire_count = 0

        self.width = track.width
        self.height = track.height
        self.dist = track.dist

        # Konumun olculdugu andaki taret acisi. Taret dondukce konum
        # bu referansa gore kaydirilir.
        self.pan_angle = _turret_pan()
        self.tilt_angle = _turret_tilt()

    def lost_duration(self, timestamp):
        """Iz dustugunden bu yana gecen sureyi dondurur.

        Args:
            timestamp: Simdiki zaman (saniye)

        Returns:
            float — saniye. Iz duser durumda degilse 0.
        """
        if self.lost_since is None:
            return 0.0
        return timestamp - self.lost_since

    def search_radius(self, timestamp):
        """Yeniden eslestirme icin arama yaricapini hesaplar.

        Yaricap uc bilesenden olusur: taban deger, Kalman belirsizligi
        ve kayip suresince hedefin katedebilecegi mesafe.

        Args:
            timestamp: Simdiki zaman (saniye)

        Returns:
            float — piksel
        """
        vx, vy = self.velocity
        speed = math.hypot(vx, vy)
        lost_for = self.lost_duration(timestamp)

        return (settings.ENGAGE_REACQUIRE_RADIUS
                + self.uncertainty * settings.ENGAGE_UNCERTAINTY_SCALE
                + speed * lost_for)

    def to_dict(self, timestamp):
        """Angajman durumunu sozluk olarak dondurur.

        Args:
            timestamp: Simdiki zaman (saniye)

        Returns:
            dict — arayuz ve loglama icin ozet
        """
        return {
            "track_id": self.track_id,
            "state": self.state,
            "state_name": ENGAGEMENT_STATE_NAMES.get(self.state, "?"),
            "cls": self.cls,
            "team": self.team,
            "x": round(self.position[0], 1),
            "y": round(self.position[1], 1),
            "vx": round(self.velocity[0], 1),
            "vy": round(self.velocity[1], 1),
            "lost_for": round(self.lost_duration(timestamp), 2),
            "shots_fired": self.shots_fired,
            "reacquires": self.reacquire_count,
            "duration": round(timestamp - self.started_at, 2),
            "w": self.width,
            "h": self.height,
            "dist": self.dist,
            "balloon_id": self.balloon_id,
        }


# ---------------------------------------------------------------------------
# Ana dongu
# ---------------------------------------------------------------------------

def _turret_pan():
    """Guncel taret pan acisini dondurur."""
    return float(state.PARAM_VALUES.get("system.pan_angle", 0.0))


def _turret_tilt():
    """Guncel taret tilt acisini dondurur."""
    return float(state.PARAM_VALUES.get("system.tilt_angle", 0.0))


def _apply_ego_motion():
    """Kilitli hedefin piksel konumunu taret hareketine gore kaydirir.

    Kilit disaridan alinmis olmalidir.

    Kamera taretin ustundedir; taret dondugunde sabit bir hedef bile
    goruntude yer degistirir. Bu duzeltme yapilmazsa
    _find_reacquire_candidate yanlis yerde arar ve kilit gereksiz
    yere duser.
    """
    pan_now = _turret_pan()
    tilt_now = _turret_tilt()

    _current.position = ego_motion.compensate_position(
        _current.position,
        _current.pan_angle, _current.tilt_angle,
        pan_now, tilt_now,
    )

    _current.pan_angle = pan_now
    _current.tilt_angle = tilt_now

def update(timestamp=None):
    """Angajman durumunu gunceller.

    Kontrol dongusu tarafindan her turda cagrilmalidir. Kilitli iz
    goruluyorsa konum guncellenir; dusmusse yeniden eslestirme denenir.

    Args:
        timestamp: Simdiki zaman. None ise su an kullanilir.

    Returns:
        Engagement nesnesi veya aktif angajman yoksa None
    """
    if timestamp is None:
        timestamp = time.time()

    with _lock:
        if _current is None:
            return None

        if _current.state in (EngagementState.DESTROYED,
                              EngagementState.ABANDONED):
            return _current

        _apply_ego_motion()
        track = track_store.get_track(_current.track_id)

        if track is not None and track.age(timestamp) < settings.ENGAGE_TRACK_STALE:
            _follow(track, timestamp)
        else:
            _handle_lost(timestamp)

        if _current.state == EngagementState.LOCKED:
            _check_kill(timestamp)

        return _current


def _follow(track, timestamp):
    """Kilitli izi takip eder ve angajman durumunu tazeler.

    Kilit disaridan alinmis olmalidir.

    Args:
        track: Takip edilen iz
        timestamp: Simdiki zaman (saniye)
    """
    x, y, vx, vy = track.motion.predict(timestamp)

    _current.position = (x, y)
    _current.velocity = (vx, vy)
    _current.uncertainty = track.motion.position_uncertainty()
    _current.team = track.team
    _current.last_seen = timestamp
    _current.width = track.width
    _current.height = track.height
    _current.dist = track.dist
    _current.pan_angle = _turret_pan()
    _current.tilt_angle = _turret_tilt()

    if _current.state == EngagementState.LOST:
        log.info("Hedef yeniden goruldu: track_id=%d kayip_sure=%.2f s",
                 _current.track_id, _current.lost_duration(timestamp))
        _current.state = EngagementState.LOCKED
        _current.lost_since = None


def _handle_lost(timestamp):
    """Iz dustugunde yeniden eslestirme veya vazgecme kararini verir.

    Kilit disaridan alinmis olmalidir.

    Args:
        timestamp: Simdiki zaman (saniye)
    """
    if _current.lost_since is None:
        _current.lost_since = timestamp
        _current.state = EngagementState.LOST
        log.info("Kilitli iz dustu: track_id=%d, yeniden eslestirme "
                 "deneniyor", _current.track_id)

    lost_for = _current.lost_duration(timestamp)

    if lost_for > settings.ENGAGE_LOST_TIMEOUT:
        _abandon(timestamp, "tolerans doldu")
        return

    candidate = _find_reacquire_candidate(timestamp)

    if candidate is not None:
        _reacquire(candidate, timestamp)
    else:
        log.debug("Aday bulunamadi: konum=(%.0f, %.0f) yaricap=%.0f iz=%d",
                  _current.position[0], _current.position[1],
                  _current.search_radius(timestamp),
                  len(track_store.all_tracks()))
        _extrapolate(timestamp)


def _extrapolate(timestamp):
    """Iz yokken konumu son bilinen hizla ileri tasir.

    Kilit disaridan alinmis olmalidir.

    Args:
        timestamp: Simdiki zaman (saniye)
    """
    dt = timestamp - _current.last_seen
    x, y = _current.position
    vx, vy = _current.velocity

    _current.position = (x + vx * dt, y + vy * dt)
    _current.last_seen = timestamp
    _current.uncertainty += abs(vx) * dt + abs(vy) * dt


def _find_reacquire_candidate(timestamp):
    """Kayip hedefle eslesebilecek yeni bir iz arar.

    Kilit disaridan alinmis olmalidir.

    Esleme kriterleri: tahmin edilen konuma yakinlik, ayni sinif,
    ayni takim. En yakin uygun aday secilir.

    Args:
        timestamp: Simdiki zaman (saniye)

    Returns:
        Track nesnesi veya uygun aday yoksa None
    """
    radius = _current.search_radius(timestamp)
    px, py = _current.position

    best = None
    best_distance = None

    for track in track_store.all_tracks():
        if track.track_id == _current.track_id:
            continue

        if not track.is_confirmed():
            continue

        if settings.ENGAGE_MATCH_CLASS and track.cls != _current.cls:
            continue

        if settings.ENGAGE_MATCH_TEAM and track.team != _current.team:
            continue

        tx, ty, _, _ = track.predict_compensated(timestamp)
        distance = math.hypot(tx - px, ty - py)

        if distance > radius:
            continue

        if best_distance is None or distance < best_distance:
            best = track
            best_distance = distance

    return best


def _reacquire(track, timestamp):
    """Kilidi yeni bir ize devreder.

    Kilit disaridan alinmis olmalidir.

    Args:
        track: Yeni iz
        timestamp: Simdiki zaman (saniye)
    """
    old_id = _current.track_id
    lost_for = _current.lost_duration(timestamp)

    _current.track_id = track.track_id
    _current.state = EngagementState.LOCKED
    _current.lost_since = None
    _current.reacquire_count += 1

    _follow(track, timestamp)

    log.info("Kilit devredildi: %d -> %d (kayip %.2f s, %d. devir)",
             old_id, track.track_id, lost_for, _current.reacquire_count)


def _abandon(timestamp, reason):
    """Angajmani sonlandirir.

    Kilit disaridan alinmis olmalidir.

    Args:
        timestamp: Simdiki zaman (saniye)
        reason: Vazgecme nedeni (loglama icin)
    """
    _current.state = EngagementState.ABANDONED
    log.info("Angajman birakildi: track_id=%d neden=%s sure=%.2f s atis=%d",
             _current.track_id, reason,
             timestamp - _current.started_at, _current.shots_fired)


# ---------------------------------------------------------------------------
# Dis arayuz
# ---------------------------------------------------------------------------

def lock(track_id, timestamp=None):
    """Belirtilen ize kilitlenir.

    Mevcut angajman varsa iptal edilir.

    Args:
        track_id: Kilitlenecek iz kimligi
        timestamp: Simdiki zaman. None ise su an kullanilir.

    Returns:
        bool — kilitlenme basarili mi
    """
    global _current

    if timestamp is None:
        timestamp = time.time()

    track = track_store.get_track(track_id)

    if track is None:
        log.warning("Kilitlenemedi: track_id=%d bulunamadi", track_id)
        return False

    if not track.is_confirmed():
        log.warning("Kilitlenemedi: track_id=%d henuz onaylanmamis", track_id)
        return False

    with _lock:
        if _current is not None and _current.state in (
                EngagementState.LOCKED, EngagementState.LOST):
            log.info("Onceki angajman iptal edildi: track_id=%d",
                     _current.track_id)

        _current = Engagement(track, timestamp)
        log.info("Kilitlenildi: track_id=%d cls=%d team=%d",
                 track_id, track.cls, track.team)

    return True


def release():
    """Kilidi birakir."""
    global _current

    with _lock:
        if _current is not None:
            log.info("Kilit birakildi: track_id=%d", _current.track_id)
        _current = None


def register_shot(timestamp=None):
    """Kilitli hedefe atis yapildigini kaydeder.

    Atis siniri asilirsa angajman birakilir.

    Args:
        timestamp: Simdiki zaman. None ise su an kullanilir.
    """
    if timestamp is None:
        timestamp = time.time()

    with _lock:
        if _current is None:
            return

        _current.shots_fired += 1

        if _current.shots_fired >= settings.ENGAGE_MAX_SHOTS:
            _abandon(timestamp, "atis siniri asildi")


def confirm_kill(timestamp=None):
    """Imha teyidini kaydeder.

    Args:
        timestamp: Simdiki zaman. None ise su an kullanilir.
    """
    if timestamp is None:
        timestamp = time.time()

    with _lock:
        if _current is None:
            return

        _current.state = EngagementState.DESTROYED
        log.info("Imha teyit edildi: track_id=%d sure=%.2f s atis=%d",
                 _current.track_id, timestamp - _current.started_at,
                 _current.shots_fired)


def current(timestamp=None):
    """Mevcut angajman ozetini dondurur.

    Args:
        timestamp: Simdiki zaman. None ise su an kullanilir.

    Returns:
        dict veya aktif angajman yoksa None
    """
    if timestamp is None:
        timestamp = time.time()

    with _lock:
        if _current is None:
            return None
        return _current.to_dict(timestamp)


def is_active():
    """Aktif bir angajman olup olmadigini bildirir.

    Returns:
        bool
    """
    with _lock:
        return _current is not None and _current.state in (
            EngagementState.LOCKED, EngagementState.LOST)


def _check_kill(timestamp):
    """Kilitli maketin balonunun imha edilip edilmedigini kontrol eder.

    Maket vurulmaz; hedef, maketin altindaki balondur. Maket kutusu
    angajman boyunca gorunur kalir, bu nedenle imha teyidi maketin
    kaybolmasindan cikarilamaz.

    Balon patladiginda model onu artik goremez. Kilitli makete bagli
    balon belirli bir sure boyunca goruntuye girmezse ve hedefe atis
    yapilmissa imha teyit edilmis sayilir.

    Kilit disaridan alinmis olmalidir.

    Args:
        timestamp: Simdiki zaman (saniye)
    """
    balloon = _find_balloon(_current.track_id, timestamp)

    if balloon is not None:
        _current.balloon_id = balloon.track_id
        _current.balloon_lost_since = None
        return

    # Hedefe hic atis yapilmadiysa balonun gorunmemesi imha degil,
    # tespit eksikligidir.
    if _current.shots_fired == 0:
        return

    if _current.balloon_lost_since is None:
        _current.balloon_lost_since = timestamp
        return

    lost_for = timestamp - _current.balloon_lost_since

    if lost_for >= settings.ENGAGE_KILL_CONFIRM_TIME:
        _current.state = EngagementState.DESTROYED
        log.info("Imha teyit edildi: track_id=%d balon=%s sure=%.2f s atis=%d",
                 _current.track_id, _current.balloon_id,
                 timestamp - _current.started_at, _current.shots_fired)


def _find_balloon(parent_track_id, timestamp):
    """Belirtilen makete bagli balon izini bulur.

    Args:
        parent_track_id: Maket izinin kimligi
        timestamp: Simdiki zaman (saniye)

    Returns:
        Track veya bulunamazsa None
    """
    for track in track_store.all_tracks():
        if track.cls != TargetClass.BALLOON:
            continue

        if track.parent_id != parent_track_id:
            continue

        if track.age(timestamp) > settings.TRACK_FRESH_WINDOW:
            continue

        return track

    return None