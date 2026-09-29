"""UDP video yayin sunucusu.

Kareleri JPEG olarak sikistirip UDP uzerinden tek datagram halinde
gonderir. Her paket bir tam kare tasir; parcalama yapilmaz.

Paket yapisi (little-endian):
    Offset  Boyut  Alan       Tip
    0       4      magic      "BX3F"
    4       4      frame_id   uint32
    8       8      timestamp  double (Unix zamani)
    16      4      jpeg_size  uint32
    20      2      width      uint16
    22      2      height     uint16
    24      ...    JPEG verisi

Alici yetisemezse paketler dusrulur; kare birikmesi olmaz. Nisan ekrani
icin dogru davranis budur — eski kare gostermek yerine kare atlanir.
"""

import logging
import socket
import struct
import time

from config import settings
from vision import encoder, frame_buffer

log = logging.getLogger("video_server")

HEADER_SIZE = struct.calcsize(settings.VIDEO_HEADER_FORMAT)

_socket = None
_running = False


def _open_socket():
    """UDP gonderim soketini acar ve gonderim tamponunu buyutur."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF,
                    settings.SEND_BUFFER_SIZE)

    actual = sock.getsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF)
    log.info("Gonderim tamponu: %d bayt (istenen %d)",
             actual, settings.SEND_BUFFER_SIZE)

    return sock


def _build_packet(jpg, frame_id, width, height):
    """Baslik ve JPEG verisini tek pakete birlestirir.

    Args:
        jpg: JPEG baytlari
        frame_id: Kare sayaci
        width: Kare genisligi
        height: Kare yuksekligi

    Returns:
        bytes — gonderime hazir datagram
    """
    header = struct.pack(
        settings.VIDEO_HEADER_FORMAT,
        settings.VIDEO_MAGIC,
        frame_id,
        time.time(),
        len(jpg),
        width,
        height,
    )
    return header + jpg


def run(target_ip=None, target_port=None):
    """Yayin dongusunu calistirir. stop() cagrilana kadar devam eder.

    Args:
        target_ip: Hedef IP. None ise settings.TARGET_IP.
        target_port: Hedef port. None ise settings.VIDEO_PORT.
    """
    global _socket, _running

    if target_ip is None:
        target_ip = settings.TARGET_IP
    if target_port is None:
        target_port = settings.VIDEO_PORT

    _socket = _open_socket()
    _running = True
    target = (target_ip, target_port)

    log.info("Video yayini basladi: %s:%d", target_ip, target_port)

    last_id = 0
    sent = 0
    dropped = 0
    last_size = 0
    last_quality = 0
    last_report = time.perf_counter()

    while _running:
        start = time.perf_counter()

        frame, frame_id = frame_buffer.get_latest()

        if frame is None or frame_id == last_id:
            time.sleep(settings.IDLE_SLEEP)
            continue

        last_id = frame_id

        stream_frame = encoder.resize_for_stream(frame)
        jpg, quality = encoder.encode_jpeg_bounded(stream_frame)

        if jpg is None:
            dropped += 1
            continue

        height, width = stream_frame.shape[:2]
        packet = _build_packet(jpg, frame_id, width, height)

        try:
            _socket.sendto(packet, target)
            sent += 1
            last_size = len(packet)
            last_quality = quality
        except OSError as e:
            dropped += 1
            log.warning("Paket gonderilemedi (%d bayt): %s", len(packet), e)

        now = time.perf_counter()
        if now - last_report >= settings.REPORT_INTERVAL:
            log.info("gonderilen=%d dusen=%d boyut=%.0f KB kalite=%d",
                     sent, dropped, last_size / 1024, last_quality)
            last_report = now

        elapsed = time.perf_counter() - start
        if elapsed < settings.STREAM_INTERVAL:
            time.sleep(settings.STREAM_INTERVAL - elapsed)

    _socket.close()
    log.info("Video yayini durdu (toplam %d kare)", sent)


def stop():
    """Yayin dongusunu durdurur."""
    global _running
    _running = False