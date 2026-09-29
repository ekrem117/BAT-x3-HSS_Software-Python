"""MJPEG HTTP video sunucusu — tani araci.

Kareleri multipart/x-mixed-replace formatinda HTTP uzerinden yayinlar.
Asil video aktarimi protocols.udp.video_server uzerinden yapilir; bu
modul tarayicidan gorsel dogrulama icin tutulur.

"Kamera mi sorunlu, arayuz mu" sorusunu tarayicidan bakarak cevaplamayi
saglar. Diger yayinlarla ayni frame_buffer'dan okur.

Uc nokta:
    /        Test sayfasi (HTML)
    /stream  MJPEG akisi

TCP tabanli oldugu icin datagram boyut siniri yoktur; encode_jpeg
yeterlidir.
"""

import logging
import time
from http.server import BaseHTTPRequestHandler

from config import settings
from vision import encoder, frame_buffer

log = logging.getLogger("mjpeg_server")

INDEX_HTML = b"""<!DOCTYPE html>
<html>
<head><title>BAT-X3 Video</title></head>
<body style="margin:0;background:#111;text-align:center">
  <img src="/stream" style="max-width:100%;height:auto">
</body>
</html>"""


class MjpegHandler(BaseHTTPRequestHandler):
    """MJPEG akisi ve test sayfasi sunan HTTP isleyicisi."""

    def do_GET(self):
        """GET isteklerini yola gore yonlendirir."""
        if self.path == "/":
            self._serve_index()
        elif self.path == "/stream":
            self._serve_stream()
        else:
            self.send_error(404)

    def _serve_index(self):
        """Basit test sayfasini gonderir."""
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(INDEX_HTML)))
        self.end_headers()
        self.wfile.write(INDEX_HTML)

    def _serve_stream(self):
        """MJPEG akisini gonderir.

        Baglanti kapanana kadar yayin yapar. Yalnizca yeni kareler
        gonderilir; ayni kare tekrar kodlanmaz. Hiz frame_buffer
        tarafindan belirlenir.
        """
        self.send_response(200)
        self.send_header("Age", "0")
        self.send_header("Cache-Control", "no-cache, private")
        self.send_header("Pragma", "no-cache")
        self.send_header(
            "Content-Type",
            f"multipart/x-mixed-replace; boundary={settings.MJPEG_BOUNDARY}",
        )
        self.end_headers()

        log.info("Istemci baglandi: %s", self.client_address[0])

        sent = 0
        last_sent_id = 0

        try:
            while True:
                frame, frame_id = frame_buffer.get_latest()

                if frame is None or frame_id == last_sent_id:
                    time.sleep(settings.IDLE_SLEEP)
                    continue

                last_sent_id = frame_id
                jpg = encoder.encode_jpeg(frame)

                if jpg is None:
                    continue

                boundary = settings.MJPEG_BOUNDARY
                self.wfile.write(f"--{boundary}\r\n".encode())
                self.wfile.write(b"Content-Type: image/jpeg\r\n")
                self.wfile.write(f"Content-Length: {len(jpg)}\r\n".encode())
                self.wfile.write(f"X-Frame-Id: {frame_id}\r\n".encode())
                self.wfile.write(b"\r\n")
                self.wfile.write(jpg)
                self.wfile.write(b"\r\n")

                sent += 1

        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            log.info("Istemci ayrildi: %s (%d kare gonderildi)",
                     self.client_address[0], sent)
        except Exception:
            log.exception("Akis hatasi: %s", self.client_address[0])

    def log_message(self, fmt, *args):
        """Varsayilan konsol loglamasini bastirir.

        BaseHTTPRequestHandler her istegi stderr'e yazar; kendi
        logger'imizi kullaniyoruz.
        """
        log.debug("%s - %s", self.client_address[0], fmt % args)