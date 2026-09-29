"""Protokol durum kodlari ve siniflandirma sabitleri.

Durum kodlari UDP_Protocol.docx Tablo 2'den alinmistir; telde sayisal
deger gonderilir (ErrCode.X.value).

Hicbir proje modulunu import etmez.
"""

from enum import Enum


class ErrCode(Enum):
    """Protokol durum ve hata kodlari.

    Kod 0 basariyi, digerleri hata durumlarini temsil eder.
    """

    SUCCESS = 0
    UNDEFINED_METHOD_TYPE = 1
    UNDEFINED_KEY = 2
    MESSAGE_FORMAT_ERROR = 3
    VALUE_TYPE_ERROR = 4
    ACCESS_TYPE_ERROR = 5
    INVALID_VALUE = 6
    VALUE_LENGTH_ERROR = 7
    VALUE_RANGE_ERROR = 8
    INTERNAL_ERROR = 9
    READ_ERROR = 10
    WRITE_ERROR = 11


class TargetClass:
    """Hedef sinif kodlari. Tespit paketinde 'cls' alani.

    Kodlar YOLO modelinin egitim sirasiyla birebir aynidir:
        ['drone', 'f16', 'fuze', 'heli', 'balon']

    Bu esitlik bilinclidir; model indeksi ile protokol kodu arasinda
    donusum gerektirmez. Farkli sirada egitilmis bir model kullanilirsa
    settings.MODEL_CLASS_MAP guncellenir.
    """

    DRONE = 0
    F16 = 1
    MISSILE = 2
    HELICOPTER = 3
    BALLOON = 4


CLASS_NAMES = {
    TargetClass.DRONE: "drone",
    TargetClass.F16: "f16",
    TargetClass.MISSILE: "fuze",
    TargetClass.HELICOPTER: "heli",
    TargetClass.BALLOON: "balon",
}


class Team:
    """Dost/dusman kodlari. Tespit paketinde 'team' alani.

    UNKNOWN sinifindaki hedeflere angajman yapilmaz.
    """

    FRIEND = 0
    ENEMY = 1
    UNKNOWN = 2


class Access:
    """Parametre erisim tipleri.

    RO   Yalnizca okunur. SET denemesi ACCESS_TYPE_ERROR dondurur.
    RW   Okunur ve yazilir.
    WRO  Yalnizca yazilir. GET denemesi ACCESS_TYPE_ERROR dondurur.
         Kritik ve tetikleyici parametreler icin kullanilir.
    """

    RO = "RO"
    RW = "RW"
    WRO = "WRO"


class Method:
    """Protokol mesaj tipleri."""

    GET = "GET"
    SET = "SET"
    GET_RSP = "GETRSP"
    SET_RSP = "SETRSP"
    ERR_RSP = "ERRRSP"


class SystemMode:
    """Sistem calisma modlari. "system.mode" parametresi bu degerlerden
    birini tasir.

    Mod gecis kurallari (hangi moddan hangisine gecilebilir, gecerken
    ne sifirlanir) burada DEGIL, control/system_manager.py icindedir.
    Bu sinif yalnizca ortak sozluk saglar, kural icermez.

    IDLE        Bosta, guvenli. Mod gecislerinin ugrak noktasi.
    MANUAL      Operator kontrolu (Asama-1).
    AUTO        Otonom hedef takibi.
    LOOP_DEMO   Sunum modu, sinirlar arasi dongu.
    ESTOP       Acil durdur etkin.
    """

    IDLE = "IDLE"
    MANUAL = "MANUAL"
    AUTO = "AUTO"
    LOOP_DEMO = "LOOP_DEMO"
    ESTOP = "ESTOP"


class LinkState:
    """Arduino seri baglantisinin durumu. "system.link" parametresi icin.

    Yalnizca hardware/arduino_link.py tarafindan uretilir; arayuz veya
    baska hicbir katman bu degeri yazmaz (RO parametre).

    DISCONNECTED   Port hic acilmadi veya kapandi.
    CONNECTED      Port acik, son yazma/heartbeat basarili.
    TIMEOUT        Port acik ama Arduino watchdog suresinde yanit vermedi.
    """

    DISCONNECTED = "DISCONNECTED"
    CONNECTED = "CONNECTED"
    TIMEOUT = "TIMEOUT"


class EngagementState:
    """Angajman durum makinesi durumlari.

    IDLE        Hedef secilmedi
    LOCKED      Hedef kilitli ve goruluyor
    LOST        Iz dustu, tahmin ediliyor ve yeniden eslestirme deneniyor
    DESTROYED   Imha teyidi alindi
    ABANDONED   Tolerans doldu veya atis siniri asildi
    """

    IDLE = 0
    LOCKED = 1
    LOST = 2
    DESTROYED = 3
    ABANDONED = 4


ENGAGEMENT_STATE_NAMES = {
    EngagementState.IDLE: "IDLE",
    EngagementState.LOCKED: "LOCKED",
    EngagementState.LOST: "LOST",
    EngagementState.DESTROYED: "DESTROYED",
    EngagementState.ABANDONED: "ABANDONED",
}