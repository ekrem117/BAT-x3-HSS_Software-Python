# BAT-X3 — Hava Savunma Taret Sistemi (Python Alt Sistemi)

TEKNOFEST 2026 Çelik Kubbe Hava Savunma Sistemleri yarışması için geliştirilen otonom taret yazılımı. Kamera görüntüsünden hedefleri tespit eder, takip eder, dost/düşman ayrımı yapar ve Arduino kontrollü pan-tilt taretini manuel ya da otonom olarak yönlendirir.

Bu depo sistemin Python tarafıdır. Operatör arayüzü (C#) ve taret firmware'i (Arduino) ayrı projelerdir; bu yazılımla UDP ve seri port üzerinden haberleşir.
Operatör arayüzü: [ekrem117/BAT-x3-HSS-GUI](https://github.com/ekrem117/BAT-x3-HSS-GUI)

## Özellikler

- **Tespit:** YOLO (Ultralytics) ile 5 sınıf — drone, F-16, füze, helikopter, balon
- **Takip:** BoT-SORT / ByteTrack, iz başına Kalman hareket modeli, takipçi ID değişimlerine dayanıklı hedef kilidi
- **Sınıflandırma:** HSV tabanlı dost/düşman renk analizi
- **Mesafe kestirimi:** Bilinen boyutlu balon üzerinden monoküler mesafe
- **Nişan:** Öngörü süresi, maket–balon ofseti, isteğe bağlı balistik ve paralaks düzeltmesi
- **Kontrol:** Mod durum makinesi, dijital + analog + hassas manuel kontrol, otonom takip ve angajman, sunum modu, acil durdurma
- **Arayüz haberleşmesi:** UDP üzerinden GET/SET komut protokolü, video ve tespit yayını

## Mimari

Bağımlılıklar tek yönde akar. `core/` başka hiçbir katmanı tanımaz; katmanlar birbirini doğrudan değil, `core/` üzerinden tanır.

```
config/   Tüm sabitler (tek kaynak)
   ↓
core/     Paylaşılan durum: parametre kataloğu, komut kuyruğu, enum'lar
   ↓
 ┌────────────┬────────────┬────────────┬────────────┐
 vision/    protocols/    control/    hardware/
 kare,      ağ:           karar,       Arduino
 tespit,    UDP + TCP     taret        seri port
 takip                    sürme
```

Görüntü işleme hattı:

```
frame_buffer → detection_buffer → track_store → threat / engagement → aiming → turret_driver → SystemManager → Arduino
 (kamera)       (YOLO + renk +      (Kalman)     (hedef seçimi,        (nişan)   (piksel hatası
                 mesafe)                          kilit yönetimi)                  → eksen komutu)
```

Her servis kendi thread'inde çalışır. Tespit model hızında (onlarca–yüzlerce ms), takip döngüsü ise tespitten bağımsız olarak 50 Hz'de Kalman tahminiyle çalışır.

## Gereksinimler

- Python 3.11 (geliştirme ve testler Windows üzerinde yapıldı)
- USB kamera (Logitech Brio ile test edildi)
- Arduino + servo tabanlı pan-tilt taret (donanım olmadan da çalıştırılabilir, bkz. [Donanımsız çalıştırma](#donanımsız-çalıştırma))
- NVIDIA GPU önerilir; CPU'da da çalışır ama çıkarım yavaşlar

## Kurulum

```bash
python -m venv venv
venv\Scripts\activate            # Linux/macOS: source venv/bin/activate
pip install -r requirements.txt

pip install pynput pygame        # isteğe bağlı: klavye/oyun kolu kumanda araçları
```

### Model dosyası

**Eğitilmiş YOLO ağırlıkları bu depoya dahil değildir.** Kendi veri setinizle bir Ultralytics YOLO modeli eğitip `models/` klasörüne koyun ve yolunu `config/settings.py` içinde belirtin:

```python
MODEL_PATH = "models/modeliniz.pt"
```

Model şu sınıf sırasıyla eğitilmiş olmalıdır: `['drone', 'f16', 'fuze', 'heli', 'balon']`. Farklı bir sıra kullanırsanız yalnızca `MODEL_CLASS_MAP` tablosunu güncellemeniz yeterlidir.

Model olmadan denemek için `USE_YOLO = False` (sentetik tespit) veya `USE_COLOR_DETECTOR = True` (renk tabanlı tespit) kullanılabilir.

## Yapılandırma

Tüm ayarlar `config/settings.py` dosyasındadır; her sabitin yanında neden o değerde olduğu açıklanır. Bir ayar sabitini değiştirmeden önce yorumunu okuyun — birçoğu sahada ölçülmüş kalibrasyon sonuçlarıdır.

**Kişisel/geçici değişiklikler için `settings.py` düzenlenmez.** Bunun yerine `config/local_settings.py` oluşturulur (git'e dahil edilmez) ve ezilmek istenen değerler oraya yazılır:

```python
# config/local_settings.py
SERIAL_PORT = "COM3"
CAMERA_INDEX = 0
```

> Not: `local_settings` şu anda `settings.py` dosyasının ortasında yüklenir. Bu noktadan sonra tanımlanan değerler (nişan, taret sürme, eksen limitleri, analog kontrol) yerel olarak ezilemez.

Sık değiştirilen ayarlar:

| Ayar | Açıklama |
|---|---|
| `SERIAL_PORT` | Arduino'nun bağlı olduğu port (`COM5`, `/dev/ttyACM0`) |
| `CAMERA_INDEX` / `USE_CAMERA` | Kamera indeksi / `False` ise sentetik kare |
| `MODEL_PATH` | YOLO ağırlık dosyası |
| `ENABLE_*` | Servisleri (kontrol, ağ, video, tespit, MJPEG, takip) ayrı ayrı açar/kapatır |
| `PAN_*_DEG` / `TILT_*_DEG` | Eksen limitleri — **firmware'deki değerlerle birebir aynı olmalıdır** |
| `ANALOG_*_RATE_DPS` | Manuel analog kontrolde azami eksen hızı |
| `AUTO_RATE_FACTOR` | Otonom azami hız çarpanı (aşağıya bakın) |
| `DEBUG_OVERLAY` | Kare üzerine tanı bilgisi çizer — **yarışmada `False` olmalıdır** |

**Otonom hız ayrı bir sabit değildir,** manuel hızdan türetilir: `ANALOG_*_RATE_DPS × AUTO_RATE_FACTOR`. Manuel hızı değiştirirseniz otonom hız da aynı oranda değişir; çarpanı yeniden hesaplayın.

## Çalıştırma

```bash
python main.py
```

Tüm servisler tek süreçte başlar; `Ctrl+C` ile durdurulur. Log'da "kontrol katmani acik" ifadesi kontrol katmanının başladığını gösterir. Loglar `logs/` klasörüne yazılır.

Arayüz olmadan tareti kumanda etmek için **ayrı bir terminalde**:

```bash
python -m tools.manual_wasd            # klavye (yön tuşları)
python -m tools.manual_analog_wasd     # klavye (analog / mutlak açı)
python -m tools.manual_gamepad         # oyun kolu
```

`manual_wasd` tuşları:

| Tuş | İşlev |
|---|---|
| `W A S D` | Yön (birlikte basılabilir) |
| `M` / `I` | MANUAL / IDLE moduna geç |
| `N` | AUTO moduna geç (otonom takip) |
| `K` / `J` | ARM aç-kapa / ateş |
| `L` / `V` | Sunum modu: tarama / elips |
| `T` / `Y` | Acil durdur / acil durdurmadan çık |
| `P` | Durum sorgula |
| `ESC` | Çıkış |

Görüntüyü izlemek için tarayıcıda `http://localhost:8080/` açın veya `python tools/test_receiver.py` çalıştırın.

### Çalışma modları

`IDLE`, `MANUAL`, `AUTO`, `LOOP_DEMO`, `ESTOP`. İki çalışma modu arasında doğrudan geçiş yoktur; her geçiş `IDLE` üzerinden yapılır. `ESTOP`'a her moddan girilebilir, yalnızca `IDLE`'a çıkılabilir. Her mod değişiminde silah güvenliğe alınır.

### Donanımsız çalıştırma

`config/local_settings.py` ile donanım gerektiren bileşenler kapatılabilir:

```python
ENABLE_CONTROL = False     # Arduino yok
USE_CAMERA = False         # sentetik hareketli kare
USE_YOLO = False           # sentetik tespitler
```

Sentetik üreteç dost, düşman, bilinmeyen ve balon hedeflerini hareket ettirir; kilitlenme ve angajman mantığı normal şekilde çalışır. Arayüz geliştirmek için gerçek kameradan daha tekrarlanabilirdir.

## Arayüz haberleşmesi

| Kanal | Protokol | Port | Yön |
|---|---|---|---|
| Komut / ayar (GET/SET) | UDP | 5005 | İstek–cevap |
| Video | UDP | 5007 | Yayın |
| Tespit | UDP | 5008 | Yayın |
| Tanı (MJPEG) | TCP/HTTP | 8080 | Tarayıcıya yayın |

Video ve tespit paketleri aynı `frame_id`'yi taşır; istemci kutuları doğru kareyle eşleştirebilir. Tespit koordinatları kaynak çözünürlüktedir (1920×1080), video yayını 1280×720'dir.

Paket formatları, parametre kataloğu ve hata kodları: [docs/protocol_spec.md](docs/protocol_spec.md)

Örnek sorgu (5005 portuna):

```json
{"Method":"GET","messageID":1,"system.fps":"?"}
```

## Donanım haberleşmesi

Python, Arduino ile 115200 baud seri port üzerinden konuşur. İki komut biçimi vardır:

- **Tek bayt:** yön bit maskesi (manuel) ve özel komutlar (HOME, ateş, acil durdur, serbest bırak)
- **5 bayt `0xFB` çerçevesi:** mutlak pan/tilt açısı (analog kontrol ve otonom takip)

Bayt tanımları `hardware/serial_protocol.py` içindedir ve **firmware ile birebir eşleşmelidir**; bir tarafta değişip diğerinde değişmeyen sabit hata vermez, sessizce yanlış komut üretir. Arduino'dan konum geri beslemesi yoktur; taret konumunun tek kaynağı Python tarafındaki hedef açıdır.

## Klasör yapısı

### `config/`
| Dosya | İşlev |
|---|---|
| `settings.py` | Tüm sabitler — tek yapılandırma kaynağı |
| `botsort.yaml` / `bytetrack.yaml` | Takipçi yapılandırmaları |

### `core/`
| Dosya | İşlev |
|---|---|
| `state.py` | Parametre kataloğu, anlık değerler, komut kuyruğu |
| `enums.py` | Durum kodları, mod, sınıf, takım ve erişim sabitleri |
| `ego_motion.py` | Taret dönerken kamera hareketi telafisi |
| `logging_setup.py` | Log yapılandırması |

### `vision/`
| Dosya | İşlev |
|---|---|
| `frame_source.py` | Kare kaynağı (kamera veya sentetik) |
| `frame_buffer.py` | Paylaşılan son kare — kamera tek thread'de bir kez açılır |
| `detector.py` | YOLO tespit sarmalayıcısı |
| `color_detector.py` | Renk tabanlı tespit (model yerine) |
| `synthetic.py` / `synthetic_detector.py` | Sentetik kare ve tespit üreticileri |
| `detection_buffer.py` | Çıkarım thread'i ve tespit tamponu |
| `classifier.py` | Dost/düşman renk sınıflandırması |
| `association.py` | Balon–maket eşleştirmesi |
| `ranging.py` | Mesafe kestirimi |
| `motion.py` | Kalman hareket modeli |
| `track_store.py` | İz deposu ve konum tahmini |
| `ballistics.py` | Balistik ve paralaks düzeltmesi |
| `encoder.py` | JPEG kodlama |

### `control/`
| Dosya | İşlev |
|---|---|
| `system_manager.py` | Tek karar merkezi: modlar, güvenlik kuralları, seri komut üretimi |
| `param_bridge.py` | Parametre kataloğu ile `SystemManager` arasındaki köprü |
| `tracking_loop.py` | 50 Hz takip ve angajman döngüsü |
| `threat.py` | Tehdit önceliklendirme ve hedef seçimi |
| `engagement.py` | Angajman durum makinesi (kilit, kayıp, imha teyidi) |
| `aiming.py` | Nişan çözümü |
| `turret_driver.py` | Nişan hatasını eksen komutuna çevirir |
| `loop_demo.py` | Sunum modu koreografisi |

### `protocols/`
| Dosya | İşlev |
|---|---|
| `udp/command_server.py` | GET/SET komut sunucusu |
| `udp/dispatcher.py` | Mesaj doğrulama ve işleme (soketten bağımsız) |
| `udp/video_server.py` | Video yayını |
| `udp/detection_server.py` | Tespit yayını |
| `tcp/mjpeg_server.py` | Tarayıcı tanı yayını |

### `hardware/`
| Dosya | İşlev |
|---|---|
| `arduino_link.py` | Seri port sahibi: bağlantı, heartbeat, yeniden bağlanma |
| `serial_protocol.py` | Bayt sabitleri ve çerçeve kodlama |

### `tools/`
Geliştirme ve doğrulama araçları; üretim kodunun parçası değildir.

| Araç | İşlev | `main.py` açık olmalı mı? |
|---|---|---|
| `manual_wasd` / `manual_analog_wasd` / `manual_gamepad` | Arayüz yerine klavye/oyun kolu kumandası | Evet |
| `test_receiver.py` | Video + tespit alıcısı, gecikme ve kare kaybı istatistikleri | Evet |
| `auto_probe` | Otonom zincirin nerede koptuğunu adım adım gösterir | Evet |
| `track_bench` | Otonom takip performansı ölçümü | Evet |
| `ego_calibrate` | Ego-motion ölçek kalibrasyonu | Evet |
| `control_test` | Kontrol mantığı testi — donanım ve ağ gerektirmez | Hayır |
| `hardware_test` | Adım adım gerçek Arduino testi | Hayır |
| `backlash_test` / `deadband_test` / `diagonal_test` | Eksen davranışı ölçümleri | Hayır |
| `bench.py` | Kamera ve kodlama performans ölçümü | Hayır |
| `live_predict` / `track_debug` / `balloon_debug` | Model ve takip teşhis araçları | Hayır |
| `gamepad_probe` | Oyun kolu eksen/düğme keşfi | Hayır |
| `run_dev.bat` | `main.py` + `test_receiver.py`'yi birlikte başlatır (Windows) | — |

Modül olarak çalıştırılanlar `python -m tools.<ad>` şeklinde başlatılır.

## Yeni parametre ekleme

Arayüzden okunacak/yazılacak yeni bir parametre için yalnızca `core/state.py` güncellenir; protokol katmanına dokunulmaz:

```python
PARAM_DEFS["turret.pan"] = {
    "type": float,
    "access": Access.RO,
    "min": -180.0,
    "max": 180.0,
    "unit": "derece",
    "desc": "Yatay eksen açısı",
}
PARAM_VALUES["turret.pan"] = 0.0
```

Ardından `docs/protocol_spec.md` Bölüm 9 güncellenir.

## Bilinen kısıtlar

- **Konum geri beslemesi yok.** Servolar açık çevrimdir; mekanik engellenme yazılım tarafından algılanamaz.
- **Ego-motion telafisi kalibre edilmedi** (`EGO_MOTION_ENABLED = False`).
- **Tek namlu.** İkinci tetik firmware'de devre dışıdır.
- **Kamera formatı.** Bazı kameralar MJPG yerine YUY2'ye düşer; USB 2.0 üzerinde 720p@30 sürdürülemez.
- **Otomatik test paketi yoktur;** doğrulama `tools/` altındaki araçlarla yapılır.

## Bağımlılıklar hakkında

Nesne tespiti ve takip için kullanılan [Ultralytics](https://github.com/ultralytics/ultralytics) kütüphanesi AGPL-3.0 lisanslıdır. Bu yazılımı kullanacak veya dağıtacaksanız Ultralytics lisans koşullarını ayrıca değerlendirin.
