"""Komut ve ayar sunucusu.

Soketi acar, gelen datagramlari JSON olarak cozer ve dispatcher'a
iletir. Cozulemeyen mesajlar icin ERRRSP (status=3) dondurur.

Cevap her zaman istegin geldigi adrese gonderilir; istemci portu koda
gomulu degildir.
"""

import json
import logging
import socket

from config import settings
from core.enums import ErrCode, Method
from protocols.udp import dispatcher

log = logging.getLogger("command_server")

_socket = None
_running = False


def run(host=None, port=None):
    """Dinleme dongusunu calistirir. stop() cagrilana kadar devam eder.

    Args:
        host: Dinlenecek adres. None ise settings.COMMAND_UDP_HOST.
        port: Dinlenecek port. None ise settings.COMMAND_UDP_PORT.
    """
    global _socket, _running

    if host is None:
        host = settings.COMMAND_UDP_HOST
    if port is None:
        port = settings.COMMAND_UDP_PORT

    _socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    _socket.bind((host, port))
    _socket.settimeout(0.5)
    _running = True

    log.info("Komut sunucusu dinliyor: %s:%d", host, port)

    while _running:
        try:
            data, addr = _socket.recvfrom(settings.UDP_BUFFER_SIZE)
        except socket.timeout:
            continue
        except OSError:
            break

        response = _process(data, addr)

        try:
            _socket.sendto(json.dumps(response).encode("utf-8"), addr)
        except OSError as e:
            log.warning("Cevap gonderilemedi (%s): %s", addr, e)

    _socket.close()
    log.info("Komut sunucusu durdu")


def _process(data, addr):
    """Ham datagrami cozer ve cevap sozlugu uretir.

    Args:
        data: Ham datagram baytlari
        addr: Gonderen adres (loglama icin)

    Returns:
        Cevap sozlugu
    """
    try:
        text = data.decode("utf-8", errors="replace").strip()
        message = json.loads(text)

        if not isinstance(message, dict):
            raise ValueError("mesaj bir nesne degil")

        return dispatcher.handle_message(message)

    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as e:
        log.error("Mesaj cozulemedi: %s | gonderen=%s ham=%r", e, addr, data)
        return {
            "Method": Method.ERR_RSP,
            "messageID": None,
            "status": ErrCode.MESSAGE_FORMAT_ERROR.value,
        }


def stop():
    """Dinleme dongusunu durdurur."""
    global _running
    _running = False