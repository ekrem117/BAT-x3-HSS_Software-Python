"""Kare kaynagi ve kodlama olcum araci.

Yakalama suresi, JPEG kodlama suresi ve kare boyutunu olcer. Uretim
kodunun parcasi degildir; elle calistirilir.

DIKKAT: Kamerayi dogrudan acar. main.py calisirken kullanilamaz —
kamera ayni anda tek surec tarafindan acilabilir.

Kullanim (proje kokunden):
    python tools/bench.py
"""

import logging
import sys
import time
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from vision import encoder, frame_source  # noqa: E402

log = logging.getLogger("bench")

SAMPLE_SIZE = 30


def main():
    """Olcum dongusunu calistirir. ESC ile cikilir."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)-14s | %(message)s",
        datefmt="%H:%M:%S",
    )

    print("ESC ile cikis")

    capture_times = []
    encode_times = []
    sizes = []

    try:
        while True:
            t0 = time.perf_counter()
            frame, frame_id = frame_source.get_frame()
            t1 = time.perf_counter()

            jpg, quality = encoder.encode_jpeg_bounded(frame)
            t2 = time.perf_counter()

            capture_times.append((t1 - t0) * 1000)
            encode_times.append((t2 - t1) * 1000)
            sizes.append(len(jpg) / 1024 if jpg else 0)

            if len(capture_times) >= SAMPLE_SIZE:
                _report(capture_times, encode_times, sizes, quality)
                capture_times.clear()
                encode_times.clear()
                sizes.clear()

            cv2.imshow("bench", frame)
            if cv2.waitKey(1) == 27:
                break
    finally:
        frame_source.release_camera()
        cv2.destroyAllWindows()


def _report(capture_times, encode_times, sizes, quality):
    """Toplanan olcumlerin ortalamasini loglar.

    Args:
        capture_times: Yakalama sureleri (ms)
        encode_times: Kodlama sureleri (ms)
        sizes: Kare boyutlari (KB)
        quality: Son kullanilan JPEG kalitesi
    """
    avg_capture = sum(capture_times) / len(capture_times)
    avg_encode = sum(encode_times) / len(encode_times)
    avg_size = sum(sizes) / len(sizes)
    fps = 1000 / avg_capture if avg_capture > 0 else 0

    log.info("yakalama=%.1f ms  encode=%.1f ms  boyut=%.0f KB  kalite=%d  ~%.1f fps",
             avg_capture, avg_encode, avg_size, quality, fps)


if __name__ == "__main__":
    main()