"""En yalin canli tespit testi — kamera + YOLO, baska hicbir sey.

Thread yok, izleyici yok, tracker yok. Sadece kamerayi ac, her karede
model.predict() calistir, kutulari ciz, ekranda goster. Algilamanin
kendisinde sorun var mi yoksa daha ust katmanlarda mi (thread, izleyici,
kuyruk) diye ayirt etmek icin.

main.py CALISMAMALIDIR (kamera kilidi cakisir).

Cikis: 'q' tusu.

Kullanim:
    py -m tools.live_predict
"""

import time

import cv2
from ultralytics import YOLO

from config import settings

print(f"Kamera aciliyor (index={settings.CAMERA_INDEX})...")
cap = cv2.VideoCapture(settings.CAMERA_INDEX, cv2.CAP_DSHOW)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, settings.FRAME_WIDTH)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, settings.FRAME_HEIGHT)
if not cap.isOpened():
    raise SystemExit("Kamera acilamadi.")
print("Kamera acildi.")

print(f"Model yukleniyor: {settings.MODEL_PATH} ...")
model = YOLO(settings.MODEL_PATH)
print(f"Model yuklendi. siniflar={model.names}  conf_esigi={settings.MODEL_CONF}")
print("Cikmak icin pencerede 'q' tusuna bas.\n")

colors = {
    0: (255, 128, 0),    # drone
    1: (0, 128, 255),    # f16
    2: (0, 0, 255),      # fuze
    3: (255, 0, 255),    # heli
    4: (0, 255, 0),      # balon
}

frame_no = 0
while True:
    ok, frame = cap.read()
    if not ok:
        print("Kare okunamadi.")
        break

    frame_no += 1
    t0 = time.perf_counter()
    results = model.predict(
        frame,
        imgsz=settings.MODEL_IMGSZ,
        conf=settings.MODEL_CONF,
        iou=settings.MODEL_IOU,
        max_det=settings.MODEL_MAX_DET,
        device=settings.MODEL_DEVICE,
        verbose=False,
    )
    dt_ms = (time.perf_counter() - t0) * 1000

    boxes = results[0].boxes
    n = len(boxes) if boxes is not None else 0

    for i in range(n):
        x1, y1, x2, y2 = map(int, boxes.xyxy[i].tolist())
        cls_id = int(boxes.cls[i].item())
        conf = float(boxes.conf[i].item())
        color = colors.get(cls_id, (255, 255, 255))
        label = f"{model.names.get(cls_id, cls_id)} {conf:.2f}"

        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        cv2.putText(frame, label, (x1, max(0, y1 - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

    hud = f"kare {frame_no}  sure={dt_ms:.0f}ms  tespit={n}"
    cv2.putText(frame, hud, (20, 40), cv2.FONT_HERSHEY_SIMPLEX,
                0.9, (0, 255, 255), 2)

    print(hud, flush=True)

    show = cv2.resize(frame, (960, int(960 * frame.shape[0] / frame.shape[1])))
    cv2.imshow("live_predict - q ile cik", show)

    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()
print("Bitti.")
