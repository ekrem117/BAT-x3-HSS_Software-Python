"""Proje genelinde kullanilan sabitler.

Port, cozunurluk, baud gibi degerleri degistirmek icin tum kod tabaninda
yalnizca bu dosya guncellenir. Hicbir proje modulunu import etmez.

Bu dosya yarisma/uretim ayarlarini tasir. Gelistirme sirasinda gecici
degisiklik gerekiyorsa (kamera yokken calistirma, Arduino bagli degilken
test) config/local_settings.py kullanilmalidir; bu dosya git'e dahil
edilmez ve dosyanin sonunda otomatik yuklenir.
"""

# ---------------------------------------------------------------------------
# Seri baglanti (ESP32 / Arduino)
# ---------------------------------------------------------------------------

SERIAL_PORT = "COM5"          # Windows: "COM5" | Linux: "/dev/ttyACM0"
BAUD_RATE = 115200
SERIAL_TIMEOUT = 0.05

# Ardisik atislar arasi minimum sure
# (firmware TRIGGER_HOLD_MS=250 + donus suresi)
FIRE_COOLDOWN_S = 0.6

# ---------------------------------------------------------------------------
# Arayuz haberlesmesi (C# <-> Python)
# ---------------------------------------------------------------------------

# "0.0.0.0" tum arayuzlerden gelen istekleri kabul eder.
# Yalnizca ayni bilgisayardan baglanilacaksa "127.0.0.1" daha guvenlidir.
COMMAND_UDP_HOST = "127.0.0.1"
COMMAND_UDP_PORT = 5005       # GET/SET dinleme portu

TARGET_IP = "127.0.0.1"       # Yayin hedefi (arayuz)
VIDEO_PORT = 5007             # Video yayini
DETECTION_PORT = 5008         # Tespit yayini

MJPEG_HOST = "0.0.0.0"
MJPEG_PORT = 8080             # Tarayici tani sunucusu

UDP_BUFFER_SIZE = 65535
SEND_BUFFER_SIZE = 4 * 1024 * 1024
RECV_BUFFER_SIZE = 4 * 1024 * 1024

COMMAND_QUEUE_SIZE = 100

# ---------------------------------------------------------------------------
# Kamera ve kare
# ---------------------------------------------------------------------------

FRAME_WIDTH = 1920
FRAME_HEIGHT = 1080
# Yayin cozunurlugu. Yakalama cozunurlugunden bagimsizdir: model yuksek
# cozunurluklu kareyi kullanirken arayuze kucultulmus kare gonderilir.
# Boylece tespit dogrulugu korunur ve UDP datagram siniri asilmaz.
#
# Tespit koordinatlari kaynak cozunurluktedir; alici taraf video paketi
# basligindaki width/height alanlarina gore olcekler.
STREAM_WIDTH = 1280
STREAM_HEIGHT = 720
TARGET_FPS = 30
FRAME_INTERVAL = 1.0 / TARGET_FPS

# Yayin hizi. Yakalama hizindan BAGIMSIZ: cikarim ~20 Hz oldugu icin
# video daha yavas yayinlanmalidir, aksi halde arayuz her kareye
# tespit bulamaz ve etiketler yanip soner.
STREAM_FPS = 30
STREAM_INTERVAL = 1.0 / STREAM_FPS

USE_CAMERA = True
CAMERA_INDEX = 1

# Pozlama sabitleme — otomatik pozlama HSV renk esiklerini kaydirir ve
# dost/dusman ayrimini bozar (gereksinim GI-12).
LOCK_EXPOSURE = True
EXPOSURE_VALUE = -5
CAMERA_GAIN = 64        # Brio'da aralik genelde 0-255

# ---------------------------------------------------------------------------
# Video kodlama
# ---------------------------------------------------------------------------

JPEG_QUALITY = 80
MAX_JPEG_BYTES = 60000        # UDP datagram siniri icin 960guvenlik payli ust sinir
MIN_JPEG_QUALITY = 40
JPEG_QUALITY_STEP = 10

# ---------------------------------------------------------------------------
# Video paket protokolu
# ---------------------------------------------------------------------------

VIDEO_MAGIC = b"BX3F"
VIDEO_HEADER_FORMAT = "<4sIdIHH"
MJPEG_BOUNDARY = "frame"

# ---------------------------------------------------------------------------
# Bilesen anahtarlari
# ---------------------------------------------------------------------------

ENABLE_CONTROL = True         # Kontrol katmani (SystemManager + ParamBridge)
ENABLE_COMMAND_SERVER = True  # GET/SET sunucusu
ENABLE_VIDEO = True           # UDP video yayini
ENABLE_DETECTIONS = True      # Cikarim ve tespit yayini
ENABLE_MJPEG = True           # Tarayici tani sunucusu
ENABLE_TRACKING_LOOP = True   # Takip ve angajman dongusu

# ---------------------------------------------------------------------------
# Gelistirme
# ---------------------------------------------------------------------------

# Kare uzerine kare numarasi ve canlilik gostergesi cizer.
# Yarismada False olmalidir: gercek goruntude tespit dogrulugunu bozar ve
# arayuz tarafindaki overlay ile cakisir.
DEBUG_OVERLAY = False

# ---------------------------------------------------------------------------
# Zamanlama
# ---------------------------------------------------------------------------

IDLE_SLEEP = 0.002            # Yeni kare beklerken kisa uyku
REPORT_INTERVAL = 5.0         # Istatistik loglama araligi (saniye)
SHUTDOWN_TIMEOUT = 3.0        # Thread durma bekleme suresi

# ---------------------------------------------------------------------------
# Nesne tespiti (YOLO)
# ---------------------------------------------------------------------------

USE_YOLO = True               # False ise sentetik tespit ureticisi kullanilir
MODEL_PATH = "models/best_v5.pt" #bbest_final.pt ve best_final.pt3 iyi
MODEL_IMGSZ = 1280

# Dusuk esik bilinclidir: ByteTrack iki asamali eslestirme yapar ve dusuk
# guvenli kutulari kayip izleri kurtarmak icin kullanir. Gercek filtreleme
# tracker config'teki track_high_thresh ve TRACK_MIN_CONFIDENCE ile yapilir.
#
# 0.25 idi. botsort.yaml'daki new_track_thresh=0.35 ile arasinda bir
# olu bolge vardi: 0.25-0.35 arasi guvenle gelen bir tespit modelde
# gorunuyor ama izleyici ona yeni iz acmiyordu (new_track_thresh
# altinda), track_store.update() bunu hicbir log basmadan atiyordu.
# 0.30'a cekilerek bolge daraltildi; tamamen kapatilmadi cunku dusuk
# esigin kendisi bilincli (yukaridaki not) — cok yukseltmek kayip
# izleri kurtarma mekanizmasini bozar.
MODEL_CONF = 0.30

MODEL_IOU = 0.45              # NMS ortusme esigi
MODEL_DEVICE = None           # None=otomatik, "cpu", "cuda:0"
MODEL_MAX_DET = 20            # Kare basina maksimum tespit

# Kutu alan filtreleri — karmasik arka plandan kaynaklanan yanlis
# pozitifleri eler.
#
# DIKKAT: 0.60 degeri yakin mesafeli masa ustu testler icin gevsetilmistir.
# Yarisma ortaminda hedefler 5-15 m mesafede olacak ve karenin en fazla
# %5'ini kaplayacaktir; o asamada 0.25'e cekilmelidir.
MODEL_MAX_BOX_RATIO = 0.60
MODEL_MIN_BOX_RATIO = 0.00003

INFERENCE_IDLE_SLEEP = 0.002  # Yeni kare beklerken uyku

# Model sinif indeksinden protokol sinif koduna esleme.
# Mevcut model ['drone', 'f16', 'fuze', 'heli', 'balon'] sirasiyla
# egitilmistir ve protokol kodlari bu siraya gore tanimlanmistir
# (core.enums.TargetClass). Bu nedenle esleme kimlik donusumudur.
#
# Farkli sirada egitilmis bir model kullanilirsa yalnizca bu tablo
# guncellenir; kod degistirilmez.
MODEL_CLASS_MAP = {
    0: 0,   # drone
    1: 1,   # f16
    2: 2,   # fuze
    3: 3,   # heli
    4: 4,   # balon
}

# ---------------------------------------------------------------------------
# Takip (ByteTrack / BoT-SORT)
# ---------------------------------------------------------------------------

USE_TRACKER = True
TRACKER_CONFIG = "config/botsort.yaml"

# ---------------------------------------------------------------------------
# Dost/dusman renk analizi
# ---------------------------------------------------------------------------

USE_COLOR_CLASSIFIER = True

# Sartname renkleri:
#   Dusman  Kirmizi     #F50A0A  -> OpenCV HSV H≈0
#   Dost    Camgobegi   #00A3E0  -> OpenCV HSV H≈98
#
# Kirmizi H cemberinin basinda oldugu icin iki aralik gerekir.
# Esikler core.state uzerinden calisma sirasinda ayarlanabilir.

COLOR_ROI_RATIO = 0.6         # BBox'in merkez orani (arka plani dislar)
COLOR_MIN_PIXEL_RATIO = 0.15  # Karar icin gereken minimum piksel orani

# ---------------------------------------------------------------------------
# Hareket modeli (Kalman filtresi)
# ---------------------------------------------------------------------------

# Baslangic belirsizlikleri (varyans)
KF_INIT_POS_VAR = 100.0       # Konum: ilk olcum makul dogrulukta
KF_INIT_VEL_VAR = 10000.0     # Hiz: baslangicta hicbir bilgi yok

# Surec gurultusu — hedefin sabit hiz modelinden sapma egilimi.
# Yuksek deger: manevra yapan hedefi hizli takip eder, ancak tahmin
# gurultulu olur. Dusuk deger: yumusak tahmin, manevrada geride kalir.
KF_PROCESS_NOISE = 8000.0

# Olcum gurultusu — YOLO kutu merkezinin titremesi (varyans, piksel^2).
# Yuksek deger: olcume az guvenir, tahmini yumusatir.
KF_MEAS_VAR = 30.0 

# ---------------------------------------------------------------------------
# Iz yonetimi
# ---------------------------------------------------------------------------

# Iz onaylanmadan once gereken tespit sayisi. Tek karelik yanlis
# pozitiflerin angajmana girmesini engeller.
TRACK_MIN_HITS = 2

# Yayina ve angajmana girecek izler icin minimum guven. MODEL_CONF
# dusuk tutuldugu icin asil filtreleme burada yapilir.
TRACK_MIN_CONFIDENCE = 0.35

# Tespit gelmeden izin yasatilacagi sure (saniye). Bu sure boyunca
# konum tahmin edilmeye devam eder; angajman katmani yeniden
# eslestirme icin bu tahminleri kullanir.
TRACK_MAX_AGE = 0.8

# Bu sureden daha eski olan izler "tahmin edilmis" olarak isaretlenir.
# Arayuz bunlari farkli gosterebilir.
TRACK_FRESH_WINDOW = 0.15

# ---------------------------------------------------------------------------
# Takip ve angajman dongusu
# ---------------------------------------------------------------------------


CONTROL_LOOP_HZ = 50.0        # Arduino komut gonderim hizi

# Senin bolumun
TRACKING_LOOP_HZ = 50         # Takip/angajman dongusu hizi

# Angajman yokken otomatik hedef secimi. Tehdit onceliklendirmesi
# eklenene kadar test amaclidir.
AUTO_LOCK = True

# ---------------------------------------------------------------------------
# Angajman
# ---------------------------------------------------------------------------

# Kilitli izin "olu" sayilmasi icin gereken sure. TRACK_MAX_AGE'den
# belirgin sekilde kisa olmalidir: takipci ID'yi dusurdugunde angajman
# hemen yeniden eslestirme aramasina baslamalidir. Uzun beklemek Kalman
# tahmininin gercek konumdan sapmasina ve eslesmenin kacirilmasina yol
# acar.
ENGAGE_TRACK_STALE = 0.5    # 0.5 idi

# Kilitli hedef izi dustugunde vazgecilmeden once beklenecek sure.
# Bu sure boyunca konum Kalman ile tahmin edilir ve yeni izlerle
# yeniden eslestirme denenir.
ENGAGE_LOST_TIMEOUT = 2.5

# Yeniden eslestirmede taban arama yaricapi (piksel). Gercek yaricap
# Kalman belirsizligi ve hedef hiziyla olceklenir.
ENGAGE_REACQUIRE_RADIUS = 120.0

# Belirsizlik olcekleme carpani. Yuksek deger daha gevsek eslestirme.
ENGAGE_UNCERTAINTY_SCALE = 2.0

# Yeniden eslestirmede sinif ve takim uyumu aranir. Renk analizi
# kararsizsa takim kontrolu devre disi birakilabilir.
ENGAGE_MATCH_CLASS = True
ENGAGE_MATCH_TEAM = True

# Imha teyidi: kilitli hedef bu sure boyunca hic gorulmezse ve atis
# yapilmissa imha edilmis sayilir.
ENGAGE_KILL_CONFIRM_TIME = 1.5

# Hedefe bu kadar atis yapildigi halde imha teyidi gelmezse hedef
# iskalanmis sayilir ve siradaki hedefe gecilir.
ENGAGE_MAX_SHOTS = 6

# ---------------------------------------------------------------------------
# Mesafe kestirimi
# ---------------------------------------------------------------------------

# Kamera goruş alani (derece). Logitech Brio: 65 / 78 / 90.
# Deger Logitech Camera Settings uygulamasindan ayarlanir; buradaki
# deger kameradaki ayarla ayni olmalidir.
CAMERA_FOV_DEG = 78.0

# Logitech FOV degerlerini capraz (diagonal) olarak belirtir.
# Yatay FOV bilinen bir kamera icin False yapilmalidir.
CAMERA_FOV_IS_DIAGONAL = True

# Ampirik duzeltme carpani. Bilinen mesafede olcum yapip
# gercek_mesafe / hesaplanan_mesafe orani buraya yazilir.
# Nominal FOV degerleri lens toleransi nedeniyle sapabilir.
RANGE_CALIBRATION_FACTOR = 1.0

# Hedeflerin gercek boyutlari (metre). Sartname Tablo 1.
#
# Maketler yonelime gore farkli genislikte gorunur; bu nedenle
# mesafe kestiriminde oncelik balona verilir. Balon kuredir ve
# her acidan ayni capta gorunur.
#
# UYARI: 14 cm balon 15 m mesafede yalnizca ~8 piksel kaplar. Bu
# boyutta mesafe kestirimi hatasi yuksek, tespit guvenilirligi
# dusuktur. Yarisma oncesi 15 m'de tespit performansi dogrulanmalidir.
TARGET_REAL_SIZE = {
    0: 0.30,    # drone
    1: 0.50,    # f16
    2: 0.40,    # fuze
    3: 0.50,    # heli
    4: 0.14,    # balon — capi olculerek dogrulanmalidir
}

# Mesafe kestiriminde guvenilir sayilan siniflar. Balon disindaki
# hedeflerde yonelim hatasi buyuktur ve kestirim isaretlenir.
RANGE_RELIABLE_CLASSES = (4,)

# Menzil kusaklari (metre). Yarisma mesafeleri 5 / 10 / 15 m'dir;
# kusak siniri komsu mesafelerin ortasindan gecer.
RANGE_BAND_LIMITS = (7.5, 12.5, 18.0)

# Gecerli mesafe araligi. Bu araligin disindaki kestirimler
# guvenilmez sayilir.
RANGE_MIN_M = 1.0
RANGE_MAX_M = 25.0

# ---------------------------------------------------------------------------
# Sunum modu (LOOP_DEMO)
# ---------------------------------------------------------------------------
#
# control/loop_demo.py koreografisinin konum ve hiz ayarlari. Yorunge
# Python'da hesaplanir ve mutlak aci cercevesiyle gonderilir: capraz
# hareketler duz cizgidir, hiz yol boyunca sabittir, kalkis ve durus
# yumusaktir. Ayrintili gerekce modul aciklamasindadir.
#
# Bu blok local_settings yuklemesinden ONCE durur; boylece sergi
# sirasinda config/local_settings.py ile ayarlanabilir.

# Hareket kutusunun kenarlari (taret birimi). Yon esleme firmware ile
# aynidir: SOL = pan acisi BUYUK, SAG = KUCUK; YUKARI = tilt acisi
# BUYUK, ASAGI = KUCUK.
#
# Eksen sinirlarinin (PAN_*/TILT_*_DEG) birkac derece ICINDE secilir.
# Tam sinira giden yorunge, Python ve firmware sinirlari farkliysa
# taretin durdugu ama komutun ilerledigi bir bolum uretir; hareket orada
# takiliyormus gibi gorunur. Varsayilanlar her eksende sinirin 3 birim
# icindedir.
DEMO_PAN_LEFT_DEG = 97.0
DEMO_PAN_RIGHT_DEG = 43.0
DEMO_TILT_LOW_DEG = 118.0
DEMO_TILT_HIGH_DEG = 147.0

# Yol boyunca sabit hiz (taret birimi/s). Capraz harekette de ayni hiz
# gecerlidir; eksenler hizi yolun egimine gore paylasir.
#
# Cok dusuk secilmemelidir: tilt ekseni kucuk komut degisimlerinde
# takilip sicriyor (bkz. ANALOG_STEP_TILT_*_DEG). 25 birim/s'de capraz
# harekette bile tilt ~12 birim/s ile ilerler; sorunun gozlendigi hassas
# mod hizinin (1.5) cok uzerindedir. Tilt takiliyorsa cozum filtre
# eklemek degil hizi artirmaktir.
DEMO_SPEED_DPS = 75.0

# Hizlanma ve yavaslama suresi (s). Hiz bu surede kosinus egrisiyle
# sifirdan DEMO_SPEED_DPS'e cikar; koselerde sarsinti olmaz. Kisa bir
# harekete iki rampa sigmazsa tepe hiz otomatik dusurulur.
DEMO_RAMP_S = 0.3

# Her noktada bekleme (s). Hareketleri gozle birbirinden ayirir ve
# servonun komuta yetismesine zaman tanir.
DEMO_DWELL_S = 0.3

# Elips duzeninin (V) ORTALAMA yol hizi (taret birimi/s). Tarama
# hizindan (DEMO_SPEED_DPS) ayridir; elipse giris hareketi
# DEMO_SPEED_DPS ile yapilir.
#
# Her eksen saf sinusle surulur (gerekce: control/loop_demo.py,
# _EllipseLap): hiz tepede/dipte ortalamanin ~1.3 kati, sag/sol
# uclarda ~0.7 katidir. Varsayilan kutuda cevre ~133 birimdir.
#
#   hiz   tur     pan uclarinda ivme   tilt'in yavas bolgesi (donus basina)
#   45    3.0 s   ~120 birim/s^2       ~0.31 s
#   60    2.2 s   ~215 birim/s^2       ~0.17 s
#   75    1.8 s   ~340 birim/s^2       ~0.11 s
#
# "Yavas bolge": tilt hizinin 10 birim/s'nin altinda kaldigi sure; bu
# bolgede tilt takilip sicramaya yatkindir. Hizlandirmak onu kisaltir
# ama pan'in uclarda donusunu sertlestirir (ivme hizin karesiyle artar).
DEMO_ELLIPSE_SPEED_DPS = 60.0

# Elipste pan'in tilt'ten ne kadar ONDE surulecegi (s). Sahada pan
# ekseni komutun gerisinde kaliyordu: tilt tepeye vardiginda pan henuz
# ortaya gelmemis, donuste tilt dibe indiginde pan henuz donmemis
# oluyordu (2026-09-15). Komutta iki eksen tam senkrondu; kayma
# fizikseldir (agir taret, disli boslugu, surtunme). Pan komutu bu kadar
# erken verilince fiziksel hareket hizalanir; tilt'e dokunulmaz.
#
# AYAR (taret basinda, main.py calisirken):
#   1. Klavye aracinda V ile elipsi baslat.
#   2. 1 / 2 tuslariyla degeri canli azalt / artir (0.02 s adim).
#   3. Dogru deger: tilt TAM TEPEDEYKEN pan TAM ORTADA (HOME_PAN_DEG
#      hizasi), tilt tam dipteyken yine tam ortada. Pan ortaya gec
#      variyorsa artir, erken variyorsa azalt.
#   4. Arac ekrana yazdigi degeri buraya yaz; yeniden baslatinca
#      buradan okunur.
#
# 0.2 baslangic tahminidir (gozlenen kayma 0.2-0.4 s gecikmeye denk).
# Gecikme hizla degisebilir: DEMO_ELLIPSE_SPEED_DPS degisirse yeniden
# ayarla.
DEMO_ELLIPSE_PAN_LEAD_S = 0.2

# ---------------------------------------------------------------------------
# Yerel gecersiz kilma
# ---------------------------------------------------------------------------
#
# config/local_settings.py varsa yukaridaki degerlerin uzerine yazar.
# Bu dosya git'e dahil edilmez; her gelistirici kendi test ortamina gore
# ayar yapabilir ve ortak ayarlar surekli cakismaz.
#
# Ornek config/local_settings.py:
#     ENABLE_CONTROL = False        # Arduino bagli degil
#     CAMERA_INDEX = 1              # Farkli kamera indeksi

try:
    from config.local_settings import *   # noqa: F401,F403
except ImportError:
    pass




# ---------------------------------------------------------------------------
# Nisan cozumu
# ---------------------------------------------------------------------------

# Uctan uca sistem gecikmesi (saniye). Hedefin bu kadar ilerideki
# konumuna nisan alinir.
#
# Bilesenler: kamera yakalama ~30 ms, cikarim sirasi ~50 ms, YOLO
# cikarimi 20-100 ms (GPU/CPU), seri+firmware ~20 ms, servo mekanigi
# 60-120 ms.
#
# Olculerek ayarlanmalidir: taret hedefin gerisinde kaliyorsa artirilir,
# onune geciyorsa azaltilir.
AIM_LEAD_TIME = 0.10

# Balon, maket kutusunun altinda bu oranda asagida AUTO_SMOOTHING.
# Deger maket yuksekliginin katidir; mesafeden bagimsizdir cunku
# kutu yuksekligi de mesafeyle olceklenir.
#
# Sahada olculmelidir: nisan artisi balonun uzerine gelene kadar
# ayarlanir.
AIM_BALLOON_OFFSET_ENABLED = True 
AIM_BALLOON_OFFSET_RATIO = 0.5

# Nisan hatasi bu degerin altindaysa hedefte sayilir; servo surulmez
# ve ates izni verilir. Kucuk deger hassas nisan ama titreme riski.
AIM_DEAD_ZONE_PX =18.0

# Balon sinif kodu — nisan kaydirmasi bu sinifta uygulanmaz.
BALLOON_CLASS = 4


# ---------------------------------------------------------------------------
# Balistik ve paralaks
# ---------------------------------------------------------------------------
#
# Kamera ve namlu ayni eksende degildir; ekrandaki nisangah ile merminin
# gittigi nokta ortusmez. Fark mesafeye baglidir: paralaks yakinda buyuk,
# mermi dususu uzakta buyuktur.

BALLISTIC_CORRECTION_ENABLED = False

# Kamera merceginin merkezinden namlu agzinin merkezine olan mesafe (metre).
#
# Iki namlu kameranin altinda simetrik yerlesiktir: her biri yatayda
# 20.82 mm, dikeyde 22.90 mm uzaktadir.
#
# SOL namlu kullanildigi icin yatay ofset negatiftir.
# Sag namlu icin +0.02082, iki namlu birden icin 0.0 kullanilir.
MUZZLE_OFFSET_X = -0.02082
MUZZLE_OFFSET_Y = 0.0229

# Mermi cikis hizi (m/s). KWC M11 ~120 m/s.
MUZZLE_VELOCITY = 95.0

# Sabit nisangah otelemesi (piksel). Namlu-kamera eksen paralelsizligi
# ve servo sifir noktasi kaymasi gibi mesafeden bagimsiz hatalari
# duzeltir. Atis testinden sonra ayarlanir.
#
# Isabet nisangahin saginda ise AIM_ZERO_X negatif,
# asagisinda ise AIM_ZERO_Y negatif girilir.
AIM_ZERO_X = -18.0
AIM_ZERO_Y =  27.0

# Mesafe kestirimi yoksa kullanilacak varsayilan mesafe (m).
BALLISTIC_DEFAULT_RANGE = 15.0

# ---------------------------------------------------------------------------
# Tehdit onceliklendirme
# ---------------------------------------------------------------------------
#
# Skor = (w_yakinlik * yakinlik + w_hiz * hiz + w_merkez * merkezlik) * guven
#
# Agirliklarin toplami 1.0 olmak zorunda degildir; goreli buyuklukleri
# onemlidir.

THREAT_W_PROXIMITY = 0.5      # Yakin hedef oncelikli
THREAT_W_SPEED = 0.3          # Hizli hedef daha az sure icinde kacar
THREAT_W_CENTRALITY = 0.2     # Merkeze yakin hedefe donmek hizlidir

# Yakinlik olcegi. Kutu alani orani karekoku bu carpanla olceklenir;
# 5 m mesafedeki bir maket yaklasik 1.0 skor almalidir.
THREAT_PROXIMITY_SCALE = 4.0

# Hiz referansi: kare genisliginin kaci kadar/saniye hiz 1.0 skor alir.
# 0.5 degeri "yarim ekran genisligi kadar saniyede" demektir.
THREAT_SPEED_REFERENCE = 0.5

# Balonu tespit edilemeyen maketlere kilitlenilmez. Balonu patlatilmis
# hedeflerin yeniden angajmana girmesini engeller.
#
# Model balon tespitinde zayifsa gecici olarak False yapilabilir; bu
# durumda imha teyidi de calismaz.
THREAT_REQUIRE_BALLOON = False

# ---------------------------------------------------------------------------
# Taret surme
# ---------------------------------------------------------------------------
#
# Firmware ikili yon bitleri kabul ettigi icin oransal kontrol yerine
# olu bantli bang-bang kontrol uygulanir. Titremeyi azaltmak icin
# darbe genisligi modulasyonu kullanilir.

# ---------------------------------------------------------------------------
# Taret surme (otonom)
# ---------------------------------------------------------------------------
#
# Nisan hatasi analog girdi oranina cevrilir; aci hesabi ve yumusatma
# SystemManager tarafinda yapilir. Boylece manuel kol ve otonom takip
# ayni hareket yolunu kullanir.

ENABLE_TURRET_DRIVE = True

# Bu piksel hatasi ve uzeri tam girdi (1.0) uretir. Kucuk deger hizli
# ama asimli, buyuk deger yumusak ama yavas tepki verir.
#
# 500 idi, kademeli 250->180->150'ye indirildi (31 Ağustos, gercek
# kamerayla dogrulandi: 150'de hizli VE stabil). 100'e kadar denendi
# ama fayda saglamadi - bkz. AUTO_RATE_FACTOR notu, asil hiz tavani
# orasiydi.
TURRET_FULL_INPUT_PX = 150.0

# Eksen yonleri. Taret ters yone donuyorsa isaret degistirilir.
# Not: ANALOG_PAN_SIGN / ANALOG_TILT_SIGN ile birlikte etki eder;
# ikisinden yalnizca birini degistirin.
TURRET_PAN_SIGN = 1.0
TURRET_TILT_SIGN = -1.0

# --- Otonom mod farklari ---
#
# Otonom hiz DOGRUDAN yazilmaz, analog hizlardan turetilir.
# system_manager.py._build_analog_payload_locked() is_auto=True dali:
#     pan_max  = ANALOG_PAN_RATE_DPS  * AUTO_RATE_FACTOR
#     tilt_max = ANALOG_TILT_RATE_DPS * AUTO_RATE_FACTOR
# Ayni formul control/turret_driver.py::_rate_to_input icinde TERS
# yonde de kullanilir (ileri beslemede aci hizini girdi oranina
# cevirirken); biri degisirse digeri de degismelidir.
#
# Ayri bir "AUTO hiz" sabiti YOKTUR. Eskiden AUTO_PAN_RATE_DPS /
# AUTO_TILT_RATE_DPS vardi ama hicbir yerde okunmuyordu; bunlarla
# yapilan ayar denemeleri etkisizdi ve "otonom hala yavas"
# gozleminin asil sebebiydi. Karisikligi onlemek icin silindiler.
#
# Dogrulanmis referans (31 Agustos, gercek kamera,
# TURRET_FULL_INPUT_PX=150):
#     ANALOG 25/18 * 0.43 -> pan 10.75, tilt 7.7 derece/s (hizli VE stabil)
# Manuel hizlar firmware'e gore 75/70'e cikarildigi icin carpan bu
# referansi koruyacak sekilde 0.14'te tutuldu:
#     ANALOG 75/70 * 0.14 -> pan 10.5, tilt 9.8 derece/s
# Pan referansla ayni; tilt ~%27 hizli, sahada dogrulanmali. Tilt
# asim yaparsa pan/tilt icin ayri carpan gerekir.
#
# UYARI: ANALOG_*_RATE_DPS degistirilirse otonom tavan da ayni oranda
# degisir. Manuel hizi ayarlarken bu carpani da yeniden hesapla.
AUTO_RATE_FACTOR = 0.14    # Azami hiz carpani (ANALOG_*_RATE_DPS uzerinden)
AUTO_USE_EXPO = False       # Takipte dogrusal tepki gerekir
AUTO_LEAD_TIME_S = 0.0      # AIM_LEAD_TIME zaten tahmin yapiyor


# ---------------------------------------------------------------------------
# Renk tabanli tespit (model yerine)
# ---------------------------------------------------------------------------
#
# USE_COLOR_DETECTOR = True yapildiginda YOLO yerine renk tespiti
# kullanilir. Model guvenilir olmadiginda kontrol zincirini (takip,
# angajman, nisan, taret surme) ayarlamak icin kullanilir.
#
# Cikti formati ayni oldugu icin ust katmanlar degismez.

USE_COLOR_DETECTOR = False

# Kare alanina gore minimum ve maksimum nesne boyutu.
# 0.0005 ~ 640 piksel (1280x720'de yaklasik 25x25 kutu)
COLOR_MIN_AREA_RATIO = 0.0005
COLOR_MAX_AREA_RATIO = 0.25

# En-boy orani filtresi. Balon kureseldir; 0.5-2.0 arasi tolerans
# kismen gorunen veya deforme olmus balonlari da kapsar.
COLOR_MIN_ASPECT = 0.5
COLOR_MAX_ASPECT = 2.0

# Kare basina en fazla kac nesne dondurulecegi (alana gore buyukten
# kucuge siralanir).
COLOR_MAX_TARGETS = 5

# ---------------------------------------------------------------------------
# Eksen limitleri
# ---------------------------------------------------------------------------

# Bu degerler firmware'deki PAN_MIN_DEG / PAN_MAX_DEG vb. ile BIREBIR
# eslesmek zorundadir. Firmware zaten kirpma yapar; Python tarafinda ayni
# kirpmayi yapmazsak hedef aci sinirin otesine kayar ve kol birakildiginda
# taret gecikmeli tepki verir.
PAN_MIN_DEG = 40.0
PAN_MAX_DEG = 100.0
TILT_MIN_DEG = 115.0
TILT_MAX_DEG = 150.0

HOME_PAN_DEG = 70.0
HOME_TILT_DEG =120.0

# ---------------------------------------------------------------------------
# Analog kontrol
# ---------------------------------------------------------------------------


# Servoya komut edilen aci, hedefin bu kadar sure ilerisi olarak
# gonderilir. Servo torku ic konum hatasiyla orantilidir; hedef yalnizca
# 0.3 derece ilerideyse servo neredeyse hic tork uretmez ve elle
# durdurulabilir. On gorus payi sayesinde eksen ayni hizda ilerler ama
# servo surekli belirgin bir hata gorur.
#
# Pay hizla orantilidir: hassas modda otomatik olarak kucuk kalir,
# boylece kol birakildiginda geri sicrama olusmaz.
ANALOG_LEAD_TIME_S = 0.04


# Analog girdi yumusatma katsayisi (0..1). Her turda yeni deger bu
# oranda karisir; kucuk deger daha puruzsuz ama daha gecikmeli.
# 0.25 ile ~30 ms'lik yumusatma olusur, gozle fark edilmez ama kol
# ADC gurultusunu belirgin sekilde keser.
ANALOG_SMOOTHING = 0.90


# Hassas moddaki ileri besleme payi.
#
# ESKI GEREKCE GECERSIZ: burada "servo torku konum hatasiyla
# orantilidir, o yuzden pay buyuk olmali" yaziyordu ve deger 1.8'e
# kadar cikarilmisti. tools/deadband_test.py olcumu bunu curuttu:
# sorun tork degil, KOMUT DEGISIMI ESIGI (~1.0 birim). Sabit bir pay
# komutu kaydirir ama degisim boyutunu buyutmez, yani bu soruna hicbir
# katkisi yoktur. Hareketi saglayan mekanizma artik dither'dir
# (asagiya bak).
#
# Payin kalan tek islevi hareket sirasinda servoyu bir miktar onde
# tutmaktir. Kucuk secilir cunku kol birakildiginda komut `hiz * pay`
# kadar geri doner: hassas modda 1.5 birim/s * 0.2 s = 0.3 birim, yani
# olculen 1.0 birimlik esigin ALTINDA — taret bu geri donusu fiilen
# uygulamaz, oldugu yerde kalir. Istenen davranis tam olarak budur.
ANALOG_LEAD_PRECISION_S = 2.0


# --- Ileri besleme TABANI (hizdan bagimsiz) ---
#
# KAPATILDI (0 = etkisiz). "Yavas = gucsuz" sorununu cozmek icin
# eklenmisti: pay hizla orantili kuculdugu icin en hafif dokunusta
# sifira yaklasiyordu, taban da bunu engelliyordu.
#
# tools/deadband_test.py olcumu bu yaklasimin dayanagini curuttu:
# sorun torkun yetersizligi degil, taretin ~1.0 birimden kucuk komut
# DEGISIMLERINE hic tepki vermemesi. Taban sabit bir kaydirmadir;
# komutun bulundugu yeri degistirir ama ardisik komutlar arasindaki
# FARKI buyutmez, dolayisiyla esigi asmaya yardim etmez. Sahada da
# etkisi gozlenmedi (2.0 birime kadar denendi).
#
# Kod yerinde birakildi (control/system_manager.py::_lead_error);
# 0'dan buyuk bir deger yazilirsa yeniden devreye girer.
ANALOG_MIN_LEAD_PAN_DEG = 0.0
ANALOG_MIN_LEAD_TILT_DEG = 0.0


# --- En kucuk yayin adimi (ASIL COZUM) ---
#
# tools/deadband_test.py, iki yonu ayri olcen surumuyle:
#
#            0.1   0.2   0.3   0.5   1.0   1.5   2.0   3.0
#   YUKARI   yok   yok   yok   sic   sic   sic   PURU  PURU
#   ASAGI    yok   yok   yok   sic   PURU  PURU  PURU  PURU
#
# Taret 0.5 birimin altindaki komut DEGISIMLERINE hic tepki vermiyor.
# Hassas modda tick basina yalnizca ~0.03 birim ilerliyoruz; komut
# suruniyor, servo yok sayiyor, biriken fark esigi asinca tek seferde
# sicriyordu. Gozlenen "gecikmeli, birikmis sicrama" tam olarak budur.
#
# Cozum: komutu bekletip ancak hedef bir tam adim uzaklastiginda
# yayinlamak. Boylece her yayin, olcumde PURUZSUZ cikan buyuklukte
# olur. Hassas hizda (1.5 birim/s) asagi yonde adim araligi 0.67 sn
# olur — olcumdeki 0.6 sn'lik tutma suresine neredeyse birebir denk.
#
# YON BAZLIDIR: yukari hareket yercekimi yuku yuzunden daha buyuk adim
# ister (2.0), asagi daha kucukle yetinir (1.0). Gereginden buyuk adim
# hareketi kabalastirir, bu yuzden her yon kendi olculen degerini alir.
#
# Pan olculmedi ve pan zaten sorunsuz calistigi icin KAPALI (0).
# Pan'da da hafif dokunuslar tutarsizsa tools/deadband_test.py'yi pan
# icin calistirip buraya yaz.
ANALOG_STEP_PAN_DEG = 0.0          # olculmedi — kapali
ANALOG_STEP_TILT_UP_DEG = 2.0      # OLCULDU
ANALOG_STEP_TILT_DOWN_DEG = 1.0    # OLCULDU


# --- Dither (salinim) — DENENDI, KULLANILMIYOR ---
#
# Fikir: komutu hedef etrafinda salindirip servoyu her yarim periyotta
# esigin disina itmek. Frekans taramasi bunu eledi:
#
#            1 Hz   2 Hz   3 Hz   5 Hz   8 Hz
#   YUKARI   PURU   yok    yok    yok    yok
#   ASAGI    PURU   yok    yok    yok    yok(*)
#
#   (*) Asagi/8 Hz bir koşuda "puruzsuz" verdi ama komsu frekanslarin
#       hepsi olu ve onceki kosum ayni noktada "hareket yok" demisti;
#       aykiri deger olarak elendi.
#
# Belirleyici degisken genlik degil SUREDIR: ayni buyuklukteki degisim
# 0.6 sn tutuldugunda hareket uretiyor, 62 ms tutuldugunda uretmiyor.
# Servo yol almaya baslayamadan komut ters donuyor.
#
# Calisan tek frekans 1 Hz, yani yarim periyot 500 ms. Bu, namlunun
# saniyede bir 2 birimlik yay cizmesi demek — nisan almak icin
# kullanilamaz. Bu yuzden genlikler 0 (kapali) birakildi.
#
# Kod yerinde (control/system_manager.py::_dither_offset). Geri acmak
# istersen frekans zaten olculen tek calisan degere ayarli.
ANALOG_DITHER_HZ = 1.0             # OLCULDU: calisan tek frekans
ANALOG_DITHER_PAN_DEG = 0.0        # kapali
ANALOG_DITHER_TILT_UP_DEG = 0.0    # kapali
ANALOG_DITHER_TILT_DOWN_DEG = 0.0  # kapali

# Bu hizin uzerinde salinim uygulanmaz (dither acilirsa gecerli).
ANALOG_DITHER_MAX_RATE_DPS = 25.0


# --- Bosluk (backlash) telafisi ---
#
# Telafi hedef aciya DEGIL ayri bir offset degiskenine yazilir; boylece
# sistemin konum modeli (_pan_target) bozulmaz ve limit kirpmasi dogru
# yerde calisir.
#
# TILT SIMETRIK DEGILDIR: yercekimi ekseni surekli tek yone bastirir,
# o yonde slack zaten kapalidir.
BACKLASH_ENABLED = True

BACKLASH_PAN_DEG = 1.20            # OLCULEREK doldur

# "UP" = tilt acisinin ARTTIGI yon. Mekanizmanda ters ise ikisini
# yer degistir.
#
# GECICI TEST DEGERI: DOWN=0.20 iken kucuk darbeler dislide "bosta"
# kayboluyor, gercek boslugu kapatmiyordu (asagi yonde hareket
# algilanmiyor, sonra birikip tek seferde sicriyordu). UP=1.80/
# DOWN=1.90 ise sicrama/salinima yol aciyordu — muhtemelen deger
# yanlis degil, BACKLASH_SLEW_S ile COK HIZLI uygulaniyordu. Asagida
# ikisi de orta bir degere esitlendi: elle test edip (motoru IDLE'da
# tut, tilt'i yavasca iki yone cevir, hangi yonde bosta donme daha
# fazla hissediliyorsa o yonun degerini artir) gercek boslugu
# ölçüp buraya gir.
#
# TILT ICIN KAPATILDI (0 = etkisiz). Iki sebep:
#
# 1. Offset kol merkeze donunce SIFIRLANMIYOR; _BacklashComp son yonun
#    slack degerini tutmaya devam ediyor. 1.0 birimlik bir offset,
#    olculen hareket esigiyle (~1.0 birim) tam ayni buyuklukte — yani
#    kol birakildiginda taret bir adim daha kayiyordu. Simulasyonda
#    dogrulandi: birakma sonrasi komut hedefin +1.04 birim uzerinde
#    kaliyordu.
#
# 2. Bu degerler hicbir zaman olculmedi; "tork = konum hatasi"
#    varsayiminin gecerli sanildigi donemde elle ayarlandi (1.80/1.90,
#    sonra 0.50/0.20, sonra 1.00/1.00). tools/deadband_test.py o
#    varsayimi curuttu.
#
# GERI GETIRME KOSULU: yalnizca yon DEGISIMINDE gercek bir olu bant
# gozlenirse. O zaman bile deger olculen hareket esiginin ALTINDA
# kalmalidir; esik boyunda bir offset birakmak yukaridaki 1. maddedeki
# sicramayi geri getirir.
BACKLASH_TILT_UP_DEG = 0.0
BACKLASH_TILT_DOWN_DEG = 0.0

# Telafi ancak girdi bu esigi asinca tetiklenir. Kol merkezindeki ADC
# gurultusunun isaret degistirip surekli darbe uretmesini engeller —
# eski kod tam bu yuzden tilt'te firliyordu.
BACKLASH_ARM_INPUT = 0.15

# Yon degisimi bu sure boyunca teyit edilmeden telafi uygulanmaz (s).
BACKLASH_CONFIRM_S = 0.05

# Offset anlik basamak degil, bu sure icinde rampalanir (s). Anlik
# basamak servoyu tam hizda sicratir. 0.08 -> 0.12: buyutulen offset
# (0.5/0.2 -> 1.0/1.0) ayni sureye sigdirilirsa rampa hizi artar ve
# eski salinim sorununu geri getirebilir; sureyi de biraz uzattik.
BACKLASH_SLEW_S = 0.16


# --- Yercekimi telafisi (yalnizca tilt) ---
#
# Backlash ve ANALOG_LEAD_PRECISION_S payi RATE ILE ORANTILI: kol
# merkeze yakinken veya cok yavas hareket ederken ikisi de sifira
# yaklasir. Ama tilt ekseni TASIDIGI YUK yuzunden kol hic basilmasa
# bile yercekimine karsi surekli tork gerektirir; pan boyle bir yuk
# tasimaz. Sonuc: hassas moddaki kucuk komutlarda pay yercekimini
# karsilamaya yetmiyor, servo hareket etmiyor; hata biriktikce (rate
# ile orantili paylar da eklenince) esik asilinca ani ama hassas
# olmayan bir sicrama oluyor.
#
# Cozum: girdi buyuklugunden BAGIMSIZ, sabit bir on-yukleme payi.
# Backlash/lead'in aksine kol birakilinca da KAYBOLMAZ; servoya her
# zaman yercekimine karsi asgari bir tork uretecek kadar konum hatasi
# verir.
#
# DOGRULAMA: motor gucsuzken tilt asagi (aci AZALAN yon = DOWN)
# dusmeye meylediyor ama disliler SIKI/kendinden kilitli oldugu icin
# fiilen dusmuyor. Yorumdaki kurala gore (telafi, dusme yonunun
# TERSINE) bu +1 (UP) anlamina gelir — SIGN su an -1 yazili, bu
# celiskiyi doğrulamadan degistirmedim; asagidaki not'a bak.
#
# Kendinden kilitli disli, hareketsizken tutmak icin tork istemez ama
# harekete BASLAMAK icin normalden cok daha buyuk bir kirilma
# (breakaway) toku ister — bu yuzden UP yonunde kucuk komutlar hic
# hareket uretmiyor, ~2 sn sonra biriken hata esigi asinca aniden
# sicriyordu. UYGULAMA ARTIK KOSULLU: yalnizca AKTIF olarak
# TILT_GRAVITY_SIGN yonunde hareket edilirken eklenir — ters yonde
# veya kol ortadayken sifirdir (bkz. control/system_manager.py,
# moving_against_gravity). Bu sayede DOWN'i artik etkilemez, UP icin
# deger rahatca buyutulebilir.
#
# KAPATILDI (0 = etkisiz). tools/deadband_test.py olcumu bu payin
# dayandigi varsayimi curuttu: sorun yercekimine karsi tork uretmek
# degil, taretin ~1.0 birimden kucuk komut DEGISIMLERINE hic tepki
# vermemesi. Sabit bir pay komutu kaydirir, ardisik komutlar
# arasindaki farki buyutmez — esigi asmaya katkisi yoktur. Sahada da
# etkisi gozlenmedi (0.4 ve 0.8 denendi). Yerini dither aldi.
#
# Kod yerinde birakildi (control/system_manager.py,
# moving_against_gravity); 0'dan buyuk deger yazilirsa geri gelir.
TILT_GRAVITY_BIAS_DEG = 0.0
TILT_GRAVITY_SIGN = 1.0           # yon dogrulandi: yercekimi asagi cekiyor


# Kol tam cekildiginde hedefin saniyede kac derece kayacagi. Firmware'in
# MAX_VEL degerinden DUSUK olmalidir; aradaki fark eksenin hedefe
# yetismesi icin gereken paydir.
ANALOG_PAN_RATE_DPS = 75.0     # firmware PAN_MAX_VEL_DPS = 800
ANALOG_TILT_RATE_DPS = 70.0    # firmware TILT_MAX_VEL_DPS = 600

# Tepki egrisi ussu. 1.0 dogrusal, 2.0 merkeze yakin hassas ve uclarda
# hizli. Kol az cekildiginde ince ayar, cok cekildiginde hizli hareket
# istendigi icin 2.0 secildi.
ANALOG_EXPO = 2.0

# --- Hassas mod ---
#
# Carpan yerine dogrudan derece/saniye yazilir. Eski ANALOG_PRECISION_FACTOR
# gercek hizi (35 * 0.04 = 1.4 derece/s) gizliyordu ve expo ile birlesince
# kolun alt yarisi olu bolgeye donuyordu.
#
# HEDEF OLCUT: kol tam itildiginde 15 metrede saniyede yaklasik bir balon
# capi (15 cm = 0.57 derece) kaymali.
#
# DOGRULAMA: hassas modda kolu tam it, 5 saniye tut, 15 metredeki kaymayi
# olc. 75 cm civari cikmali. Cikmiyorsa disli orani farkli demektir,
# degeri olculen orana gore duzelt.
ANALOG_PAN_PRECISION_DPS = 1.80
ANALOG_TILT_PRECISION_DPS = 1.50

# Hassas modda tepki egrisi DOGRUSAL olmalidir. Ince ayari saglayan sey
# zaten hassas modun dusuk azami hizidir; ustune expo koymak kolun
# kullanilabilir yolunu bosa harciyor.
PRECISION_USE_EXPO = False

# Bu hizin altindaki komutlar sifirlanir.
ANALOG_MIN_RATE_DPS = 0.0003


# Eksen yonu duzeltmesi
ANALOG_PAN_SIGN = -1.0
ANALOG_TILT_SIGN = 1.0

# Takipte gurultu kaynagi kol ADC'si degil YOLO kutu merkezi;
# agir yumusatma gereksiz gecikme ekler.
AUTO_SMOOTHING = 0.75

# ---------------------------------------------------------------------------
# Kamera hareketi (ego-motion) telafisi
# ---------------------------------------------------------------------------
#
# Kamera taretin ustundedir ve taretle birlikte doner. Taret dondugunde
# sabit bir hedef bile goruntude yer degistirir. Telafi yapilmazsa
# takipci hedefi bekledigi yerde bulamaz, izi duşurur ve yeni ID atar.
#
# KALIBRASYON (zorunlu, 5 dakika):
#   1. Sabit bir nesneyi kadraja al (duvarda isaret, kutu kosesi)
#   2. MANUAL modda pan'i bir konuma getir; nesnenin piksel x konumunu
#      ve taret pan acisini not et  -> X1, A
#   3. Pan'i 15-20 birim cevir; tekrar not et  -> X2, B
#   4. EGO_PX_PER_PAN_UNIT = abs(X2 - X1) / abs(B - A)
#   Ayni islemi tilt/y ekseni icin tekrarla.
#
# Piksel konumu MJPEG sayfasindan (http://localhost:8080/) veya
# arayuzdeki kutu merkezinden okunabilir.

EGO_MOTION_ENABLED = False

# BASLANGIC TAHMINI — olculerek degistirilmelidir.
#
# Pan: yatay FOV ~70 derece / 1920 px ve 1 taret birimi ~1 gercek
# derece varsayimiyla.
#
# DUZELTME (2026-09-10): eski yorumdaki "tilt pulse araligi dar
# (1000-1350 us), 1:2 disli, birim basina hareket pan'in dortte biri"
# ifadesi YANLISTIR. Guncel durum: her iki eksen de 500-1800 us
# araligini kullanir (1300 us acikligi).
#
#     Pan : 100-40 =  60 birim -> 1300/60 = birim basina ~21.7 us
#     Tilt: 155-110 = 45 birim -> 1300/45 = birim basina ~28.9 us
#
# Yani tilt pan'dan DAHA IYI cozunurluge sahiptir (~%33), daha kotu
# degil. Asagidaki tilt degeri hala eski varsayimdan kalmadir ve
# olculmemistir.
#
# BU SAYILARIN ONEMI: hassas moddaki "kucuk komut hareket uretmiyor,
# sonra sicriyor" sorunu arastirilirken eski yorum ölu bant hesabina
# dayanak yapildi ve yanilticiydi. 28.9 us/birim, tipik servo ölu
# bandinin (5-10 us) cok uzerindedir; ayrica daha iyi cozunurluklu
# eksenin daha kotu davranmasi ölu bant aciklamasiyla celisir. Sorun
# cozunurlukte degil, mekanik yuk/tork tarafinda aranmalidir.
#
# Gercek birim -> derece orani tools/ego_calibrate.py ile olculmeli.
#
# EGO_MOTION_ENABLED su an False oldugu icin bu degerler etkin degil.
EGO_PX_PER_PAN_UNIT = 17.5
EGO_PX_PER_TILT_UNIT = 17.0   # DOGRULANMAMIS — eski varsayimdan kalma

# Kayma yonu. Telafi hedefi TERS yone itiyorsa isareti degistir.
EGO_PAN_SIGN = 1.0
EGO_TILT_SIGN = -1.0



# ---------------------------------------------------------------------------
# Hiz ileri beslemesi
# ---------------------------------------------------------------------------
#
# Hedefin acisal hizi dogrudan komuta eklenir. Kalici geride kalmayi
# kazanc artirmadan ortadan kaldirir.

AIM_FEEDFORWARD_ENABLED = False

# Filtre katsayisi (0..1). Kucuk deger daha agir filtre.
# 0.12 ile ~50 Hz dongude zaman sabiti ~170 ms olur: hedefin gercek
# hiz degisiminden hizli, pozitif geri besleme dongusunden yavas.
AIM_FF_SMOOTHING = 0.12

# Ileri besleme girdisinin ust siniri (analog girdi birimi).
# Kestirim bozulursa taretin firlamasini engeller.
AIM_FF_MAX = 0.25

# Bu surenin uzerinde tespit gelmemisse ileri besleme sifirlanir.
# Bayat hiz kestirimiyle surmek hedefi buyuk olcude kacirir.
AIM_FF_MAX_AGE_S = 0.30

# Bu sureden daha eski izler YAYINLANMAZ. Iz nesnesi silinmez
# (angajman yeniden eslestirme icin tahmine ihtiyac duyar) ama
# arayuze ve nisan katmanina gonderilmez. Aksi halde kamera
# donerken olu kutu ekranda surunur ve nisan noktasi ona kilitli
# kalir.
#
# 0.20 idi - RTX 3050 Ti'nin ~50ms cikarim hizina gore ayarlanmisti.
# GTX 1050 Ti (Pascal, fp16 destegi yok) ~150-220ms'de calisiyor; bu
# durumda her donguden sonra iz kisa sureligine "bayat" sayilip
# yayindan dusuyor, surekli titreme/gecikme hissi veriyordu. 0.40'a
# cikarildi (31 Agustos, dogrulandi): 1050ti'nin en kotu durumuna
# (220ms) ~2x pay birakir, RTX'te zaten bol marjin var.
TRACK_PUBLISH_MAX_AGE = 0.40