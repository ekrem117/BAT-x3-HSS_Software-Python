"""YOLO nesne tespit sarmalayicisi.

Ultralytics YOLO modelini yukler ve kare uzerinde cikarim yapar.
Model sinif indeksleri protokol sinif kodlarina cevrilir; esleme
config.settings.MODEL_CLASS_MAP uzerinden yapilir.

Yeni bir model kullanmak icin settings.MODEL_PATH ve gerekiyorsa
MODEL_CLASS_MAP guncellenir; bu modulun govdesi degismez.

Cikti formati (docs/protocol_spec.md Bolum 11):
    {"id": int, "x": int, "y": int, "w": int, "h": int,
     "cls": int, "team": int, "conf": float, "parent_id": int|None}

Koordinatlar kaynak cozunurluktedir ve kutunun SOL UST kosesini gosterir.
"""

import logging
import time
from pathlib import Path

from config import settings
from core.enums import Team

log = logging.getLogger("detector")

_model = None
_model_failed = False


def load_model():
    """YOLO modelini yukler.

    Model dosyasi bulunamazsa veya ultralytics kurulu degilse None
    dondurur; cagiran taraf sentetik ureticiye dusebilir.

    Returns:
        YOLO nesnesi veya yuklenemezse None
    """
    try:
        from ultralytics import YOLO
    except ImportError:
        log.error("ultralytics kurulu degil: pip install ultralytics")
        return None

    model_path = Path(settings.MODEL_PATH)
    if not model_path.is_absolute():
        model_path = Path(__file__).resolve().parent.parent / model_path

    if not model_path.exists():
        log.error("Model dosyasi bulunamadi: %s", model_path)
        return None

    try:
        model = YOLO(str(model_path))
    except Exception:
        log.exception("Model yuklenemedi: %s", model_path)
        return None

    device = settings.MODEL_DEVICE or _detect_device()
    log.info("Model yuklendi: %s | cihaz=%s | siniflar=%s",
             model_path.name, device, model.names)

    if device == "cpu":
        log.warning("GPU bulunamadi, cikarim CPU uzerinde yapilacak "
                    "(kare basina 80-300 ms bekleniyor)")

    return model


def _detect_device():
    """Kullanilabilir cikarim cihazini belirler.

    Returns:
        str — "cuda:0" veya "cpu"
    """
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda:0"
    except ImportError:
        pass
    return "cpu"


def is_ready():
    """Modelin kullanima hazir olup olmadigini bildirir.

    Returns:
        bool
    """
    return _model is not None


def detect(frame):
    """Kare uzerinde nesne tespiti yapar.

    Model ilk cagrida yuklenir. Yukleme basarisiz olursa tekrar
    denenmez ve bos liste dondurulur.

    Takim (team) alani bu asamada UNKNOWN olarak birakilir; renk
    analizi ve balon eslestirmesi sonraki asamalarda yapilir.

    Args:
        frame: BGR NumPy dizisi

    Returns:
        (detections, inference_ms) — detections: sozluk listesi
    """
    global _model, _model_failed

    if _model is None:
        if _model_failed:
            return [], 0.0
        _model = load_model()
        if _model is None:
            _model_failed = True
            return [], 0.0

    start = time.perf_counter()

    try:
        if settings.USE_TRACKER:
            results = _model.track(
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
        else:
            results = _model.predict(
                frame,
                imgsz=settings.MODEL_IMGSZ,
                conf=settings.MODEL_CONF,
                iou=settings.MODEL_IOU,
                max_det=settings.MODEL_MAX_DET,
                device=settings.MODEL_DEVICE,
                verbose=False,
            )
    except Exception:
        log.exception("Cikarim hatasi")
        return [], 0.0

    inference_ms = (time.perf_counter() - start) * 1000
    detections = _parse_results(results, frame.shape)

    return detections, inference_ms


def _parse_results(results, frame_shape):
    """Ultralytics sonuclarini protokol formatina cevirir.

    Gercekci olmayan boyuttaki kutular elenir: cok buyuk kutular
    genellikle karmasik arka plandan kaynaklanan yanlis pozitiflerdir.

    Args:
        results: model.predict() ciktisi
        frame_shape: Kare boyutu (yukseklik, genislik, kanal)

    Returns:
        list[dict] — protokol formatinda tespitler
    """
    detections = []

    if not results:
        return detections

    boxes = results[0].boxes
    if boxes is None or len(boxes) == 0:
        return detections

    frame_area = frame_shape[0] * frame_shape[1]

    for i in range(len(boxes)):
        x1, y1, x2, y2 = boxes.xyxy[i].tolist()
        model_cls = int(boxes.cls[i].item())
        conf = float(boxes.conf[i].item())
        model_cls = int(boxes.cls[i].item())
        conf = float(boxes.conf[i].item())

        # ByteTrack track_id atar; takipci kapaliysa veya iz henuz
        # onaylanmadiysa None olabilir.
        if boxes.id is not None:
            track_id = int(boxes.id[i].item())
        else:
            track_id = -1

        box_area = (x2 - x1) * (y2 - y1)
        ratio = box_area / frame_area

        if ratio > settings.MODEL_MAX_BOX_RATIO:
            log.debug("Kutu elendi (cok buyuk): sinif=%s oran=%.3f conf=%.2f",
                      _model.names.get(model_cls, "?"), ratio, conf)
            continue

        if ratio < settings.MODEL_MIN_BOX_RATIO:
            log.debug("Kutu elendi (cok kucuk): oran=%.4f", ratio)
            continue

        protocol_cls = settings.MODEL_CLASS_MAP.get(model_cls)
        if protocol_cls is None:
            log.warning("Bilinmeyen model sinifi: %d", model_cls)
            continue

        detections.append({
            "id": track_id,
            "x": int(x1),
            "y": int(y1),
            "w": int(x2 - x1),
            "h": int(y2 - y1),
            "cls": protocol_cls,
            "team": Team.UNKNOWN,
            "conf": round(conf, 2),
            "parent_id": None,
        })

    return detections