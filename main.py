"""BAT-X3 Python alt sistemi giris noktasi.

Tum bilesenleri baslatir ve yonetir:
    - Kare yakalama dongusu (vision.frame_buffer)
    - Cikarim dongusu       (vision.detection_buffer)
    - Takip/angajman dongusu (control.tracking_loop)
    - Kontrol katmani       (SystemManager + ParamBridge, seri port)
    - Komut/ayar sunucusu   (UDP, settings.COMMAND_UDP_PORT)
    - Video yayini          (UDP, settings.VIDEO_PORT)
    - Tespit yayini         (UDP, settings.DETECTION_PORT)
    - MJPEG tani sunucusu   (TCP, settings.MJPEG_PORT)

Tum video tuketicileri ayni frame_buffer'dan okur; kamera bir kez acilir
ve tum yayinlar ayni frame_id'yi kullanir. Bu, alici tarafta kutularin
dogru kareyle eslestirilmesini saglar.

Bilesenler settings.ENABLE_* bayraklariyla ayri ayri kapatilabilir.

Kullanim:
    python main.py
    Ctrl+C ile durdurulur.
"""

import logging
import threading
import time
from http.server import ThreadingHTTPServer

from config import settings
from control import tracking_loop
from control import turret_driver
from control.param_bridge import ParamBridge
from control.system_manager import SystemManager
from core.logging_setup import setup_logging
from protocols.tcp import mjpeg_server
from protocols.udp import command_server, detection_server, video_server
from vision import detection_buffer, frame_buffer
from vision import ballistics, ranging

ballistics.describe(ranging.focal_length_px())

log = logging.getLogger("main")


def _start_thread(target, name):
    """Adlandirilmis bir daemon thread baslatir.

    Args:
        target: Calistirilacak fonksiyon
        name: Thread adi (log ve hata ayiklama icin)

    Returns:
        threading.Thread — baslatilmis thread
    """
    thread = threading.Thread(target=target, name=name, daemon=True)
    thread.start()
    return thread


def _start_workers():
    """Goruntu isleme ve takip dongulerini baslatir.

    Bu bilesenler kendi thread'lerini yonettigi icin threads listesine
    eklenmezler.
    """
    frame_buffer.start()

    if settings.ENABLE_DETECTIONS:
        detection_buffer.start()

    if settings.ENABLE_TRACKING_LOOP:
        tracking_loop.start()


def _start_services():
    """Etkinlestirilmis ag ve kontrol servislerini baslatir.

    Returns:
        (threads, http_server, control) — durdurma icin gerekli
        referanslar. control, (manager, bridge) ikilisi veya None'dir.
    """
    threads = []
    http_server = None
    control = None

    # Kontrol katmani ONCE baslatilir: seri baglantinin kurulmasi bir
    # saniyeye kadar surebilir, komut sunucusu acilmadan once denemeye
    # baslamis olmasi iyidir.
    #
    # SystemManager ve ParamBridge kendi thread'lerini yonettigi icin
    # _start_thread kullanilmaz; threads listesine de eklenmezler.
    if settings.ENABLE_CONTROL:
        manager = SystemManager()
        manager.start()
        bridge = ParamBridge(manager)
        bridge.start()
        turret_driver.set_backend(manager)
        control = (manager, bridge)

    if settings.ENABLE_COMMAND_SERVER:
        threads.append(_start_thread(command_server.run, "command_server"))

    if settings.ENABLE_VIDEO:
        threads.append(_start_thread(video_server.run, "video_server"))

    if settings.ENABLE_DETECTIONS:
        threads.append(_start_thread(detection_server.run, "detection_server"))

    if settings.ENABLE_MJPEG:
        http_server = ThreadingHTTPServer(
            (settings.MJPEG_HOST, settings.MJPEG_PORT),
            mjpeg_server.MjpegHandler,
        )
        threads.append(_start_thread(http_server.serve_forever, "mjpeg_server"))
        log.info("MJPEG tani sunucusu: http://localhost:%d/", settings.MJPEG_PORT)

    return threads, http_server, control


def _shutdown(threads, http_server, control):
    """Tum bilesenleri duzgun sekilde durdurur.

    Args:
        threads: Durdurulacak thread listesi
        http_server: HTTP sunucu nesnesi veya None
        control: (manager, bridge) ikilisi veya None
    """
    # Kontrol katmani EN ONCE durdurulur: onceligimiz tareti durdurmaktir.
    # Ag servisleri birkac milisaniye daha acik kalabilir, taret kalamaz.
    #
    # Sira onemli: once dongu durur (manager'a yeni komut gitmesin),
    # sonra manager STOP gonderip portu kapatir.
    if control is not None:
        manager, bridge = control
        turret_driver.set_backend(None)
        bridge.stop()
        manager.stop()

    command_server.stop()
    video_server.stop()
    detection_server.stop()

    if http_server is not None:
        http_server.shutdown()

    for thread in threads:
        thread.join(timeout=settings.SHUTDOWN_TIMEOUT)
        if thread.is_alive():
            log.warning("Thread durmadi: %s", thread.name)

    # Goruntu isleme zinciri tersten durdurulur: once tuketiciler,
    # sonra uretici.
    tracking_loop.stop()
    detection_buffer.stop()
    frame_buffer.stop()

    log.info("Sistem durdu")


def main():
    """Tum alt sistemleri baslatir ve calistirir."""
    setup_logging(level=logging.INFO)

    log.info("BAT-X3 Python alt sistemi baslatiliyor")

    _start_workers()
    threads, http_server, control = _start_services()

    log.info(
        "Sistem calisiyor (%d ag servisi%s). Ctrl+C ile durdurun.",
        len(threads),
        ", kontrol katmani acik" if control is not None else "",
    )

    try:
        # Kontrol katmani kendi thread'lerini yonettigi icin threads
        # listesinde yer almaz. Yalnizca thread sayisina bakilirsa tum
        # ag servisleri kapatildiginda program aninda sonlanir ve
        # Arduino baglantisi kurulmus olsa bile kapanir.
        while threads or control is not None:
            if threads and not any(t.is_alive() for t in threads):
                log.warning("Tum ag servisleri durdu")
                break
            time.sleep(0.2)
    except KeyboardInterrupt:
        log.info("Kapatiliyor...")
    finally:
        _shutdown(threads, http_server, control)


if __name__ == "__main__":
    main()
