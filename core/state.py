"""Paylasilan sistem durumu.

Tum katmanlarin eristigi merkezi durum: parametre katalogu, anlik degerler
ve komut kuyrugu. Katmanlar birbirini degil bu modulu tanir.

PARAM_DEFS      Parametrelerin statik tanimlari. Calisma sirasinda degismez.
PARAM_VALUES    Anlik degerler. SET ile veya sistem tarafindan guncellenir.
COMMAND_QUEUE   Tetikleyici parametrelerden dogan komutlar. Protokol katmani
                yazar, kontrol dongusu tuketir.

Tanim alanlari:
    type     Python tipi (int, float, str)
    access   core.enums.Access degerlerinden biri
    min/max  Sayisal sinirlar
    unit     Birim, arayuzde gosterilir
    desc     Aciklama
    trigger  (opsiyonel) True ise deger saklanmaz, komut kuyruguna alinir

Yeni parametre eklemek icin PARAM_DEFS ve PARAM_VALUES birlikte
guncellenmelidir; protokol katmanina dokunulmaz.

Katalogun resmi kaynagi: docs/protocol_spec.md, Bolum 9
"""

from queue import Queue

from config import settings
from core.enums import Access

# ---------------------------------------------------------------------------
# Komut kuyrugu
# ---------------------------------------------------------------------------

# Tetikleyici parametrelerden dogan komutlar buraya birakilir.
# Eleman yapisi: {"action": str, "value": Any, "ts": float}
#
# Kuyrugu tuketmek kontrol dongusunun sorumlulugundadir. Tuketilmezse
# kuyruk dolar ve yeni komutlar INTERNAL_ERROR ile reddedilir.
COMMAND_QUEUE = Queue(maxsize=settings.COMMAND_QUEUE_SIZE)


# ---------------------------------------------------------------------------
# Parametre katalogu
# ---------------------------------------------------------------------------

PARAM_DEFS = {

    # --- Kontrol ----------------------------------------------------------

    "control.pid.kp": {
        "type": float,
        "access": Access.RW, 
        "min": 0.0,
        "max": 10.0,
        "unit": "",
        "desc": "PID oransal kazanc",
    },

#eklendi
    # --- Sistem modu ve baglanti --------------------------------------

    "system.mode": {
        "type": int,
        "access": Access.RW,
        "min": 0,
        "max": 4,
        "unit": "",
        "desc": "Sistem modu (0=IDLE,1=MANUAL,2=AUTO,3=LOOP_DEMO,4=ESTOP)",
    },
    "system.link": {
        "type": int,
        "access": Access.RO,
        "min": 0,
        "max": 2,
        "unit": "",
        "desc": "Arduino baglanti durumu (0=KOPUK,1=BAGLI,2=TIMEOUT)",
    },

    # --- Manuel hareket (WASD) ------------------------------------------
    # GUI, tus basiliyken 1, birakildiginda 0 gonderir. Surekli SET yerine
    # her key-down/key-up olayinda bir kez SET beklenir.

    "motion.manual.up": {
        "type": int, "access": Access.RW, "min": 0, "max": 1,
        "unit": "", "desc": "W basili (tilt yukari)",
    },
    "motion.manual.down": {
        "type": int, "access": Access.RW, "min": 0, "max": 1,
        "unit": "", "desc": "S basili (tilt asagi)",
    },
    "motion.manual.left": {
        "type": int, "access": Access.RW, "min": 0, "max": 1,
        "unit": "", "desc": "A basili (pan sola)",
    },
    "motion.manual.right": {
        "type": int, "access": Access.RW, "min": 0, "max": 1,
        "unit": "", "desc": "D basili (pan saga)",
    },




    # --- Analog hareket (oyun kolu / otonom) ----------------------------
    # -1.0 ile 1.0 arasi. Yon VE buyukluk tasir; sifir dur demektir.
    # Bu parametreler yazildiginda sistem bitmask yerine mutlak aci
    # cercevesi gonderir.

    "motion.analog.pan": {
        "type": float, "access": Access.RW, "min": -1.0, "max": 1.0,
        "unit": "", "desc": "Yatay analog girdi (- sol, + sag)",
    },
    "motion.analog.tilt": {
        "type": float, "access": Access.RW, "min": -1.0, "max": 1.0,
        "unit": "", "desc": "Dikey analog girdi (- asagi, + yukari)",
    },
    "motion.analog.precision": {
        "type": int, "access": Access.RW, "min": 0, "max": 1,
        "unit": "", "desc": "Hassas mod (1=acik, hizlar dusurulur)",
    },

    # --- Sunum modu -----------------------------------------------------
    # LOOP_DEMO'da calisacak hareket duzeni. Mod degismeden de yazilabilir;
    # sunum sirasinda degisirse yeni duzen taretin bulundugu yerden
    # baslar.

    "motion.demo.pattern": {
        "type": int, "access": Access.RW, "min": 0, "max": 1,
        "unit": "", "desc": "Sunum hareket duzeni (0=tarama+capraz, 1=elips)",
    },

    # Pan ekseninin fiziksel gecikmesinin telafisi. Elips donerken
    # degistirilebilir ve yumusakca uygulanir; taret basinda ayarlanip
    # bulunan deger settings.DEMO_ELLIPSE_PAN_LEAD_S'e yazilir.
    "motion.demo.pan_lead": {
        "type": float, "access": Access.RW, "min": -1.0, "max": 1.0,
        "unit": "s", "desc": "Elipste pan'in tilt'ten onde surulme suresi",
    },






    # --- Sistem durumu ----------------------------------------------------

    "system.fps": {
        "type": float,
        "access": Access.RO,
        "min": 0.0,
        "max": 200.0,
        "unit": "fps",
        "desc": "Anlik isleme hizi",
    },

    # --- Silah ------------------------------------------------------------

    "weapon.armed": {
        "type": int,
        "access": Access.RW,
        "min": 0,
        "max": 1,
        "unit": "",
        "desc": "Ates yetkisi (0=kapali, 1=acik)",
    },
    "weapon.fire_mode": {
        "type": int,
        "access": Access.RW,
        "min": 0,
        "max": 1,
        "unit": "",
        "desc": "Atis modu (0=tekli, 1=seri)",
    },
    "weapon.burst_count": {
        "type": int,
        "access": Access.RW,
        "min": 1,
        "max": 10,
        "unit": "adet",
        "desc": "Seri atis mermi sayisi",
    },
    "weapon.selected": {
        "type": int,
        "access": Access.RW,
        "min": 0,
        "max": 2,
        "unit": "",
        "desc": "Secili namlu (0=sol, 1=sag, 2=her ikisi)",
    },
    "weapon.ammo": {
        "type": int,
        "access": Access.RO,
        "min": 0,
        "max": 100,
        "unit": "adet",
        "desc": "Kalan mermi",
    },
    "weapon.shots_fired": {
        "type": int,
        "access": Access.RO,
        "min": 0,
        "max": 9999,
        "unit": "adet",
        "desc": "Toplam atilan mermi",
    },
    "weapon.fire": {
        "type": int,
        "access": Access.WRO,
        "min": 0,
        "max": 1,
        "unit": "",
        "desc": "Ates tetikleyici",
        "trigger": True,
    },
    # --- Renk analizi: dusman (kirmizi) -----------------------------------

    "vision.enemy.h_min": {
        "type": int, "access": Access.RW, "min": 0, "max": 179,
        "unit": "", "desc": "Dusman renk alt ton esigi (kirmizi, alt aralik)",
    },
    "vision.enemy.h_max": {
        "type": int, "access": Access.RW, "min": 0, "max": 179,
        "unit": "", "desc": "Dusman renk ust ton esigi (kirmizi, alt aralik)",
    },
    "vision.enemy.h_min2": {
        "type": int, "access": Access.RW, "min": 0, "max": 179,
        "unit": "", "desc": "Dusman renk alt ton esigi (kirmizi, ust aralik)",
    },
    "vision.enemy.h_max2": {
        "type": int, "access": Access.RW, "min": 0, "max": 179,
        "unit": "", "desc": "Dusman renk ust ton esigi (kirmizi, ust aralik)",
    },
    "vision.enemy.s_min": {
        "type": int, "access": Access.RW, "min": 0, "max": 255,
        "unit": "", "desc": "Dusman renk minimum doygunluk",
    },
    "vision.enemy.v_min": {
        "type": int, "access": Access.RW, "min": 0, "max": 255,
        "unit": "", "desc": "Dusman renk minimum parlaklik",
    },

    # --- Renk analizi: dost (camgobegi) -----------------------------------

    "vision.friend.h_min": {
        "type": int, "access": Access.RW, "min": 0, "max": 179,
        "unit": "", "desc": "Dost renk alt ton esigi (camgobegi)",
    },
    "vision.friend.h_max": {
        "type": int, "access": Access.RW, "min": 0, "max": 179,
        "unit": "", "desc": "Dost renk ust ton esigi (camgobegi)",
    },
    "vision.friend.s_min": {
        "type": int, "access": Access.RW, "min": 0, "max": 255,
        "unit": "", "desc": "Dost renk minimum doygunluk",
    },
    "vision.friend.v_min": {
        "type": int, "access": Access.RW, "min": 0, "max": 255,
        "unit": "", "desc": "Dost renk minimum parlaklik",
    },

    # --- Tespit ayarlari --------------------------------------------------

    "vision.conf_threshold": {
        "type": float, "access": Access.RW, "min": 0.0, "max": 1.0,
        "unit": "", "desc": "Minimum tespit guven esigi",
    },
    "vision.detection_count": {
        "type": int, "access": Access.RO, "min": 0, "max": 100,
        "unit": "adet", "desc": "Son karedeki tespit sayisi",
    },
    "vision.inference_ms": {
        "type": float, "access": Access.RO, "min": 0.0, "max": 10000.0,
        "unit": "ms", "desc": "Model cikarim suresi",
    },

        # --- Otonom hareket -------------------------------------------------

    "motion.auto.pan": {
        "type": float, "access": Access.RO, "min": -1.0, "max": 1.0,
        "unit": "", "desc": "Otonom yatay girdi",
    },
    "motion.auto.tilt": {
        "type": float, "access": Access.RO, "min": -1.0, "max": 1.0,
        "unit": "", "desc": "Otonom dikey girdi",
    },
    "system.pan_angle": {
        "type": float, "access": Access.RO,
        "min": 0.0, "max": 180.0, "unit": "deg",
        "desc": "Taret pan hedef acisi",
    },
    "system.tilt_angle": {
        "type": float, "access": Access.RO,
        "min": 0.0, "max": 180.0, "unit": "deg",
        "desc": "Taret tilt hedef acisi",
    },
    "vision.aim_error_x": {
        "type": float, "access": Access.RO,
        "min": -4000.0, "max": 4000.0, "unit": "px",
        "desc": "Nisan noktasinin merkeze yatay uzakligi",
    },
    "vision.aim_error_y": {
        "type": float, "access": Access.RO,
        "min": -4000.0, "max": 4000.0, "unit": "px",
        "desc": "Nisan noktasinin merkeze dikey uzakligi",
    },

    "engage.track_id":   {"type": int, "access": Access.RO, "min": -1, "max": 100000,
                          "unit": "", "desc": "Kilitli iz kimligi (-1 = yok)"},
    "engage.locked":     {"type": int, "access": Access.RO, "min": 0, "max": 1,
                          "unit": "", "desc": "Kilit LOCKED durumunda mi"},
    "engage.reacquires": {"type": int, "access": Access.RO, "min": 0, "max": 100000,
                          "unit": "", "desc": "Yeniden eslestirme sayisi"},

    "control.ff_pan":  {"type": float, "access": Access.RO,
                        "min": -1.0, "max": 1.0, "unit": "",
                        "desc": "Ileri besleme pan katkisi"},
    "control.ff_tilt": {"type": float, "access": Access.RO,
                        "min": -1.0, "max": 1.0, "unit": "",
                        "desc": "Ileri besleme tilt katkisi"},

}


# ---------------------------------------------------------------------------
# Anlik degerler
# ---------------------------------------------------------------------------

PARAM_VALUES = {
    "control.pid.kp": 1.8,
    "system.mode": 0,          # IDLE
    "system.link": 0,          # KOPUK

    "motion.manual.up": 0,
    "motion.manual.down": 0,
    "motion.manual.left": 0,
    "motion.manual.right": 0,

    "motion.analog.pan": 0.0,   #sonradan eklendi
    "motion.analog.tilt": 0.0,
    "motion.analog.precision": 0,

    "motion.demo.pattern": 0,   # 0=tarama+capraz, 1=elips
    "motion.demo.pan_lead": float(settings.DEMO_ELLIPSE_PAN_LEAD_S),


    "system.fps": 0.0,
    "weapon.armed": 0,
    "weapon.fire_mode": 0,
    "weapon.burst_count": 3,
    "weapon.selected": 0,
    "weapon.ammo": 30,
    "weapon.shots_fired": 0,
    "weapon.fire": 0,

    "vision.enemy.h_min": 0,
    "vision.enemy.h_max": 10,
    "vision.enemy.h_min2": 170,
    "vision.enemy.h_max2": 179,
    "vision.enemy.s_min": 100,
    "vision.enemy.v_min": 80,

    "vision.friend.h_min": 60,
    "vision.friend.h_max": 130,
    "vision.friend.s_min": 70,
    "vision.friend.v_min": 50,

    "vision.conf_threshold": 0.35,
    "vision.detection_count": 0,
    "vision.inference_ms": 0.0,

    "motion.auto.pan": 0.0,
    "motion.auto.tilt": 0.0,

    "system.pan_angle": 0.0,
    "system.tilt_angle": 0.0,

    "vision.aim_error_x": 0.0,
    "vision.aim_error_y": 0.0,

    "engage.track_id": -1,
    "engage.locked": 0,
    "engage.reacquires": 0,
    "control.ff_pan": 0,
    "control.ff_tilt": 0,
}