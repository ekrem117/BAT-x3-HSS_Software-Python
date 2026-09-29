"""Tespit yayin sunucusu.

Tespit kutularini JSON olarak UDP uzerinden yayinlar. Video akisiyla
ayni frame_id kullanilir; alici taraf kutulari dogru kareyle
eslestirebilir.

Paket yapisi (UTF-8 JSON):
    {
      "frame_id": uint,
      "ts": float,
      "detections": [
        {"id": int, "x": int, "y": int, "w": int, "h": int,
         "cls": int, "team": int, "conf": float}
      ]
    }

Koordinatlar kaynak cozunurluktedir ve kutunun SOL UST kosesini gosterir.
Alici yetisemezse paketler dusrulur; birikme olmaz.
"""

import json
import logging
import socket
import time

from config import settings
from vision import detection_buffer, track_store
from control import engagement
from control import aiming, engagement

log = logging.getLogger("detection_server")

_socket = None
_running = False


def _build_packet(frame_id, boxes, lock_info, aim_info):
    """Tespit paketini JSON baytlarina cevirir.

    Args:
        frame_id: Ilgili kare numarasi
        boxes: Tespit sozlukleri listesi
        lock_info: Angajman ozeti veya None
        aim_info: Nisan cozumu veya None

    Returns:
        bytes — UTF-8 kodlanmis JSON
    """
    payload = {
        "frame_id": frame_id,
        "ts": time.time(),
        "detections": boxes,
        "lock": lock_info,
        "aim": aim_info,
    }
    return json.dumps(payload).encode("utf-8")


def run(target_ip=None, target_port=None):
    """Yayin dongusunu calistirir. stop() cagrilana kadar devam eder.

    Args:
        target_ip: Hedef IP. None ise settings.TARGET_IP.
        target_port: Hedef port. None ise settings.DETECTION_PORT.
    """
    global _socket, _running

    if target_ip is None:
        target_ip = settings.TARGET_IP
    if target_port is None:
        target_port = settings.DETECTION_PORT

    _socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    _running = True
    target = (target_ip, target_port)

    log.info("Tespit yayini basladi: %s:%d", target_ip, target_port)

    last_id = 0
    sent = 0
    last_size = 0
    last_count = 0
    last_report = time.perf_counter()

    while _running:
        start = time.perf_counter()

        _, frame_id = detection_buffer.get_latest()

        if frame_id == 0:
            time.sleep(settings.IDLE_SLEEP)
            continue

        boxes = track_store.predict_all()
        lock_info = engagement.current()
        aim_info = aiming.solve(lock_info)
        packet = _build_packet(frame_id, boxes, lock_info, aim_info)

        try:
            _socket.sendto(packet, target)
            sent += 1
            last_size = len(packet)
            last_count = len(boxes)
        except OSError as e:
            log.warning("Paket gonderilemedi (%d bayt): %s", len(packet), e)

        now = time.perf_counter()
        if now - last_report >= settings.REPORT_INTERVAL:
            log.info("gonderilen=%d hedef=%d boyut=%d bayt",
                     sent, last_count, last_size)
            last_report = now

        elapsed = time.perf_counter() - start
        if elapsed < settings.FRAME_INTERVAL:
            time.sleep(settings.FRAME_INTERVAL - elapsed)

    _socket.close()
    log.info("Tespit yayini durdu (toplam %d paket)", sent)


def stop():
    """Yayin dongusunu durdurur."""
    global _running
    _running = False