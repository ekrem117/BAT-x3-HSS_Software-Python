# CLAUDE.md

Bu dosya, Claude Code'un (claude.ai/code) bu depodaki kodla çalışırken uyması gereken yönergeleri içerir.

## Dil

**Kod tabanının tamamı — kaynak yorumları, docstring'ler, log mesajları, commit mesajları ve dokümantasyon (README.md, docs/protocol_spec.md) — Türkçedir.** Mevcut dosyaları düzenlerken veya yeni kod eklerken bu kurala uy; bir modülü dosyanın ortasında İngilizceye çevirme. Kullanıcıyla onun kullandığı dilde konuşulabilir.

## Proje

BAT-X3, bir hava savunma taret yarışma robotunun (Teknofest Çelik Kubbe HSS) Python alt sistemidir: görüntü işleme (kamera yakalama, YOLO tespiti, takip, dost/düşman renk sınıflandırması), kontrol/karar katmanı (mod durum makinesi, hedef angajmanı, nişan çözümü, taret sürme) ve ayrı bir C# operatör arayüzüyle UDP/TCP üzerinden haberleşen ağ servisleri. Arduino kontrollü tareti seri port üzerinden sürer. Her şey tek bir süreçte (`main.py`) çalışır; her servis kendi daemon thread'indedir.

Bu depo yalnızca Python tarafıdır. Arayüz (C#) ve firmware (Arduino `.ino`) ayrı depolardadır ve değişmez dış sözleşmeler olarak kabul edilir.

## Çalıştırma

```bash
python -m venv venv
venv\Scripts\activate          # Linux/macOS: source venv/bin/activate
pip install -r requirements.txt

python main.py                 # Ctrl+C ile durdurulur; tüm servisler bu tek süreçte daemon thread olarak çalışır
```

Otomatik test paketi yoktur (pytest/unittest yok). Doğrulama `tools/` altındaki betiklerle ve gözle, elle yapılır.

### Elle doğrulama araçları

| Komut | Amaç | `main.py` çalışıyor olmalı mı? |
|---|---|---|
| `python tools/test_receiver.py` | UDP referans istemcisi: video (5007) + tespit (5008) katmanı, gecikme/kare kaybı istatistikleri | Evet |
| `http://localhost:8080/` | Tarayıcı MJPEG tanı yayını | Evet |
| `python tools/bench.py` | Kamera yakalama + JPEG kodlama ölçümü; kamerayı doğrudan açar | Hayır — kamera tek sahiplidir |
| `python -m tools.control_test` | `SystemManager` mod/ateş/backlash mantığını sahte seri bağlantıyla dener | Hayır, donanım/ağ gerekmez |
| `python -m tools.hardware_test` | Onay istemleriyle adım adım gerçek Arduino testi | Hayır — port çakışması |
| `python -m tools.backlash_test` / `diagonal_test` | Fiziksel eksen davranışı kontrolleri (`diagonal_test` klavye girdisini atlayarak iki eksenin eşzamanlı hareketini doğrular) | Hayır — port çakışması |
| `python -m tools.auto_probe` | Yalnızca GET yapan tanı aracı: otonom takibin nerede koptuğunu bulmak için AUTO mod zincirini (mod → bağlantı → tespitler → çıkarım → otonom pan/tilt → armed) adım adım izler | Evet |
| `python -m tools.ego_calibrate` | `EGO_PX_PER_PAN_UNIT`/`EGO_PX_PER_TILT_UNIT` için en küçük kareler uydurması | Evet |
| `python -m tools.track_bench` | Otonom takip performansı: süreli bir koşuda kilit oranı, kilit değişim sıklığı, yeniden yakalama oranı | Evet |
| `python -m tools.gamepad_probe` | Kontrolcü betiği bağlanmadan önce ham gamepad eksen/düğme indekslerini yazdırır | Hayır |
| `python -m tools.manual_wasd` / `manual_analog_wasd` / `manual_gamepad` | Gerçek C# arayüzünün yerine geçer — tareti klavye/gamepad ile UDP üzerinden sürer | Evet, ayrı bir terminalde |

`tools/` altındaki her şey yalnızca geliştirme betiğidir, üretim kodunun parçası değildir — kütüphane kodu gibi import edilmemelidir.

Protokolün tam başvuru belgesi: [docs/protocol_spec.md](docs/protocol_spec.md).

## Yerel geliştirme ayarları

`config/local_settings.py` (gitignore'da, asla commit edilmez) ayarları geliştirici bazında ezer — örneğin donanım/kamera/model olmadan çalışırken bunları kapatmak için:

```python
ENABLE_COMMAND_SERVER = True
ENABLE_CONTROL = False
ENABLE_VIDEO = False
ENABLE_DETECTIONS = False
ENABLE_MJPEG = False
ENABLE_TRACKING_LOOP = False
```

Diğer her şey kapalıyken yalnızca `numpy`/`opencv-python` gerekir — `ultralytics`, `torch`, `pyserial` gerekmez. Ayrıca faydalı olanlar: `USE_CAMERA = False` (sentetik hareketli kare kaynağı), `USE_YOLO = False` (sentetik tespitler). Sentetik üreteç 4 deterministik hareketli hedef (dost/düşman/bilinmeyen + balon) üretir ve kilitlenme/hız/angajman mantığını normal şekilde çalıştırır; arayüz geliştirmede gerçek kameradan daha tekrarlanabilirdir.

**Uyarı:** docstring'de yazana rağmen `from config.local_settings import *` satırı şu anda `settings.py`'nin sonunda değil, *ortasında* (LOOP_DEMO bloğundan hemen sonra) duruyor. Bu satırın altında tanımlanan hiçbir değer — nişan, taret sürme, `AUTO_RATE_FACTOR`, eksen limitleri, analog kontrol — yerel olarak **ezilemez**. Import'un dosya sonuna taşınması açık bir iştir.

**Kişisel/geçici değişiklikler için asla `config/settings.py` düzenlenmez** — ortak varsayılanların bozulmaması için `config/local_settings.py` kullanılır. `settings.py`'ye sızmış bir `ENABLE_CONTROL = False` tüm taret hareketini sessizce kapatır (hata vermez, kontrol katmanı hiç başlamaz).

## Mimari

Bağımlılıklar kesinlikle tek yönde akar. `core/` başka hiçbir katmanı tanımaz; diğer katmanlar birbirini doğrudan import etmez — `core/state.py` (parametre kataloğu) ve `core/enums.py` üzerinden buluşurlar:

```
config/  → tüm sabitler (settings.py tek kaynaktır; projeden başka hiçbir şey import etmez)
   ↓
core/    → paylaşılan durum (state.py parametre kataloğu + komut kuyruğu), enum'lar, log kurulumu
   ↓
 ┌────────────┬────────────┬────────────┬────────────┐
 vision/    protocols/    control/    hardware/
 (kare,     (ağ:          (karar,      (Arduino
  tespit,    UDP+TCP)      taret        seri port)
  takip)                   sürme)
```

`control/param_bridge.py` bilinçli bir istisnadır: ağ katmanının kontrol katmanını hiç import etmek zorunda kalmaması için `protocols/` yerine `control/` altında durur.

### `core/state.py` — parametre kataloğu (merkezi sözleşme)

`PARAM_DEFS` veriye dayalı bir katalogdur: ad → `{type, access, min, max, unit, desc, trigger?}`. `PARAM_VALUES` (anlık değerler) ile birlikte, C# arayüzünün dokunabildiği her GET/SET parametresinin *tek* tanımıdır. `protocols/udp/dispatcher.py` bu kataloğa karşı genel olarak doğrular ve okur/yazar — **parametreye özel hiçbir kodu yoktur**.

- `Access.RO` / `RW` / `WRO` (yalnızca yazma, tetikleyici parametreler için) GET/SET'in neyi kabul edeceğini belirler — bkz. `core/enums.py`.
- `"trigger": True` olarak işaretli parametreler (ör. `weapon.fire`) saklanmaz; kontrol döngüsünün tüketmesi için `core.state.COMMAND_QUEUE`'ya eklenir.
- Kataloğun kanonik dokümantasyonu `docs/protocol_spec.md` §9'dur; **katalog her değiştiğinde güncellenmelidir** (§15'teki sürüm tablosu da artırılır).

### `protocols/` — ağ katmanı, iş mantığı içermez

- `udp/command_server.py` + `udp/dispatcher.py`: 5005 portundaki GET/SET istek-cevap protokolü; yalnızca `core/state.py`'ye göre doğrulanır (varlık → erişim tipi → null → tip → aralık, bu sırayla — bkz. protocol_spec.md §6). `dispatcher.py` soketlerden habersizdir ve ağ olmadan test edilebilir.
- `udp/video_server.py` (5007) / `udp/detection_server.py` (5008): istek-cevap kanalından bağımsız, tek yönlü yayın akışları. İkisi aynı `frame_id`'yi kullanır; böylece istemci tespit kutusunu doğru video karesiyle eşleştirebilir.
- `tcp/mjpeg_server.py` (8080): yalnızca tarayıcı tanı yayını — gerçek arayüz bunu hiç kullanmaz.

Tam kablo formatı (video paket başlığı, tespit JSON şeması, sınıf/takım/angajman durum kodları, koordinat ölçekleme) `docs/protocol_spec.md`'dedir. Herhangi bir protokol koduna dokunmadan önce okunmalıdır; bu depo ile C# istemcisi arasındaki tek ortak doğruluk kaynağıdır.

### `vision/` — kamera bir kez açılır, tek `frame_buffer`, diğer her şey ondan okur

Tüm video tüketicileri (kodlayıcı, dedektör, MJPEG) `frame_buffer.py`'deki aynı paylaşılan son kareyi okur — kamera tam olarak bir kez açılır. Gerçek model entegrasyonu yalnızca dedektör katmanını değiştirmelidir, aşağı akıştaki paket formatını değil.

```
frame_buffer (tek yakalama thread'i, tüm tüketicilerin paylaştığı tek frame_id)
   → detection_buffer (çıkarım thread'i: detector/color_detector → classifier → association → ranging)
      → track_store (track_id başına Kalman MotionModel; predict_all() çıkarım hızından bağımsız, çağıranın hızında çalışır)
         → threat.py (öncelik skoru; angajman yokken kilitlenilecek hedefi seçer)
         → engagement.py (LOCKED/LOST/DESTROYED/ABANDONED durum makinesi; takipçi ID değişimlerinden bağımsız)
            → aiming.py (öngörü süresi + maket altı balon ofseti + balistik düzeltme → piksel hatası)
               → turret_driver.py (piksel hatası → analog pan/tilt girdisi, ileri besleme) → SystemManager
```

Bu yapının önemi:
- Tespit model hızında çalışır (onlarca–yüzlerce ms); video onu beklememelidir. Bu yüzden aynı `frame_buffer`'dan okuyan ayrı bir thread'dir.
- Kontrol/takip döngüsü (`control/tracking_loop.py`) `TRACKING_LOOP_HZ` (50 Hz) hızında, çıkarım hızından bağımsız çalışır; tespit beklemek yerine her izin Kalman filtresinden konum tahmin eder.
- Angajman takipçi ID'sine değil *hedef kimliğine* kilitlenir: takipçi bir ID'yi düşürüp yeniden atadığında `engagement._find_reacquire_candidate` tahmini konum + sınıf + takım ile yeniden bağlar; böylece saniyeler süren bir angajman ID değişimlerinden etkilenmez.
- Kamera taretin üstündedir; taret döndüğünde karedeki her sabit hedef yer değiştirir. İzin konumunun zaman içinde ileriye taşındığı her yerde (`track_store.predict_compensated`, `engagement._apply_ego_motion`) `core/ego_motion.py` telafisi uygulanır — olmazsa pan hareketi kilitleri düşürür ve yeniden yakalama eşleşmesini bozar.
- Hedefler maket + balon çiftleridir: angajman maketi kilitler (stabil, her zaman görünür) ama balona nişan alır (`aiming._apply_balloon_offset`). İmha teyidi (`engagement._check_kill`) atıştan sonra balon tespitinin kaybolmasından çıkarılır — maket baştan sona görünür kalır.
- Mesafe kestirimine (`vision/ranging.py`) yalnızca balon sınıfı için güvenilir (`RANGE_RELIABLE_CLASSES`) — diğer hedeflerin görünür boyutu yönelime göre değişir.

### `control/` — `SystemManager` tek karar merkezidir

`control/system_manager.py` **tüm** güvenlik ve mod geçiş kurallarının sahibidir; bu kurallar başka hiçbir yerde bulunmaz. Üstündeki hiçbir katman donanımla doğrudan konuşmaz. `core/state.py`'yi hiç tanımaz — katalog değerlerini `SystemManager`'ın iç durumuyla senkronlayan tek şey `control/param_bridge.py`'dir (aşağı: katalog → yönetici her turda; yukarı: yönetici durumu → katalog her 5. turda). Bu sayede `SystemManager` UDP ve Arduino olmadan test edilebilir (`tools/control_test.py`).

`SystemManager`'a gömülü temel kurallar:
- Mod geçişleri (`core.enums.SystemMode`: IDLE/MANUAL/AUTO/LOOP_DEMO/ESTOP) iki çalışma modu arasında asla doğrudan olmaz — her geçiş `IDLE`'dan geçer; böylece taret bir an bile sahipsiz kalmaz ve basılı tuşlar temizlenir. `ESTOP`'a her moddan girilebilir; `ESTOP`'tan yalnızca `IDLE`'a çıkılabilir. Bkz. `_ALLOWED_TRANSITIONS`. Her mod değişiminde `weapon.armed` zorla 0'a çekilir.
- Karşılıklı dışlayan iki hareket gösterimi vardır; hangisinin etkin olduğunu en son çağrılan girdi yöntemi belirler:
  - **Bit maskesi** (`set_manual_input`/`set_demo_input`, tek bayt, WASD tarzı yön bitleri) — hız firmware sabitleriyle belirlenir.
  - **Mutlak açı** (`set_analog_input`, 5 baytlık `0xFB` çerçevesi) — analog kol ve otonom takip tarafından kullanılır. Arduino'dan konum geri beslemesi olmadığı için taret konumunun tek doğruluk kaynağı Python'daki `_pan_target`/`_tilt_target`'tır.
- Backlash telafisi (`_BacklashComp`) *giden komuta eklenen bir ofset* olarak uygulanır, asla `_pan_target`'a yazılmaz; böylece konum modeli ve eksen limiti kırpması doğru kalır.
- Ateşleme `fire()` içinde sıralı bir koruma zincirinden geçer (mod → armed → mühimmat → bekleme süresi → bağlantı durumu), en ucuz kontroller önce.

**Otonom hız doğrudan ayarlanmaz, türetilir.** `_build_analog_payload_locked()` içinde (`is_auto=True` dalı) tavan `ANALOG_*_RATE_DPS * AUTO_RATE_FACTOR`'dür; `control/turret_driver.py::_rate_to_input` ileri besleme için aynı çarpımı ters yönde kullanır. Bu nedenle manuel analog hızları değiştirmek otonom hızı da aynı oranda değiştirir — `ANALOG_*_RATE_DPS` her değiştiğinde `AUTO_RATE_FACTOR` yeniden hesaplanmalıdır.

`LOOP_DEMO` girdi kurallarının istisnasıdır: `control/loop_demo.py`'deki koreografi (`param_bridge` tarafından her turda çalıştırılır) taretin tek sahibidir — bu modda manuel/analog girdi ve ARM reddedilir. Python'da sabit yol hızlı, kosinüs rampalı bir yörünge hesaplar — düz çizgi tarama/çapraz dizisi veya sürekli elips, `motion.demo.pattern` katalog parametresiyle seçilir — ve bunu `SystemManager.set_demo_target()` üzerinden gönderir. Analog yolun yumuşatma/öngörü/backlash/adım filtrelerini bilinçli olarak atlar.

### `hardware/` — tek seri port sahibi, firmware ile bayt bayt bağlı

`hardware/arduino_link.py` seri portu açmaya izinli *tek* modüldür (firmware'in watchdog'unu beslemek için `HEARTBEAT_INTERVAL_S` aralığında heartbeat gönderir, kopunca otomatik yeniden bağlanır). `hardware/serial_protocol.py` bayt sabitlerini ve çerçeve kodlamasını tanımlar; bunlar **`.ino` firmware ile birebir eşleşmek zorundadır**. Bir tarafta değişip diğerinde değişmeyen sabit çökme değil, sessizce yanlış komut üretir. Modül bilinçli olarak iş kuralı içermez (ör. "yukarı+aşağı birlikte basılırsa ne olur" `control/system_manager.py`'de çözülür, burada değil).

İki komut biçimi vardır: tek baytlık bit maskesi/özel komutlar (`CMD_HOME`, `CMD_ESTOP` vb., `0xFC`–`0xFF`) ve 5 baytlık `0xFB` mutlak açı çerçevesi.

Şu an yüklü firmware (`arduino_for_joystick_hss.ino`) `0xFB` çerçevesini işler (`FRAME_HEADER` + 4 bayt veri → `processFrame()` → `moveToImmediate()`); bu yüzden `control/` içinden kullanımı güvenlidir. İki uyarı geçerliliğini korur:
- Eski firmware sürümleri `0xFB`'yi **işlemiyordu**; onu bit maskesi olarak yanlış okuyordu ve bit4 (`0x10`) silahı ateşliyordu. Mutlak açı modunu kullanmadan önce yüklü firmware sürümü mutlaka teyit edilmelidir.
- `moveToImmediate()` servoya doğrudan yazar ve firmware'in yörünge üretecini atlar; bu yüzden gönderilen mutlak açı yörüngesindeki her süreksizlik tam hızda bir servo sıçramasına dönüşür.

### Yeni ayarlanabilir değer eklemek

Sabit ise: `config/settings.py`'ye eklenir (ortama özelse yerel olarak `config/local_settings.py`'ye de — o dosyanın içeriği asla `settings.py`'ye commit edilmez).

Arayüzden okunabilir/yazılabilir olması gerekiyorsa: yalnızca `core/state.py`'deki `PARAM_DEFS` + `PARAM_VALUES`'a eklenir — dispatcher'a asla dokunulmaz. `docs/protocol_spec.md` §9 (ve §15 sürüm tablosu) buna göre güncellenir.

## Ayar kuralları (`config/settings.py`)

- Tek dosya, proje içi import yok — donanım, port, çözünürlük ve ayar davranışını değiştiren her sabit burada yaşar ve bir değerin *neden* öyle olduğu yorumlarla ayrıntılı açıklanır (çoğu zaman sahada ölçülmüş kalibrasyon prosedürleri de satır içinde). **Bir ayar sabitini değiştirmeden önce yorumunu oku**; birçoğu salınım/backlash/gecikme hakkında zor öğrenilmiş dersler içerir.
- Her sabit **tek** yerde tanımlanır. Mükerrer tanımlar (sonraki satırın öncekini sessizce ezmesi) daha önce hatalara yol açtı — özellikle merge sonrasında.
- `ENABLE_*` bayrakları her servisin (kontrol, komut sunucusu, video, tespitler, MJPEG, takip döngüsü) bağımsız olarak kapatılmasını sağlar — bkz. yukarıdaki yerel ayarlar.
- Yarışma koşularında `DEBUG_OVERLAY` `False` olmalıdır (kare numarası/canlılık göstergesi çizer; gerçek görüntüde tespit doğruluğunu ve arayüzün kendi katmanını bozar).
- `PAN_MIN_DEG`/`PAN_MAX_DEG`/`TILT_MIN_DEG`/`TILT_MAX_DEG` firmware kırpma değerleriyle birebir eşleşmelidir — firmware de kırpar, ama Python aynı şekilde kırpmazsa hedef açı sınırın ötesine kayar ve kol bırakıldığında taret gecikmeli tepki verir.
- Model ağırlıkları (`models/*.pt`) gitignore'dadır — sürüm kontrolüne dahil değildir.

## İlgili koda dokunmadan önce bilinmesi gereken tuzaklar

- `vision/detector.py` gerçek YOLO çıktısını yalnızca `USE_YOLO=True` iken üretir. Sınıf eşlemesi (`MODEL_CLASS_MAP`) ve sınıf sırası varsayımı (`['drone','f16','fuze','heli','balon']` == `core.enums.TargetClass` sırası), yüklenen `.pt` ile uyumlu kalmalıdır — farklı sırada eğitilmiş bir model takılırsa kod değil eşleme düzeltilir.
- Bazı kameralar MJPG'den YUY2'ye düşer ve USB 2.0 üzerinden 720p@30'u sürdüremez; bu bilinen bir donanım kısıtıdır, kod hatası değildir.
- `core.state.COMMAND_QUEUE` her kontrol döngüsü turunda boşaltılmalıdır (`param_bridge._drain_commands`) — tüketilmeyen kuyruk dolar ve yeni tetikleyici komutları `INTERNAL_ERROR` ile reddetmeye başlar.
- Koordinat uzayları: tespitler kaynak çözünürlükte (1920x1080), yayın 1280x720'dir. Ölçek dönüşümü tekrarlayan bir hata kaynağıdır — her seferinde kontrol edilmelidir.
- Git merge'leri, tek tek doğru olan iki ayar değişikliğini hiçbir çakışma işareti olmadan yanlış bir sonuca birleştirebilir (ör. bir dal `ANALOG_*_RATE_DPS`'i, diğeri `AUTO_RATE_FACTOR`'ü artırır → otonom hız üç katına çıkar). Merge sonrasında yalnızca çakışan satırlara değil, birbirine bağlı sabitlerin *birleşik* değerine de bakılmalıdır.

## Önce oku

- `docs/protocol_spec.md` — UDP protokolü, parametre kataloğu (TEK doğruluk kaynağı)

## Değişmez kurallar

- Protokol değişikliği ÖNCE `protocol_spec.md`'de yapılır
- `settings.py` ortak dosyadır; her sabit TEK yerde tanımlanır
- Tek yazıcı ilkesi: bir parametreye tek katman yazar
- Python eksen limitleri firmware'dekiyle BİREBİR eşleşmelidir
- Koordinat uzayı: tespitler kaynak (1920x1080), yayın (1280x720) çözünürlüğündedir; ölçek dönüşümü her seferinde kontrol edilir

## Son çözülen sorun: otonom takip yavaşlığı

Otonom takip hedefe 3-10 sn'de oturuyordu. İlk şüphe `TURRET_FULL_INPUT_PX=500` kaynaklı düşük kazançtı; kademeli olarak 150'ye indirildi ama tek başına yetmedi.

Asıl sebep hız tavanıydı: otonom hız `ANALOG_*_RATE_DPS * AUTO_RATE_FACTOR` formülüyle türetiliyor. Eskiden ayarlanan `AUTO_PAN_RATE_DPS`/`AUTO_TILT_RATE_DPS` hiçbir yerde okunmayan ölü sabitlerdi; kaldırıldılar.

- Doğrulanmış referans (31 Ağustos, gerçek kamera): `ANALOG 25/18 × 0.43` → pan 10.75, tilt 7.7 °/s
- Eylül 2026 merge'ünde manuel hızlar firmware'e göre 75/70'e çıkarıldığı için çarpan 0.14'te tutuldu: `ANALOG 75/70 × 0.14` → pan 10.5, tilt 9.8 °/s
- Pan referansla aynı; tilt ~%27 hızlı, sahada doğrulanmalı

## Yapılmamış işler

- Tilt otonom hızını sahada doğrula; aşım yaparsa pan/tilt için ayrı `AUTO_RATE_FACTOR` ekle
- Eksen limitlerinin (`PAN_*`/`TILT_*_DEG`, `HOME_*`) güncel firmware ile birebir eşleştiğini teyit et
- `local_settings` import'u `settings.py` sonuna taşınmalı
- Ego-motion kalibrasyonu (`EGO_MOTION_ENABLED=False`; `EGO_PX_PER_PAN_UNIT=17.5` yanlış hesaplanmış, ~25 olmalı)
- `BACKLASH_*` değerleri ölçülmedi
- `serial_protocol.py` başındaki geçersiz UYARI bloğu silinmeli
- `test_receiver.py` `draw_aim` ölçekleme hatası
- Firmware: trigger2 tamamen yorum satırında (tek namlu)