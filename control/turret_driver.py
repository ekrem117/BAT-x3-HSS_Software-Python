"""Taret surme adaptoru.

Nisan hatasini analog girdi oranina cevirir ve SystemManager'a iletir.

Aci hesabi, yumusatma, tepki egrisi ve limit kirpma SystemManager
tarafinda yapilir (bkz. _build_analog_payload_locked). Bu modul yalnizca
"hedef ne kadar uzakta" bilgisini "kolu ne kadar cekmeli" bilgisine
cevirir; boylece manuel kol ve otonom takip ayni hareket yolunu kullanir
ve ayarlar tek yerde toplanir.

Hedef gorunmuyorken (LOST durumu) girdi sifirlanir. Kalman tahmini
kiliti korumak icin yeterlidir ancak taret surmek icin degildir; tahmine
gore donmek hedefi buyuk olcude kacirmaya yol acar.
"""

import logging

from config import settings
from core.enums import EngagementState
from core import state
import time

log = logging.getLogger("turret_driver")

_backend = None
_last_logged = None
# Ileri besleme durumu. Filtrelenmis hedef acisal hizi (taret birimi/s).
_ff_pan = 0.0
_ff_tilt = 0.0
_ff_last_pan = None
_ff_last_tilt = None
_ff_last_ts = None

def _turret_angles():
    """Guncel taret acilarini dondurur."""
    return (float(state.PARAM_VALUES.get("system.pan_angle", 0.0)),
            float(state.PARAM_VALUES.get("system.tilt_angle", 0.0)))


def _reset_feedforward():
    """Ileri besleme durumunu sifirlar.

    Kilit dustugunde veya hedef bayatladiginda cagrilir. Aksi halde
    eski hiz kestirimiyle surmeye devam edilir.
    """
    global _ff_pan, _ff_tilt, _ff_last_pan, _ff_last_tilt, _ff_last_ts

    _ff_pan = 0.0
    _ff_tilt = 0.0
    _ff_last_pan = None
    _ff_last_tilt = None
    _ff_last_ts = None

    state.PARAM_VALUES["control.ff_pan"] = 0.0
    state.PARAM_VALUES["control.ff_tilt"] = 0.0


def _feedforward(lock_info):
    """Hedefin acisal hizini analog girdi oranina cevirir.

    Piksel hizi taretin kendi donusunu icerir; once aci uzayina
    cevrilir:

        hedef_acisal_hizi = taret_acisal_hizi + vx / C
        C = EGO_PX_PER_PAN_UNIT * EGO_PAN_SIGN

    Sonuc agir filtrelenir ve sinirlanir; gerekcesi modul
    aciklamasindadir.

    Args:
        lock_info: control.engagement.current() ciktisi

    Returns:
        (pan, tilt) — analog girdi katkisi (-AIM_FF_MAX ... +AIM_FF_MAX)
    """
    global _ff_pan, _ff_tilt, _ff_last_pan, _ff_last_tilt, _ff_last_ts

    if not settings.AIM_FEEDFORWARD_ENABLED:
        return 0.0, 0.0

    # Bayat kestirimle surulmez.
    if lock_info.get("lost_for", 0.0) > settings.AIM_FF_MAX_AGE_S:
        _reset_feedforward()
        return 0.0, 0.0

    now = time.monotonic()
    pan_angle, tilt_angle = _turret_angles()

    if _ff_last_ts is None:
        _ff_last_ts = now
        _ff_last_pan = pan_angle
        _ff_last_tilt = tilt_angle
        return 0.0, 0.0

    dt = now - _ff_last_ts
    _ff_last_ts = now

    # Cok kisa veya cok uzun araliklarda turev guvenilmez.
    if dt < 1e-3 or dt > 0.2:
        _ff_last_pan = pan_angle
        _ff_last_tilt = tilt_angle
        return _publish_ff()

    turret_pan_rate = (pan_angle - _ff_last_pan) / dt
    turret_tilt_rate = (tilt_angle - _ff_last_tilt) / dt
    _ff_last_pan = pan_angle
    _ff_last_tilt = tilt_angle

    c_pan = settings.EGO_PX_PER_PAN_UNIT * settings.EGO_PAN_SIGN
    c_tilt = settings.EGO_PX_PER_TILT_UNIT * settings.EGO_TILT_SIGN

    if abs(c_pan) < 1e-6 or abs(c_tilt) < 1e-6:
        return 0.0, 0.0

    target_pan_rate = turret_pan_rate + lock_info["vx"] / c_pan
    target_tilt_rate = turret_tilt_rate + lock_info["vy"] / c_tilt

    # Filtre turda YALNIZCA BIR KEZ uygulanir. Iki kez uygulanirsa
    # etkin katsayi 2a - a^2 olur (0.12 -> 0.226) ve ayarlanan deger
    # tutmaz.
    alpha = settings.AIM_FF_SMOOTHING
    _ff_pan += alpha * (target_pan_rate - _ff_pan)
    _ff_tilt += alpha * (target_tilt_rate - _ff_tilt)

    return _publish_ff()

def _publish_ff():
    """Ileri besleme girdisini katalogda yayinlar ve dondurur.

    Tesnhis icin gereklidir: sabit hedefte bu deger sifira yakin
    kalmalidir. Sifirdan uzaklasiyorsa olcek veya isaret hatasi
    vardir.

    Returns:
        (pan, tilt) — analog girdi katkisi
    """
    pan_input = _ff_pan_input()
    tilt_input = _ff_tilt_input()

    state.PARAM_VALUES["control.ff_pan"] = round(pan_input, 3)
    state.PARAM_VALUES["control.ff_tilt"] = round(tilt_input, 3)

    return pan_input, tilt_input


def _rate_to_input(rate, max_rate_dps, sign):
    """Acisal hizi analog girdi oranina cevirir.

    SystemManager girdiyi soyle kullanir:
        gercek_hiz = girdi * max_rate_dps * AUTO_RATE_FACTOR * sign

    Bu fonksiyon o donusumun tersidir.

    Args:
        rate: Istenen acisal hiz (taret birimi/s)
        max_rate_dps: Eksenin azami hizi
        sign: Eksen yonu

    Returns:
        float — sinirlandirilmis analog girdi
    """
    span = max_rate_dps * settings.AUTO_RATE_FACTOR * sign

    if abs(span) < 1e-6:
        return 0.0

    value = rate / span
    limit = settings.AIM_FF_MAX

    return max(-limit, min(limit, value))


def _ff_pan_input():
    """Filtrelenmis pan ileri beslemesini girdi oranina cevirir."""
    return _rate_to_input(_ff_pan, settings.ANALOG_PAN_RATE_DPS,
                          settings.ANALOG_PAN_SIGN)


def _ff_tilt_input():
    """Filtrelenmis tilt ileri beslemesini girdi oranina cevirir."""
    return _rate_to_input(_ff_tilt, settings.ANALOG_TILT_RATE_DPS,
                          settings.ANALOG_TILT_SIGN)

def set_backend(backend):
    """Donanim surucusunu baglar.

    Surucu, set_analog_input(pan, tilt) imzasinda bir metoda sahip
    olmalidir.

    Args:
        backend: SystemManager benzeri nesne veya None
    """
    global _backend
    _backend = backend

    if backend is None:
        log.info("Taret surucusu ayrildi")
    else:
        log.info("Taret surucusu baglandi: %s", type(backend).__name__)

def get_backend():
    """Bagli SystemManager'i dondurur.

    Otonom ates icin gereklidir: tracking_loop nisan oturdugunda
    manager.fire() cagirir.

    Returns:
        SystemManager veya baglanmamissa None
    """
    return _backend  


def drive(aim_info, lock_info=None):
    """Nisan hatasindan analog girdi uretir ve gonderir.

    Girdi iki bilesenden olusur:
        Orantili   Hataya oranli. Hedefi merkeze getirir.
        Ileri besleme  Hedefin hizina esit. Kalici geride kalmayi
                       ortadan kaldirir.

    Args:
        aim_info: control.aiming.solve() ciktisi veya None
        lock_info: control.engagement.current() ciktisi veya None

    Returns:
        (pan, tilt) — gonderilen analog girdi (-1.0 ... 1.0)
    """
    _publish_lock(lock_info)

    if aim_info is None:
        _publish_error(None)
        _reset_feedforward()
        return _send(0.0, 0.0)

    _publish_error(aim_info)

    if lock_info is None or lock_info.get("state") != EngagementState.LOCKED:
        _reset_feedforward()
        return _send(0.0, 0.0)

    pan = _axis_input(aim_info["error_x"], settings.TURRET_PAN_SIGN)
    tilt = _axis_input(aim_info["error_y"], settings.TURRET_TILT_SIGN)

    ff_pan, ff_tilt = _feedforward(lock_info)

    pan = max(-1.0, min(1.0, pan + ff_pan))
    tilt = max(-1.0, min(1.0, tilt + ff_tilt))

    _log_change(pan, tilt, aim_info)
    return _send(pan, tilt)



def stop():
    """Hareketi durdurur. Mod gecislerinde ve kapanista cagrilir."""
    _send(0.0, 0.0)


def _axis_input(error_px, sign):
    """Piksel hatasini analog girdi oranina cevirir.

    Olu bant icinde sifir dondurulur. Disinda, hata FULL_INPUT_PX
    degerine oranlanir; bu deger ve uzerindeki hatalar tam girdi (1.0)
    uretir.

    Args:
        error_px: Isaretli piksel hatasi
        sign: Eksen yonu (+1 veya -1)

    Returns:
        float — -1.0 ... 1.0 arasi girdi
    """
    magnitude = abs(error_px)

    if magnitude < settings.AIM_DEAD_ZONE_PX:
        return 0.0

    span = settings.TURRET_FULL_INPUT_PX - settings.AIM_DEAD_ZONE_PX

    if span <= 0:
        ratio = 1.0
    else:
        ratio = min(1.0, (magnitude - settings.AIM_DEAD_ZONE_PX) / span)

    return ratio * (1.0 if error_px >= 0 else -1.0) * sign


def _send(pan, tilt):
    """Analog girdiyi katalog uzerinden iletir.

    Dogrudan SystemManager cagrilmaz: param_bridge her turda katalogdaki
    analog degerleri okuyup uyguladigi icin dogrudan cagri bir sonraki
    turda uzerine yazilir. Tek yazici ilkesi geregi otonom girdi de
    katalog uzerinden gecer.

    Args:
        pan: Yatay girdi (-1.0 ... 1.0)
        tilt: Dikey girdi (-1.0 ... 1.0)

    Returns:
        (pan, tilt)
    """
    state.PARAM_VALUES["motion.auto.pan"] = round(pan, 3)
    state.PARAM_VALUES["motion.auto.tilt"] = round(tilt, 3)
    return pan, tilt


def _log_change(pan, tilt, aim_info):
    """Belirgin degisimlerde loglar.

    Her dongude loglamak 50 Hz'de kullanilamaz cikti uretir.

    Args:
        pan: Yatay girdi
        tilt: Dikey girdi
        aim_info: Nisan cozumu
    """
    global _last_logged

    key = (round(pan, 1), round(tilt, 1))

    if key == _last_logged:
        return

    _last_logged = key

    log.debug("Taret: pan%+.2f tilt%+.2f (hata %.0f, %.0f px)",
              pan, tilt, aim_info["error_x"], aim_info["error_y"])

def _publish_lock(lock_info):
    """Angajman durumunu katalogda yayinlar.

    Performans olcumu bu degerleri kullanir. Kilit devri sayisi,
    ego-motion telafisinin ana olcutudur.
    """
    if lock_info is None:
        state.PARAM_VALUES["engage.track_id"] = -1
        state.PARAM_VALUES["engage.locked"] = 0
        return

    state.PARAM_VALUES["engage.track_id"] = lock_info.get("track_id", -1)
    state.PARAM_VALUES["engage.locked"] = int(
        lock_info.get("state") == EngagementState.LOCKED)
    state.PARAM_VALUES["engage.reacquires"] = lock_info.get("reacquires", 0)

def _publish_error(aim_info):
    """Nisan hatasini katalogda yayinlar.

    Ego-motion kalibrasyonu ve arayuz gostergesi bu degeri okur.
    Taret surulmedigi durumlarda da yayinlanir; aksi halde
    kalibrasyon sirasinda ornek toplanamaz.

    Args:
        aim_info: Nisan cozumu veya None
    """
    if aim_info is None:
        state.PARAM_VALUES["vision.aim_error_x"] = 0.0
        state.PARAM_VALUES["vision.aim_error_y"] = 0.0
        return

    state.PARAM_VALUES["vision.aim_error_x"] = round(aim_info["error_x"], 1)
    state.PARAM_VALUES["vision.aim_error_y"] = round(aim_info["error_y"], 1)