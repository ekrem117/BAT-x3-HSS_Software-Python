"""Duz .track() teshis araci — thread/kuyruk karmasikligi olmadan.

detection_buffer.py'nin kullandigi ile BIREBIR ayni cagriyi (model,
tracker, parametreler) tek bir duz dongude, gercek kamerayla calistirir.
Her adim ANINDA (flush=True) yazdirilir — eger bir kare takilirsa,
hangi kare numarasinda takildigi ekranda gorunur, tahmin gerekmez.

main.py CALISMAMALIDIR (kamera kilidi cakisir).

Kullanim:
    py -m tools.track_debug
"""

import time

import cv2
from ultralytics import YOLO

from config import settings

print(f"Kamera aciliyor (index={settings.CAMERA_INDEX})...", flush=True)
cap = cv2.VideoCapture(settings.CAMERA_INDEX, cv2.CAP_DSHOW)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, settings.FRAME_WIDTH)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, settings.FRAME_HEIGHT)
if not cap.isOpened():
    raise SystemExit("Kamera acilamadi.")
print("Kamera acildi.", flush=True)

print(f"Model yukleniyor: {settings.MODEL_PATH} ...", flush=True)
model = YOLO(settings.MODEL_PATH)
print(f"Model yuklendi. siniflar={model.names}", flush=True)
print(f"TRACKER_CONFIG={settings.TRACKER_CONFIG}", flush=True)

N = 8
for i in range(1, N + 1):
    ok, frame = cap.read()
    if not ok:
        print(f"kare {i}: OKUNAMADI", flush=True)
        continue

    print(f"kare {i}: .track() baslıyor...", flush=True)
    t0 = time.perf_counter()
    results = model.track(
        frame,
        imgsz=settings.MODEL_IMGSZ,
        conf=settings.MODEL_CONF,
        iou=settings.MODEL_IOU,
        max_det=settings.MODEL_MAX_DET,
        device=settings.MODEL_DEVICE,
        tracker=settings.TRACKER_CONFIG,
        persist=True,
        verbose=False,
    )
    dt = (time.perf_counter() - t0) * 1000
    n_box = len(results[0].boxes) if results and results[0].boxes is not None else 0
    print(f"kare {i}: BITTI  sure={dt:.0f}ms  kutu_sayisi={n_box}", flush=True)

cap.release()
print("Tamamlandi.", flush=True)
