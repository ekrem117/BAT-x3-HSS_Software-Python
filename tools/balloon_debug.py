"""Balon tespit teshisi — kaydedilmis bir karede modelin HAM cikisini gosterir.

Kamera/izleyici/oran filtresi zincirini devre disi birakir; yalnizca
"model bu piksellerde balon goruyor mu, ne kadar emin" sorusuna cevap verir.

Cok dusuk conf (0.01) ile calisir ki neredeyse hicbir aday elenmesin —
gercek guven skorunu gormek istiyoruz, uretim esigini degil.

Uretim kodunun parcasi degildir; teshis bitince silinebilir.

Kullanim:
    1. main.py calisirken http://localhost:8080/ adresinden balonun
       net gorundugu bir kareyi kaydet.
    2. Asagidaki IMAGE_PATH'i o dosyaya isaret edecek sekilde degistir.
    3. main.py'yi durdur (kamera kilidi cakismasin diye, zorunlu degil
       ama temiz olur).
    4. py -m tools.balloon_debug
"""

import cv2
from ultralytics import YOLO

from config import settings

IMAGE_PATH = r"ornek_kare.png"   # <-- incelenecek goruntunun yolunu yaz

img = cv2.imread(IMAGE_PATH)
if img is None:
    raise SystemExit(f"Goruntu okunamadi: {IMAGE_PATH}")

H, W = img.shape[:2]
print(f"Goruntu: {W}x{H}")

model = YOLO(settings.MODEL_PATH)
print(f"Model: {settings.MODEL_PATH} | siniflar={model.names}")

print("\n=== TAM KARE, conf=0.01 (neredeyse hicbir aday elenmez) ===")
r = model.predict(img, imgsz=settings.MODEL_IMGSZ, conf=0.01, verbose=False)[0]

if len(r.boxes) == 0:
    print("TESPIT YOK — model bu karede HICBIR SEYI hicbir guvenle gormuyor.")
    print("Bu, esik/izleyici sorunu degildir; goruntu/model/on-isleme")
    print("zincirinde daha temel bir uyusmazlik var demektir.")
else:
    for b in r.boxes:
        cls_name = model.names[int(b.cls)]
        conf = float(b.conf)
        x1, y1, x2, y2 = b.xyxy[0].tolist()
        ratio = ((x2 - x1) * (y2 - y1)) / (W * H)
        print(f"  {cls_name:8s} conf={conf:.3f}  oran={ratio:.4f}  "
              f"kutu=({x1:.0f},{y1:.0f})-({x2:.0f},{y2:.0f})")

print("\n=== Balon icin ozel arama (varsa) ===")
balon_idx = [k for k, v in model.names.items() if v == "balon"]
if balon_idx and len(r.boxes) > 0:
    balon_boxes = [b for b in r.boxes if int(b.cls) == balon_idx[0]]
    if not balon_boxes:
        print("Balon sinifinda HICBIR aday yok (0.01 esikte bile).")
        print("-> Model bu goruntude balonu tanimiyor. Aday nedenler:")
        print("   - Egitim setinde bu isik/mesafe/acidan ornek yok")
        print("   - MODEL_PATH farkli bir checkpoint ile denenmeli")
        print("     (settings.py yorumunda 'best_final.pt ve best_final3.pt")
        print("     iyi' notu var, best_v5.pt yerine onlari dene)")
    else:
        best = max(balon_boxes, key=lambda b: float(b.conf))
        print(f"En yuksek balon guveni: {float(best.conf):.3f}")
        if float(best.conf) < settings.MODEL_CONF:
            print(f"-> MODEL_CONF ({settings.MODEL_CONF}) esiginin altinda, "
                  "bu yuzden uretimde hic gorunmuyor.")
