"""Ego-motion olcek kalibrasyonu.

EGO_PX_PER_PAN_UNIT ve EGO_PX_PER_TILT_UNIT degerlerini olcerek
belirler. Elle piksel okumaya gerek yoktur.

CALISMA MANTIGI
    Taret hareket ederken SABIT bir hedefin nisan hatasi degisir.
    Degisim tamamen kamera hareketinden kaynaklanir. Arac, taret
    acisi ile nisan hatasi ciftlerini toplar ve en kucuk kareler ile
    egimi bulur:

        hata_x = a * pan + b * tilt + sabit
        hata_y = d * pan + e * tilt + sabit

    a ve e katsayilari aradigimiz olceklerdir. b ve d capraz
    terimlerdir; kamera duzgun hizalanmissa kucuk kalmalidir.

ON KOSUL
    Katalogda su iki parametre bulunmalidir (patch dosyasina bakin):
        vision.aim_error_x
        vision.aim_error_y

KULLANIM
    1. main.py calisir durumda olsun
    2. SABIT bir hedef kadraja alinsin ve kilitlensin
    3. py -m tools.ego_calibrate
    4. Arac sayarken MANUAL modda taret YAVASCA gezdirilsin:
       once saga-sola, sonra yukari-asagi. Hedef kadraj disina
       cikmasin ve kilit dusmesin.
    5. Arac sonucu ve settings'e yazilacak satirlari basar

UYARI
    Hedef HAREKETLI olmamalidir. Hareketli hedefle olcum bozulur.
"""

import json
import math
import socket
import sys
import time

from config import settings

WATCH_KEYS = (
    "system.pan_angle",
    "system.tilt_angle",
    "vision.aim_error_x",
    "vision.aim_error_y",
    "vision.detection_count",
)

SAMPLE_HZ = 10.0
TARGET_SAMPLES = 200
RECV_WAIT_S = 0.3

# Bu araligin altinda kalan aci degisimi olcum icin yetersizdir;
# gurultu egimi bozar.
MIN_PAN_SPAN = 8.0

# Bir eksen bu araligin altinda kaldiysa bilinmeyen olarak kullanilmaz.
_MIN_SPAN_FOR_FIT = 2.0
MIN_TILT_SPAN = 8.0


def _unwrap(raw):
    """Sarmalanmis GET degerini acar."""
    if not isinstance(raw, dict):
        return raw
    for field in ("value", "val", "v", "Value"):
        if field in raw:
            return raw[field]
    return None


def _solve(samples):
    """Iki degiskenli en kucuk kareler cozumu.

    Bir eksen hic degismediyse (varyansi sifir) o eksen sistemden
    CIKARILIR ve tek degiskenli cozume dusulur. Aksi halde normal
    denklem matrisi tekil olur ve cozucu, saglam olan diger eksenin
    verisini de kaybederek sifir dondurur.

    Args:
        samples: [(pan, tilt, deger), ...]

    Returns:
        (a, b, c) — deger = a*pan + b*tilt + c
    """
    n = len(samples)
    if n < 3:
        return 0.0, 0.0, 0.0

    pans = [s[0] for s in samples]
    tilts = [s[1] for s in samples]

    pan_span = max(pans) - min(pans)
    tilt_span = max(tilts) - min(tilts)

    # Degismeyen eksen bilinmeyen olarak kullanilamaz.
    use_pan = pan_span > _MIN_SPAN_FOR_FIT
    use_tilt = tilt_span > _MIN_SPAN_FOR_FIT

    if not use_pan and not use_tilt:
        return 0.0, 0.0, 0.0

    if use_pan and use_tilt:
        return _solve_two(samples)

    if use_pan:
        slope, offset = _solve_one([(s[0], s[2]) for s in samples])
        return slope, 0.0, offset

    slope, offset = _solve_one([(s[1], s[2]) for s in samples])
    return 0.0, slope, offset


def _solve_one(pairs):
    """Tek degiskenli dogrusal regresyon.

    Args:
        pairs: [(x, y), ...]

    Returns:
        (egim, sabit)
    """
    n = float(len(pairs))
    s_x = sum(p[0] for p in pairs)
    s_y = sum(p[1] for p in pairs)
    s_xx = sum(p[0] * p[0] for p in pairs)
    s_xy = sum(p[0] * p[1] for p in pairs)

    denom = n * s_xx - s_x * s_x
    if abs(denom) < 1e-9:
        return 0.0, 0.0

    slope = (n * s_xy - s_x * s_y) / denom
    offset = (s_y - slope * s_x) / n
    return slope, offset


def _solve_two(samples):
    """Iki degiskenli normal denklem cozumu.

    Args:
        samples: [(pan, tilt, deger), ...]

    Returns:
        (a, b, c)
    """
    n = len(samples)

    s_pp = s_pt = s_tt = s_p = s_t = 0.0
    s_pv = s_tv = s_v = 0.0

    for pan, tilt, value in samples:
        s_pp += pan * pan
        s_pt += pan * tilt
        s_tt += tilt * tilt
        s_p += pan
        s_t += tilt
        s_pv += pan * value
        s_tv += tilt * value
        s_v += value

    matrix = [
        [s_pp, s_pt, s_p, s_pv],
        [s_pt, s_tt, s_t, s_tv],
        [s_p, s_t, float(n), s_v],
    ]

    # Kismi pivotlamali Gauss eliminasyonu
    for col in range(3):
        pivot = max(range(col, 3), key=lambda r: abs(matrix[r][col]))
        if abs(matrix[pivot][col]) < 1e-9:
            return 0.0, 0.0, 0.0
        matrix[col], matrix[pivot] = matrix[pivot], matrix[col]

        for row in range(3):
            if row == col:
                continue
            factor = matrix[row][col] / matrix[col][col]
            for k in range(col, 4):
                matrix[row][k] -= factor * matrix[col][k]

    return tuple(matrix[i][3] / matrix[i][i] for i in range(3))


def _report(samples):
    """Toplanan orneklerden olcek ve isaret cikarir."""
    pans = [s[0] for s in samples]
    tilts = [s[1] for s in samples]

    pan_span = max(pans) - min(pans)
    tilt_span = max(tilts) - min(tilts)

    print("\n" + "=" * 60)
    print("Ornek sayisi : {}".format(len(samples)))
    print("Pan araligi  : {:.1f} birim".format(pan_span))
    print("Tilt araligi : {:.1f} birim".format(tilt_span))

    if pan_span < MIN_PAN_SPAN:
        print("\nUYARI: Pan araligi dar ({:.1f} birim). Pan olcegi"
              " guvenilmez.".format(pan_span))
    if tilt_span < MIN_TILT_SPAN:
        print("\nUYARI: Tilt araligi dar ({:.1f} birim). Tilt olcegi"
              " guvenilmez.".format(tilt_span))

    ax, bx, _ = _solve([(s[0], s[1], s[2]) for s in samples])
    ay, by, _ = _solve([(s[0], s[1], s[3]) for s in samples])

    print("\nEgimler (piksel / taret birimi)")
    print("  hata_x / pan  : {:+8.2f}   <- pan olcegi".format(ax))
    print("  hata_x / tilt : {:+8.2f}   (capraz, kucuk olmali)".format(bx))
    print("  hata_y / pan  : {:+8.2f}   (capraz, kucuk olmali)".format(ay))
    print("  hata_y / tilt : {:+8.2f}   <- tilt olcegi".format(by))

    # compensate_position icinde: dx = -d_pan * PX * SIGN
    # Gozlenen kayma  : dx = egim * d_pan
    # Esitlik icin    : PX * SIGN = -egim
    pan_scale = abs(ax)
    tilt_scale = abs(by)
    pan_sign = -1.0 if ax > 0 else 1.0
    tilt_sign = -1.0 if by > 0 else 1.0

    print("\n" + "=" * 60)
    print("config/settings.py icine yazilacak:\n")
    print("EGO_PX_PER_PAN_UNIT = {:.1f}".format(pan_scale))
    print("EGO_PX_PER_TILT_UNIT = {:.1f}".format(tilt_scale))
    print("EGO_PAN_SIGN = {:.1f}".format(pan_sign))
    print("EGO_TILT_SIGN = {:.1f}".format(tilt_sign))
    print("=" * 60)

    if pan_span < MIN_PAN_SPAN:
        print("\nDIKKAT: Pan olculemedi. Mevcut EGO_PX_PER_PAN_UNIT")
        print("        degerini KORUYUN, 0.0 yazmayin.")
    if tilt_span < MIN_TILT_SPAN:
        print("\nDIKKAT: Tilt olculemedi. Mevcut EGO_PX_PER_TILT_UNIT")
        print("        degerini KORUYUN, 0.0 yazmayin.")

    cross = max(abs(bx), abs(ay))
    main = max(pan_scale, tilt_scale)
    if main > 0 and cross / main > 0.25:
        print("\nUYARI: Capraz terimler buyuk. Kamera taret eksenlerine")
        print("       gore egik monte edilmis olabilir; veya hedef")
        print("       olcum sirasinda hareket etti.")


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(RECV_WAIT_S)
    addr = (settings.COMMAND_UDP_HOST, settings.COMMAND_UDP_PORT)

    print(__doc__)
    print("Toplama basliyor. MANUAL modda tareti yavasca gezdirin.")
    print("Ctrl+C ile erken bitirebilirsiniz.\n")

    samples = []
    msg_id = 0
    period = 1.0 / SAMPLE_HZ
    missing_warned = False

    try:
        while len(samples) < TARGET_SAMPLES:
            msg_id += 1
            packet = {"Method": "GET", "messageID": msg_id}
            packet.update({key: "?" for key in WATCH_KEYS})
            sock.sendto(json.dumps(packet).encode(), addr)

            try:
                data, _ = sock.recvfrom(settings.UDP_BUFFER_SIZE)
                reply = json.loads(data.decode(errors="replace"))
            except (socket.timeout, OSError, json.JSONDecodeError):
                print("  yanit yok - main.py calisiyor mu?")
                time.sleep(period)
                continue

            values = {k: _unwrap(v) for k, v in reply.items()}

            if values.get("vision.aim_error_x") is None:
                if not missing_warned:
                    missing_warned = True
                    print("  vision.aim_error_x katalogda YOK veya bos.")
                    print("  Patch uygulanmis mi? Hedef kilitli mi?")
                time.sleep(period)
                continue

            pan = values.get("system.pan_angle")
            tilt = values.get("system.tilt_angle")
            ex = values.get("vision.aim_error_x")
            ey = values.get("vision.aim_error_y")

            if None in (pan, tilt, ex, ey):
                time.sleep(period)
                continue

            samples.append((float(pan), float(tilt), float(ex), float(ey)))

            if len(samples) % 20 == 0:
                print("  {} / {}  aci=({:.1f}, {:.1f})  hata=({:.0f}, {:.0f})"
                      .format(len(samples), TARGET_SAMPLES, pan, tilt, ex, ey))

            time.sleep(period)

    except KeyboardInterrupt:
        print("\nToplama durduruldu.")
    finally:
        sock.close()

    if len(samples) < 20:
        print("\nYetersiz ornek ({}). Hedef kilitli degil olabilir."
              .format(len(samples)))
        return

    _report(samples)


if __name__ == "__main__":
    main()