"""Otonom zincir teshis araci.

AUTO modunda hicbir sey hareket etmediginde zincirin HANGI halkasinda
koptugunu bulur. Sisteme yalnizca GET gonderir; hicbir sey degistirmez,
hicbir modul import etmez (config disinda).

Okunan zincir:

    system.mode              -> Mod gercekten AUTO oldu mu?
    system.link              -> Arduino baglantisi ayakta mi?
    vision.detection_count   -> Kamera bir sey goruyor mu?
    vision.inference_ms      -> Model gercekten calisiyor mu?
    motion.auto.pan / tilt   -> Otonom katman girdi URETIYOR mu?
    motion.analog.pan / tilt -> Kol girdisi (AUTO'da 0 olmali)
    weapon.armed             -> Ates yetkisi

Yorumlama:
    mode != 2                -> Mod gecisi reddedildi
    detection_count == 0     -> Kamera/model tarafi
    detection_count > 0 ama auto.pan/tilt == 0
                             -> Hedef secimi veya taret surme katmani
    auto.pan/tilt != 0 ama taret durgun
                             -> param_bridge veya SystemManager engelliyor

main.py AYRI bir terminalde calisir durumda olmalidir.
manual_gamepad.py ile AYNI ANDA calisabilir; ayri soket kullanir.

Kullanim:
    py -m tools.auto_probe
"""

import json
import socket
import time

from config import settings

# Izlenecek parametreler. GET yaniti bunlarin tamamini icermelidir;
# eksik anahtar, parametrenin PARAM_DEFS'e eklenmemis oldugunu gosterir.
WATCH_KEYS = (
    "system.mode",
    "system.link",
    "vision.detection_count",
    "vision.inference_ms",
    "motion.auto.pan",
    "motion.auto.tilt",
    "motion.analog.pan",
    "motion.analog.tilt",
    "weapon.armed",
    "system.pan_angle",
    "system.tilt_angle",
    "control.ff_pan",
    "control.ff_tilt",
)

MODE_NAMES = {0: "IDLE", 1: "MANUAL", 2: "AUTO", 3: "LOOP_DEMO", 4: "ESTOP"}

# Deger sarmalayici olarak kullanilabilecek alan adlari. Sunucu
# {"system.mode": 2} yerine {"system.mode": {"value": 2}} donebilir;
# her iki bicim de desteklenir.
VALUE_FIELDS = ("value", "val", "v", "Value")

POLL_HZ = 4.0
RECV_WAIT_S = 0.2


def _unwrap(raw):
    """Sarmalanmis degeri acar.

    Sunucu parametreleri {"value": 2, "unit": "", ...} gibi sozluk
    icinde donebilir. Bu durumda sayisal bicimlendirme calismaz;
    once ham deger cikarilir.

    Args:
        raw: Ham yanit degeri

    Returns:
        Sarmalayici cozulmus deger
    """
    if not isinstance(raw, dict):
        return raw
    for field in VALUE_FIELDS:
        if field in raw:
            return raw[field]
    # Tek elemanli sozlukse tek degeri al; degilse oldugu gibi birak.
    if len(raw) == 1:
        return next(iter(raw.values()))
    return raw


def _cell(value, width):
    """Herhangi bir tipi sabit genislikte metne cevirir.

    Sayisal bicim belirteci (:>6) sozluk veya None uzerinde patlar;
    bu yuzden once metne cevrilir.
    """
    return str(value).rjust(width)


def _format_mode(value):
    """Mod kodunu okunur hale getirir.

    Deger sayi degilse oldugu gibi gosterilir; bu durum katalogda
    modun metin olarak tutuldugunu ve param_bridge'deki sayisal
    karsilastirmanin HIC TUTMAYACAGINI gosterir.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        return f"{value!r}(SAYI DEGIL!)"
    return f"{value}({MODE_NAMES.get(value, '?')})"


def _truthy(value):
    """Sifirdan farkli sayisal deger mi?"""
    try:
        return abs(float(value)) > 1e-9
    except (TypeError, ValueError):
        return False


def _diagnose(values):
    """Okunan degerlere gore zincirin kopma noktasini tahmin eder.

    Args:
        values: parametre -> cozulmus deger sozlugu

    Returns:
        str — teshis satiri
    """
    mode = values.get("system.mode")
    link = values.get("system.link")
    det = values.get("vision.detection_count")

    if mode is None:
        return "system.mode okunamadi - komut sunucusu yanit vermiyor"

    if isinstance(mode, bool) or not isinstance(mode, int):
        return "system.mode SAYI DEGIL - param_bridge karsilastirmasi tutmaz"

    if mode != 2:
        return f"Mod AUTO degil ({MODE_NAMES.get(mode, mode)}) - gecis reddedildi"

    if link in (0, False, "0"):
        return "Arduino baglantisi YOK - komutlar hicbir yere gitmiyor"

    if "motion.auto.pan" not in values:
        return "motion.auto.pan katalogda YOK - PARAM_DEFS'e eklenmemis"

    if not _truthy(det):
        return "Tespit yok - kamera veya model tarafi (zincirin ustu)"

    if not _truthy(values.get("motion.auto.pan")) and \
       not _truthy(values.get("motion.auto.tilt")):
        return ("Tespit VAR ama otonom girdi 0 - hedef secimi veya "
                "taret surme katmani uretmiyor")

    return "Otonom girdi URETILIYOR - kopma param_bridge/SystemManager altinda"


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(RECV_WAIT_S)
    addr = (settings.COMMAND_UDP_HOST, settings.COMMAND_UDP_PORT)

    print(__doc__)
    print("Izleniyor... Ctrl+C ile cik.\n")

    msg_id = 0
    period = 1.0 / POLL_HZ
    last_diag = None
    raw_dumped = False

    try:
        while True:
            msg_id += 1
            packet = {"Method": "GET", "messageID": msg_id}
            packet.update({key: "?" for key in WATCH_KEYS})
            sock.sendto(json.dumps(packet).encode(), addr)

            try:
                data, _ = sock.recvfrom(settings.UDP_BUFFER_SIZE)
            except (socket.timeout, OSError):
                print("  yanit yok - main.py calisiyor mu?")
                time.sleep(period)
                continue

            try:
                reply = json.loads(data.decode(errors="replace"))
            except json.JSONDecodeError:
                print("  cozulemeyen yanit:", data[:300])
                time.sleep(period)
                continue

            # Ilk yanitin ham hali bir kez basilir. Yanit bicimi
            # sunucuya gore degistigi icin, cozumleme hatalarinda
            # gercek bicimi gormek gerekir.
            if not raw_dumped:
                raw_dumped = True
                print("--- HAM YANIT (ilk paket) ---")
                print(json.dumps(reply, ensure_ascii=False, indent=2)[:1200])
                print("--- HAM YANIT SONU ---\n")

            # Yanit formati sunucuya gore degisebilir; hem duz hem de
            # sarmalanmis ("Params"/"data") yapiyi dener.
            container = reply
            for wrapper in ("Params", "params", "data", "Data"):
                if isinstance(reply.get(wrapper), dict):
                    container = reply[wrapper]
                    break

            values = {k: _unwrap(v) for k, v in container.items()}

            missing = [k for k in WATCH_KEYS if k not in values]

            print(
                "mode={} link={} det={} inf={} aci=({},{}) "
                "auto=({},{}) analog=({},{}) armed={}".format(
                    _format_mode(values.get("system.mode")).ljust(16),
                    _cell(values.get("system.link"), 5),
                    _cell(values.get("vision.detection_count"), 3),
                    _cell(values.get("vision.inference_ms"), 6),
                    _cell(values.get("system.pan_angle"), 6),
                    _cell(values.get("system.tilt_angle"), 6),
                    _cell(values.get("motion.auto.pan"), 6),
                    _cell(values.get("motion.auto.tilt"), 6),
                    _cell(values.get("motion.analog.pan"), 6),
                    _cell(values.get("motion.analog.tilt"), 6),
                    values.get("weapon.armed"),
                )
            )

            if missing:
                print("  KATALOGDA YOK:", ", ".join(missing))

            diag = _diagnose(values)
            if diag != last_diag:
                print("  >>", diag)
                last_diag = diag

            time.sleep(period)

    except KeyboardInterrupt:
        print("\nCikildi.")
    finally:
        sock.close()


if __name__ == "__main__":
    main()