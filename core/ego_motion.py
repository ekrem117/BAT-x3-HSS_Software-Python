"""Kamera hareketi (ego-motion) telafisi.

Kamera taretin uzerindedir ve taretle birlikte doner. Bu yuzden piksel
konumu MUTLAK bir olcum degildir: taret 5 birim donunce hedef hic
kimildamasa bile piksel merkezi kayar.

Sonuc: piksel uzayinda tutulan her konum tahmini, taret her donduğunde
gecersizlesir. Takipci hedefi bekledigi yerde bulamaz, izi duşurur ve
yeni bir ID atar. Angajman katmani da yeniden eslestirme yaparken
yanlis yere bakar.

Bu modul, iki olcum arasinda taretin ne kadar dondugunu piksel
kaymasina cevirir. Kayma tahmin EDILMEZ, HESAPLANIR: taretin acisi
zaten bilinmektedir. Bu yontem gorsel akistan (sparseOptFlow) farkli
olarak arka plan dokusuna bagimli degildir; gokyuzune karsi da calisir.

Bagimliligi yoktur: yalnizca config/settings okur. Donanimsiz ve
kamerasiz test edilebilir.

KALIBRASYON ZORUNLU:
    settings.EGO_PX_PER_PAN_UNIT ve EGO_PX_PER_TILT_UNIT degerleri
    olculmeden bu modul dogru calismaz. Olcum yontemi settings
    icindeki aciklamada anlatilmistir.
"""

import logging

from config import settings

log = logging.getLogger("ego_motion")


def pixel_shift(pan_from, tilt_from, pan_to, tilt_to):
    """Iki taret acisi arasindaki piksel kaymasini hesaplar.

    Doner deger, SABIT bir hedefin goruntudeki konumunun ne kadar
    kayacagini bildirir. Taret saga donerse sahne sola kayar; bu
    nedenle isaret terstir ve EGO_*_SIGN ile ayarlanir.

    Args:
        pan_from: Onceki pan acisi (taret birimi)
        tilt_from: Onceki tilt acisi (taret birimi)
        pan_to: Simdiki pan acisi
        tilt_to: Simdiki tilt acisi

    Returns:
        (dx, dy) — piksel kaymasi. Telafi icin olculen konumdan
        CIKARILIR, tahmin edilen konuma EKLENIR.
    """
    d_pan = pan_to - pan_from
    d_tilt = tilt_to - tilt_from

    dx = -d_pan * settings.EGO_PX_PER_PAN_UNIT * settings.EGO_PAN_SIGN
    dy = -d_tilt * settings.EGO_PX_PER_TILT_UNIT * settings.EGO_TILT_SIGN

    return dx, dy


def compensate_position(position, pan_from, tilt_from, pan_to, tilt_to):
    """Piksel konumunu taret hareketine gore kaydirir.

    Sabit bir hedefin, taret dondukten sonra goruntude nerede
    gorunecegini hesaplar.

    Args:
        position: (x, y) piksel konumu
        pan_from/tilt_from: Konumun olculdugu andaki taret acisi
        pan_to/tilt_to: Simdiki taret acisi

    Returns:
        (x, y) — kaydirilmis konum
    """
    if not settings.EGO_MOTION_ENABLED:
        return position

    dx, dy = pixel_shift(pan_from, tilt_from, pan_to, tilt_to)
    return position[0] + dx, position[1] + dy


def angular_velocity_px(pan_rate, tilt_rate):
    """Taretin acisal hizini piksel hizina cevirir.

    Olculen piksel hizindan CIKARILDIGINDA hedefin gercek piksel
    hizi kalir. Taret donerken sabit bir hedef, olcumde yuksek hizli
    gorunur; bu duzeltme olmadan Kalman sahte bir hiz ogrenir.

    Args:
        pan_rate: Pan acisal hizi (taret birimi/saniye)
        tilt_rate: Tilt acisal hizi (taret birimi/saniye)

    Returns:
        (vx, vy) — piksel/saniye
    """
    if not settings.EGO_MOTION_ENABLED:
        return 0.0, 0.0

    return pixel_shift(0.0, 0.0, pan_rate, tilt_rate)