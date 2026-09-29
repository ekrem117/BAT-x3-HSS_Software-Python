"""UDP video ve tespit test alicisi.

Video (5007) ve tespit (5008) yayinlarini ayni anda dinler, kutulari
kare uzerine cizerek gosterir.

C# alici gelistirilmeden once sistemi dogrulamak ve C# tarafina referans
olmak icin kullanilir. Kare-kutu eslestirmesi frame_id uzerinden yapilir.

Kullanim (proje kokunden):
    python tools/test_receiver.py
"""

import json
import logging
import socket
import struct
import sys
import threading
import time
from collections import deque
from pathlib import Path

import cv2
import numpy as np


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings  # noqa: E402
from core.enums import CLASS_NAMES, TargetClass, Team  # noqa: E402
from vision import ballistics, ranging  # noqa: E402

log = logging.getLogger("test_receiver")

HEADER_SIZE = struct.calcsize(settings.VIDEO_HEADER_FORMAT)
FRAME_BUFFER_DEPTH = 10

# BGR renk kodlari
TEAM_COLORS = {
    Team.FRIEND: (224, 163, 0),      # camgobegi
    Team.ENEMY: (10, 10, 245),       # kirmizi
    Team.UNKNOWN: (0, 220, 255),     # sari
}

TEAM_NAMES = {
    Team.FRIEND: "DOST",
    Team.ENEMY: "DUSMAN",
    Team.UNKNOWN: "?",
}

# --- Paylasilan durum ------------------------------------------------------

_lock = threading.Lock()
_detection_history = deque(maxlen=FRAME_BUFFER_DEPTH)
_lock_info = None
_aim_info = None
_running = True


# --- Tespit alicisi --------------------------------------------------------

def _detection_loop():
    """Tespit paketlerini dinler ve gecmis tamponuna yazar."""
    global _lock_info, _aim_info

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((settings.TARGET_IP, settings.DETECTION_PORT))
    sock.settimeout(1.0)

    log.info("Tespit dinleniyor: %s:%d",
             settings.TARGET_IP, settings.DETECTION_PORT)

    while _running:
        try:
            data, _ = sock.recvfrom(settings.UDP_BUFFER_SIZE)
        except socket.timeout:
            continue
        except OSError:
            break

        try:
            payload = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            log.warning("Tespit paketi cozulemedi: %s", e)
            continue

        with _lock:
            _detection_history.append(
                (payload.get("frame_id", 0), payload.get("detections", []))
            )
            _lock_info = payload.get("lock")
            _aim_info = payload.get("aim")

    sock.close()


def _find_detections(frame_id):
    """Verilen kareye ait tespitleri bulur.

    Tam eslesme yoksa en yakin onceki kareyi kullanir; kutular bir kare
    geride kalabilir ancak hic gosterilmemesinden iyidir.

    Args:
        frame_id: Aranan kare numarasi

    Returns:
        (detections, matched) — matched: tam eslesme bulundu mu
    """
    with _lock:
        history = list(_detection_history)

    for fid, dets in reversed(history):
        if fid == frame_id:
            return dets, True

    for fid, dets in reversed(history):
        if fid < frame_id:
            return dets, False

    return [], False

def get_lock_info():
    """Son alinan angajman bilgisini dondurur.

    Returns:
        dict veya aktif angajman yoksa None
    """
    with _lock:
        return _lock_info


def get_aim_info():
    """Son alinan nisan cozumunu dondurur.

    Returns:
        dict veya nisan cozumu yoksa None
    """
    with _lock:
        return _aim_info


# --- Cizim -----------------------------------------------------------------

def draw_detections(frame, detections, source_width, source_height):
    """Tespit kutularini kare uzerine cizer.

    Koordinatlar kaynak cozunurluktedir; yayin cozunurluguna
    olceklenerek cizilir.

    Args:
        frame: BGR NumPy dizisi (yerinde degistirilir)
        detections: Tespit sozlukleri listesi
        source_width: Tespitlerin uretildigi kare genisligi
        source_height: Tespitlerin uretildigi kare yuksekligi
    """
    centers = {}

    scale_x = frame.shape[1] / source_width
    scale_y = frame.shape[0] / source_height

    lock_info = get_lock_info()
    locked_id = lock_info["track_id"] if lock_info else None

    for det in detections:
        x = int(det["x"] * scale_x)
        y = int(det["y"] * scale_y)
        w = int(det["w"] * scale_x)
        h = int(det["h"] * scale_y)
        team = det.get("team", Team.UNKNOWN)
        color = TEAM_COLORS.get(team, (200, 200, 200))

        centers[det["id"]] = (x + w // 2, y + h // 2)

        det_id = det.get("id", -1)
        id_text = f"#{det_id}" if det_id >= 0 else "#?"

        is_locked = det_id == locked_id
        if is_locked:
            thickness = 4
        elif det.get("predicted"):
            thickness = 1
        else:
            thickness = 2

        cv2.rectangle(frame, (x, y), (x + w, y + h), color, thickness)

        cls_name = CLASS_NAMES.get(det["cls"], "?").upper()
        team_name = TEAM_NAMES.get(team, "?")
        label = f"{id_text} {cls_name} {team_name} {det['conf']:.2f}"

        dist = det.get("dist")
        if dist is not None:
            band = det.get("band_name", "?")
            ok = "" if det.get("dist_ok") else "~"
            label += f" | {ok}{dist:.2f}m {band}"
            
        vx = det.get("vx", 0.0)
        vy = det.get("vy", 0.0)

        _draw_label(frame, label, x, y, color)
        _draw_velocity(frame, x + w // 2, y + h // 2, vx, vy, color)

    _draw_parent_links(frame, detections, centers)

def _draw_label(frame, text, x, y, color):
    """Kutu ustune okunabilir etiket cizer.

    Args:
        frame: BGR NumPy dizisi
        text: Etiket metni
        x: Kutu sol kenari
        y: Kutu ust kenari
        color: BGR renk
    """
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 0.5
    thickness = 1

    (tw, th), baseline = cv2.getTextSize(text, font, scale, thickness)
    label_y = max(th + 4, y)

    cv2.rectangle(frame, (x, label_y - th - 4), (x + tw + 4, label_y + baseline),
                  color, -1)
    cv2.putText(frame, text, (x + 2, label_y - 2), font, scale,
                (0, 0, 0), thickness)


def _draw_parent_links(frame, detections, centers):
    """Balon ile bagli oldugu maket arasinda cizgi ceker.

    Args:
        frame: BGR NumPy dizisi
        detections: Tespit listesi
        centers: id -> (cx, cy) esleme sozlugu
    """
    for det in detections:
        parent_id = det.get("parent_id")
        if parent_id is None or parent_id not in centers:
            continue

        cv2.line(frame, centers[det["id"]], centers[parent_id],
                 (255, 255, 255), 1)


def draw_hud(frame, frame_id, latency_ms, detection_count):
    """Ust bilgi satirlarini cizer.

    Args:
        frame: BGR NumPy dizisi
        frame_id: Kare numarasi
        latency_ms: Uctan uca gecikme
        detection_count: Tespit sayisi
    """
    height = frame.shape[0]

    text = (f"frame {frame_id} | gecikme {latency_ms:.0f} ms | "
            f"hedef {detection_count} | namlu @{settings.BALLISTIC_DEFAULT_RANGE:.0f}m")
    cv2.putText(frame, text, (20, height - 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

    lock_info = get_lock_info()
    if lock_info is None:
        return

    state = lock_info.get("state_name", "?")
    lock_text = (f"KILIT #{lock_info['track_id']} {state} "
                 f"devir={lock_info['reacquires']} "
                 f"kayip={lock_info['lost_for']:.1f}s")

    color = (0, 255, 0) if state == "LOCKED" else (0, 165, 255)
    cv2.putText(frame, lock_text, (20, height - 50),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)


# --- Video alicisi ---------------------------------------------------------

def parse_video_packet(data):
    """Video datagramini baslik ve JPEG olarak ayristirir.

    Args:
        data: Ham datagram baytlari

    Returns:
        (frame_id, timestamp, jpeg_bytes, width, height) veya None
    """
    if len(data) < HEADER_SIZE:
        log.warning("Paket cok kisa: %d bayt", len(data))
        return None

    magic, frame_id, timestamp, jpeg_size, width, height = struct.unpack(
        settings.VIDEO_HEADER_FORMAT, data[:HEADER_SIZE]
    )

    if magic != settings.VIDEO_MAGIC:
        log.warning("Gecersiz magic: %r", magic)
        return None

    jpeg = data[HEADER_SIZE:HEADER_SIZE + jpeg_size]

    if len(jpeg) != jpeg_size:
        log.warning("JPEG boyutu uyusmuyor: beklenen=%d gelen=%d",
                    jpeg_size, len(jpeg))
        return None

    return frame_id, timestamp, jpeg, width, height


def main():
    """Alici dongusunu calistirir. ESC ile cikilir."""
    global _running

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)-14s | %(message)s",
        datefmt="%H:%M:%S",
    )

    detection_thread = threading.Thread(target=_detection_loop,
                                        name="detections", daemon=True)
    detection_thread.start()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF,
                    settings.RECV_BUFFER_SIZE)
    sock.bind((settings.TARGET_IP, settings.VIDEO_PORT))
    sock.settimeout(1.0)

    log.info("Video dinleniyor: %s:%d",
             settings.TARGET_IP, settings.VIDEO_PORT)
    print("ESC ile cikis")

    received = 0
    missed = 0
    last_frame_id = 0
    last_report = time.perf_counter()

    try:
        while True:
            try:
                data, _ = sock.recvfrom(settings.UDP_BUFFER_SIZE)
            except socket.timeout:
                log.warning("Kare gelmiyor")
                continue

            parsed = parse_video_packet(data)
            if parsed is None:
                continue

            frame_id, timestamp, jpeg, width, height = parsed

            if last_frame_id and frame_id > last_frame_id + 1:
                missed += frame_id - last_frame_id - 1
            last_frame_id = frame_id

            frame = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8),
                                 cv2.IMREAD_COLOR)
            if frame is None:
                log.warning("JPEG cozulemedi (frame_id=%d)", frame_id)
                continue

            received += 1
            latency_ms = (time.time() - timestamp) * 1000

            detections, _ = _find_detections(frame_id)
            draw_detections(frame, detections,
                            settings.FRAME_WIDTH, settings.FRAME_HEIGHT)
            draw_aim(frame, get_aim_info())
            draw_hud(frame, frame_id, latency_ms, len(detections))

            now = time.perf_counter()
            if now - last_report >= settings.REPORT_INTERVAL:
                log.info("alinan=%d kacan=%d gecikme=%.0f ms hedef=%d %dx%d",
                         received, missed, latency_ms, len(detections),
                         width, height)
                last_report = now

            cv2.imshow("BAT-X3 test alici", frame)
            if cv2.waitKey(1) == 27:
                break
    finally:
        _running = False
        sock.close()
        cv2.destroyAllWindows()

def _draw_velocity(frame, cx, cy, vx, vy, color):
    """Hiz vektorunu ok olarak cizer.

    Ok uzunlugu 0.5 saniyelik tahmini yer degistirmeyi gosterir.

    Args:
        frame: BGR NumPy dizisi
        cx: Kutu merkezi x
        cy: Kutu merkezi y
        vx: Yatay hiz (piksel/saniye)
        vy: Dikey hiz (piksel/saniye)
        color: BGR renk
    """
    scale = 0.5
    end_x = int(cx + vx * scale)
    end_y = int(cy + vy * scale)

    if abs(end_x - cx) < 5 and abs(end_y - cy) < 5:
        return

    cv2.arrowedLine(frame, (cx, cy), (end_x, end_y), color, 2, tipLength=0.3)



def draw_aim(frame, aim_info):
    """Namlu ekseni ve nisan noktasi gostergelerini cizer.

    Uc gosterge cizilir:

    BEYAZ artı   Kamera ekseni — ekranin tam merkezi.
    YESIL artı   Namlu ekseni — merminin gidecegi tahmini nokta.
                 Balistik duzeltme kadar merkezden otelenmistir.
                 Kalibrasyon bu isarete gore yapilir.
    RENKLI artı  Kilitli hedefin nisan noktasi (varsa).

    Args:
        frame: BGR NumPy dizisi
        aim_info: aiming.solve() ciktisi veya None
    """
    h, w = frame.shape[:2]
    cx, cy = w // 2, h // 2

    # Kamera ekseni — sabit referans
    cv2.line(frame, (cx - 40, cy), (cx + 40, cy), (255, 255, 255), 1)
    cv2.line(frame, (cx, cy - 40), (cx, cy + 40), (255, 255, 255), 1)

    _draw_camera_axis(frame, cx, cy)
    _draw_muzzle_axis(frame, cx, cy)

    if aim_info is None:
        return

    ax = int(aim_info["aim_x"])
    ay = int(aim_info["aim_y"])

    color = (0, 255, 0) if aim_info["on_target"] else (0, 165, 255)

    cv2.drawMarker(frame, (ax, ay), color, cv2.MARKER_CROSS, 30, 2)
    cv2.line(frame, (cx, cy), (ax, ay), color, 1)

    cv2.putText(frame, f"hata {aim_info['distance']:.0f} px",
                (ax + 20, ay), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)


def _draw_camera_axis(frame, cx, cy):
    """Kamera eksenini kesikli acik gri cizgilerle isaretler.

    Sabit referanstir; kalibrasyonda kullanilmaz. Namlu ekseninden
    ayirt edilebilmesi icin kesikli ve soluk cizilir.

    Args:
        frame: BGR NumPy dizisi
        cx: Merkez x
        cy: Merkez y
    """
    color = (170, 170, 170)
    gap = 6
    dash = 8
    reach = 55

    for offset in range(gap, reach, dash + gap):
        end = min(offset + dash, reach)
        cv2.line(frame, (cx - end, cy), (cx - offset, cy), color, 1)
        cv2.line(frame, (cx + offset, cy), (cx + end, cy), color, 1)
        cv2.line(frame, (cx, cy - end), (cx, cy - offset), color, 1)
        cv2.line(frame, (cx, cy + offset), (cx, cy + end), color, 1)


def _draw_muzzle_axis(frame, cx, cy):
    """Namlu ekseninin ekrandaki tahmini konumunu cizer.

    Balistik duzeltme kadar kamera ekseninden otelenmistir. Kalibrasyon
    atislarinda bu isaret hedefe getirilir; isabet noktasi ile arasindaki
    fark AIM_ZERO_X/Y degerlerine yazilir.

    Iki isaret cok yakin oldugunda (yakin mesafede otelenme birkac
    piksel kalir) ayirt edilebilmesi icin kalin, dolu ve etiketli cizilir.

    Args:
        frame: BGR NumPy dizisi
        cx: Kamera ekseni x
        cy: Kamera ekseni y
    """
    dx, dy = ballistics.correction(
        settings.BALLISTIC_DEFAULT_RANGE, ranging.focal_length_px()
    )

        # Duzeltme, nisan noktasina EKLENEN kaydirmadir (bkz. aiming.solve).
    # Namlunun ekrandaki tahmini isabet noktasi bunun TERSIDIR: silah
    # sol altta oldugu icin mermi sol alta gider, nisan sag ustten
    # alinir. Isaret ters cizilirse kalibrasyon atisinda mermi
    # otelemenin iki kati kadar sapar.
    mx = int(round(cx - dx))
    my = int(round(cy - dy))
    print(f"namlu ekseni: mx={mx} my={my}  (dx={dx:.2f} dy={dy:.2f})")

    green = (0, 230, 0)
    shadow = (0, 0, 0)

    # Koyu golge: acik zeminde okunabilirlik saglar
    cv2.circle(frame, (mx, my), 22, shadow, 4)
    cv2.circle(frame, (mx, my), 22, green, 2)

    # Dort kisa cizik — dairenin disinda, ic kismi acik birakir
    for dx_dir, dy_dir in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        x1 = mx + dx_dir * 22
        y1 = my + dy_dir * 22
        x2 = mx + dx_dir * 34
        y2 = my + dy_dir * 34
        cv2.line(frame, (x1, y1), (x2, y2), shadow, 4)
        cv2.line(frame, (x1, y1), (x2, y2), green, 2)

    # Merkez noktasi
    cv2.circle(frame, (mx, my), 3, shadow, -1)
    cv2.circle(frame, (mx, my), 2, green, -1)


def _draw_shadowed_text(frame, text, x, y, color, scale=0.5):
    """Acik zeminde okunabilir metin cizer.

    Args:
        frame: BGR NumPy dizisi
        text: Yazilacak metin
        x: Sol kenar
        y: Taban cizgisi
        color: BGR renk
        scale: Yazi olcegi
    """
    font = cv2.FONT_HERSHEY_SIMPLEX
    cv2.putText(frame, text, (x, y), font, scale, (0, 0, 0), 3)
    cv2.putText(frame, text, (x, y), font, scale, color, 1)



if __name__ == "__main__":
    main()