"""UDP JSON protokol mesaj isleyicisi.

Gelen GET/SET mesajlarini dogrular, parametre katalogu uzerinde
okuma/yazma yapar ve cevap mesajini uretir. Ag katmanindan bagimsizdir;
sozluk alir, sozluk dondurur.

Tetikleyici parametreler (trigger) saklanmaz, core.state.COMMAND_QUEUE'ya
alinir. Kuyrugu tuketmek bu modulun sorumlulugunda degildir.

Protokol tanimi: docs/protocol_spec.md
"""

import logging
import time
from queue import Full

from core import state
from core.enums import Access, ErrCode, Method

log = logging.getLogger("dispatcher")

RESERVED_KEYS = ("Method", "messageID")


# ---------------------------------------------------------------------------
# Mesaj yonlendirme
# ---------------------------------------------------------------------------

def handle_message(message):
    """Mesaji Method alanina gore ilgili isleyiciye yonlendirir.

    Method alani buyuk/kucuk harf duyarsiz karsilastirilir; "GET",
    "get" ve "Get" ayni sekilde islenir.

    Args:
        message: Cozulmus JSON sozlugu

    Returns:
        Cevap sozlugu. Method taninmazsa ERRRSP (status=1).
    """
    raw_method = message.get("Method")
    message_id = message.get("messageID")

    method = raw_method.upper() if isinstance(raw_method, str) else None

    log.debug("Gelen mesaj: %s", message)

    if method == Method.GET:
        return handle_get(message, message_id)

    if method == Method.SET:
        return handle_set(message, message_id)

    log.warning("Taninmayan Method: %r (messageID=%s)", raw_method, message_id)
    return {
        "Method": Method.ERR_RSP,
        "messageID": message_id,
        "status": ErrCode.UNDEFINED_METHOD_TYPE.value,
    }


def extract_variables(message):
    """Mesajdan rezerve alanlari cikarip degiskenleri dondurur.

    Args:
        message: Cozulmus JSON sozlugu

    Returns:
        Yalnizca parametre adi/deger ciftlerini iceren sozluk
    """
    return {k: v for k, v in message.items() if k not in RESERVED_KEYS}


# ---------------------------------------------------------------------------
# GET
# ---------------------------------------------------------------------------

def handle_get(message, message_id):
    """GET mesajini isler, her degisken icin deger okur.

    Args:
        message: Cozulmus JSON sozlugu
        message_id: Cevapta geri yazilacak istek numarasi

    Returns:
        GETRSP sozlugu. Her degisken icin {"status", "value"} nesnesi.
    """
    variables = extract_variables(message)

    response = {
        "Method": Method.GET_RSP,
        "messageID": message_id,
    }

    for name in variables:
        response[name] = get_one(name)

    log.debug("GETRSP hazir: messageID=%s degisken=%d",
              message_id, len(variables))
    return response


def get_one(name):
    """Tek bir parametrenin degerini okur.

    Args:
        name: Parametre adi

    Returns:
        {"status": int, "value": Any}
        status 2 = parametre tanimsiz
        status 5 = erisim tipi okumaya izin vermiyor (WRO)
        status 0 disindaysa value None
    """
    if name not in state.PARAM_DEFS:
        log.warning("GET reddedildi: %r tanimsiz parametre", name)
        return {"status": ErrCode.UNDEFINED_KEY.value, "value": None}

    definition = state.PARAM_DEFS[name]

    if definition["access"] == Access.WRO:
        log.warning("GET reddedildi: %s access=%s", name, definition["access"])
        return {"status": ErrCode.ACCESS_TYPE_ERROR.value, "value": None}

    log.debug("GET %s = %r", name, state.PARAM_VALUES[name])
    return {"status": ErrCode.SUCCESS.value, "value": state.PARAM_VALUES[name]}


# ---------------------------------------------------------------------------
# SET
# ---------------------------------------------------------------------------

def handle_set(message, message_id):
    """SET mesajini isler, her degiskeni dogrulayip yazar.

    Args:
        message: Cozulmus JSON sozlugu
        message_id: Cevapta geri yazilacak istek numarasi

    Returns:
        SETRSP sozlugu. Her degisken icin {"status", "value"} nesnesi.
    """
    variables = extract_variables(message)

    response = {
        "Method": Method.SET_RSP,
        "messageID": message_id,
    }

    for name, value in variables.items():
        response[name] = set_one(name, value)

    log.debug("SETRSP hazir: messageID=%s degisken=%d",
              message_id, len(variables))
    return response


def set_one(name, value):
    """Tek bir parametreyi dogrular ve yazar.

    Dogrulama sirasi: katalogda var mi, erisim izni, null kontrolu,
    tip, sinir. Ilk basarisiz kontrol sonucu dondurur.

    Tetikleyici parametrelerde (trigger) deger saklanmaz; komut
    kuyruguna alinir ve value 0 dondurulur.

    Args:
        name: Parametre adi
        value: Yazilacak deger

    Returns:
        {"status": int, "value": Any}
        status 0 = basarili, value sistemde yerlesen deger
        status 2 = parametre tanimsiz
        status 4 = tip uyusmuyor
        status 5 = erisim tipi yazmaya izin vermiyor (RO)
        status 6 = deger null
        status 8 = sinir disi
        status 9 = komut kuyrugu dolu
    """
    if name not in state.PARAM_DEFS:
        log.warning("SET reddedildi: %r tanimsiz parametre", name)
        return {"status": ErrCode.UNDEFINED_KEY.value, "value": None}

    definition = state.PARAM_DEFS[name]

    if definition["access"] == Access.RO:
        log.warning("SET reddedildi: %s access=%s", name, definition["access"])
        return {"status": ErrCode.ACCESS_TYPE_ERROR.value, "value": None}

    if value is None:
        log.warning("SET reddedildi: %s deger bos", name)
        return {"status": ErrCode.INVALID_VALUE.value, "value": None}

    if not isinstance(value, definition["type"]):
        log.warning("SET reddedildi: %s tip hatasi, beklenen=%s gelen=%s deger=%r",
                    name, definition["type"].__name__,
                    type(value).__name__, value)
        return {"status": ErrCode.VALUE_TYPE_ERROR.value, "value": None}

    if value < definition["min"] or value > definition["max"]:
        log.warning("SET reddedildi: %s sinir disi, deger=%r aralik=[%s, %s]",
                    name, value, definition["min"], definition["max"])
        return {"status": ErrCode.VALUE_RANGE_ERROR.value, "value": None}

    if definition.get("trigger"):
        return enqueue_trigger(name, value)

    state.PARAM_VALUES[name] = value

    log.info("SET %s = %r", name, value)
    return {"status": ErrCode.SUCCESS.value, "value": state.PARAM_VALUES[name]}


def enqueue_trigger(name, value):
    """Tetikleyici komutu isleme kuyruguna alir.

    Kuyruk dolu ise komut atilir ve INTERNAL_ERROR dondurulur.
    Kuyrugu tuketmek kontrol dongusunun sorumlulugundadir.

    Args:
        name: Tetikleyici parametre adi
        value: Komut degeri

    Returns:
        {"status": int, "value": int} — basarili ise value her zaman 0
    """
    try:
        state.COMMAND_QUEUE.put_nowait({
            "action": name,
            "value": value,
            "ts": time.time(),
        })
    except Full:
        log.error("Komut kuyrugu dolu (%d), %s atildi",
                  state.COMMAND_QUEUE.qsize(), name)
        return {"status": ErrCode.INTERNAL_ERROR.value, "value": None}

    log.info("TRIGGER %s = %r kuyruga alindi (bekleyen=%d)",
             name, value, state.COMMAND_QUEUE.qsize())
    return {"status": ErrCode.SUCCESS.value, "value": 0}