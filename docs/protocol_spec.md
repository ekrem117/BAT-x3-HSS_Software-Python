# BAT-X3 — UDP JSON Protokol Spesifikasyonu

**Doküman No:** BATX3-PROTO-001
**Sürüm:** 1.4
**Referans:** UDP_Protocol.docx

> Bu doküman Python (sunucu) ve C# (istemci) taraflarının **tek ortak kaynağıdır**.
> Protokol değişikliği önce burada yapılır, sonra iki tarafa yansıtılır.

---

## 1. Taşıma Katmanı

| Özellik | Değer |
|---|---|
| Protokol | UDP |
| Sunucu adresi | 127.0.0.1 |
| Sunucu portu | 5005 (dinleme) |
| İstemci portu | 5006 (varsayılan) |
| Kodlama | UTF-8 |
| Maksimum datagram | 65535 bayt |
| Cevap adresi | İsteğin geldiği adres (sabit değil) |

Sunucu, cevabı isteğin geldiği adrese gönderir. İstemci portunu değiştirebilir; sunucu kodunda değişiklik gerekmez.

---

## 2. Mesaj Yapısı

Tüm mesajlar tek bir JSON nesnesidir. Rezerve alanlar ve değişkenler aynı seviyede bulunur.

### 2.1 Rezerve Alanlar

| Alan | Tip | Açıklama |
|---|---|---|
| `Method` | string | `GET`, `SET`, `GETRSP`, `SETRSP`, `ERRRSP` |
| `messageID` | integer | İstek numarası. Cevapta aynen geri döner. |

Bu iki isim parametre adı olarak kullanılamaz.

### 2.2 Değişkenler

Rezerve alanlar dışındaki her anahtar bir parametre adıdır. Bir mesajda birden fazla parametre bulunabilir.

---

## 3. Mesaj Tipleri

`Method` değeri büyük/küçük harf duyarsızdır: `GET`, `get` ve `Get` aynı şekilde işlenir. Alan adlarının kendisi (`Method`, `messageID`) tam eşleşmelidir.

### 3.1 GET — Değer Okuma

İstenen parametrelerin değerine `"?"` yazılır. Sunucu değeri kontrol etmez; anahtarın varlığı yeterlidir.

```json
{
  "Method": "GET",
  "messageID": 1001,
  "control.pid.kp": "?",
  "weapon.ammo": "?"
}
```

### 3.2 GETRSP — Okuma Cevabı

Her parametre için `{status, value}` nesnesi döner.

```json
{
  "Method": "GETRSP",
  "messageID": 1001,
  "control.pid.kp": {"status": 0, "value": 2.5},
  "weapon.ammo": {"status": 0, "value": 30}
}
```

Kısmi başarı desteklenir; her parametrenin durumu bağımsızdır.

```json
{
  "Method": "GETRSP",
  "messageID": 1002,
  "control.pid.kp": {"status": 0, "value": 2.5},
  "yok.olan": {"status": 2, "value": null}
}
```

### 3.3 SET — Değer Yazma

```json
{
  "Method": "SET",
  "messageID": 1003,
  "vision.enemy.h_max": 12,
  "control.pid.kp": 3.0
}
```

### 3.4 SETRSP — Yazma Cevabı

`value` alanı, isteğin değeri değil **sistemde yerleşen** değerdir.

```json
{
  "Method": "SETRSP",
  "messageID": 1003,
  "vision.enemy.h_max": {"status": 0, "value": 12},
  "control.pid.kp": {"status": 0, "value": 3.0}
}
```

### 3.5 ERRRSP — Mesaj Seviyesi Hata

**Kural:** `Method` alanı `GET` veya `SET` olarak okunabiliyorsa cevap her zaman `GETRSP` veya `SETRSP` tipindedir; hata detayı değişken bazlı `status` alanında bildirilir. Bu, istemcinin cevabı `messageID` ile eşleştirebilmesi için gereklidir.

`ERRRSP` yalnızca `Method` belirlenemediğinde döner:

**Tanınmayan veya eksik `Method`:**
```json
{"Method": "ERRRSP", "messageID": 1004, "status": 1}
```

**Bozuk JSON:**
```json
{"Method": "ERRRSP", "messageID": null, "status": 3}
```

JSON çözülemediği için `messageID` okunamaz, `null` döner.

---

## 4. Durum Kodları

| Kod | İsim | Açıklama |
|---|---|---|
| 0 | `SUCCESS` | İşlem başarılı |
| 1 | `UNDEFINED_METHOD_TYPE` | Method tanınmadı veya eksik |
| 2 | `UNDEFINED_KEY` | Parametre tanımsız |
| 3 | `MESSAGE_FORMAT_ERROR` | JSON formatı hatalı |
| 4 | `VALUE_TYPE_ERROR` | Değer tipi uyuşmuyor |
| 5 | `ACCESS_TYPE_ERROR` | Erişim izni yok |
| 6 | `INVALID_VALUE` | Değer boş (null) |
| 7 | `VALUE_LENGTH_ERROR` | Metin uzunluğu sınır dışı |
| 8 | `VALUE_RANGE_ERROR` | Değer izin verilen aralık dışında |
| 9 | `INTERNAL_ERROR` | Sunucu iç hatası (örn. komut kuyruğu dolu) |
| 10 | `READ_ERROR` | Değişken okuma hatası |
| 11 | `WRITE_ERROR` | Değişken yazma hatası |

**Kural:** `status != 0` ise `value` alanı her zaman `null` döner.

---

## 5. Erişim Tipleri

| Tip | GET | SET | Açıklama |
|---|---|---|---|
| `RO` | ✓ | ✗ | Salt okunur. SET denemesi → kod 5 |
| `RW` | ✓ | ✓ | Okunur ve yazılır |
| `WRO` | ✗ | ✓ | Salt yazılır. GET denemesi → kod 5 |

---

## 6. Doğrulama Sırası

SET işleminde kontroller şu sırayla yapılır. İlk başarısız kontrol sonucu döndürür.

| # | Kontrol | Hata kodu |
|---|---|---|
| 1 | Parametre katalogda var mı | 2 |
| 2 | Erişim tipi yazmaya izin veriyor mu | 5 |
| 3 | Değer `null` mı | 6 |
| 4 | Tip uyuşuyor mu | 4 |
| 5 | Sınırlar içinde mi | 8 |

GET işleminde:

| # | Kontrol | Hata kodu |
|---|---|---|
| 1 | Parametre katalogda var mı | 2 |
| 2 | Erişim tipi okumaya izin veriyor mu | 5 |

---

## 7. Tetikleyici Parametreler

Bazı parametreler bir değeri değil, bir eylemi temsil eder. Bunlar `WRO` erişimlidir ve değerleri saklanmaz.

**Davranış:**
- SET edildiğinde değer saklanmaz, komut kuyruğuna alınır
- SETRSP her zaman `{"status": 0, "value": 0}` döner
- GET edilemez (kod 5)

**Mevcut tetikleyiciler:**

| Parametre | Açıklama |
|---|---|
| `weapon.fire` | Ateş komutu |

**Örnek:**
```json
İstek : {"Method":"SET","messageID":1005,"weapon.fire":1}
Cevap : {"Method":"SETRSP","messageID":1005,"weapon.fire":{"status":0,"value":0}}
```

`status: 0` komutun **kabul edildiğini** bildirir; eylemin tamamlandığını değil. İstemci sonucu `weapon.ammo` ve `weapon.shots_fired` parametrelerinden takip eder.

---

## 8. İstemci Tarafı Kuralları

### 8.1 messageID Yönetimi

- Her yeni istek için artan bir sayaç kullanılır
- Cevaplar `messageID` ile eşleştirilir
- UDP sıra garantisi vermez; cevaplar farklı sırada gelebilir

### 8.2 Zaman Aşımı

Cevap gelmezse istek zaman aşımına uğramış sayılır. Önerilen süre: 300 ms.

### 8.3 Tekrar Gönderim

| Mesaj tipi | Tekrar |
|---|---|
| GET | Serbest — okuma yan etkisizdir |
| SET (normal parametre) | Serbest — aynı değeri yazmak yan etkisizdir |
| SET (tetikleyici) | **YAPILMAZ** — eylem tekrarlanabilir |

Tetikleyici bir komutun cevabı gelmezse istemci otomatik tekrar göndermez. Kullanıcıya "durum bilinmiyor" bildirilir; kullanıcı ilgili sayaçları kontrol ederek karar verir.

### 8.4 Periyodik Sorgu

Durum parametreleri (RO) periyodik GET ile sorgulanır. Önerilen periyot: 50 ms (20 Hz).

Birden fazla parametre **tek mesajda** sorgulanmalıdır. Parametre başına ayrı mesaj gönderilmesi gereksiz paket trafiği yaratır.

---

## 9. Parametre Kataloğu

> Kaynak: `core/state.py`. Yeni parametre eklendiğinde bu bölüm güncellenmelidir.

### 9.1 Sistem Durumu

| Parametre | Tip | Erişim | Min | Max | Birim | Açıklama |
|---|---|---|---|---|---|---|
| `system.mode` | int | RW | 0 | 4 | — | Çalışma modu (§9.2) |
| `system.link` | int | RO | 0 | 2 | — | Arduino bağlantı durumu (§9.3) |
| `system.fps` | float | RO | 0.0 | 200.0 | fps | Anlık kare yakalama hızı |

### 9.2 Sistem Modları

| Kod | Ad | Açıklama |
|---|---|---|
| 0 | `IDLE` | Boşta, güvenli. Mod geçişlerinin uğrak noktası. |
| 1 | `MANUAL` | Operatör kontrolü (Aşama-1) |
| 2 | `AUTO` | Otonom hedef takibi |
| 3 | `LOOP_DEMO` | Sunum modu: önceden tanımlı hareket döngüsü |
| 4 | `ESTOP` | Acil durdurma etkin |

**Geçiş kuralı:** Çalışma modları arasında doğrudan geçiş yoktur; her geçiş `IDLE` üzerinden yapılır. Böylece taret bir an sahipsiz kalmaz ve basılı tuşlar temizlenir. `ESTOP` her modtan girilebilir, yalnızca `IDLE`'a çıkılır.

Mod değişiminde `weapon.armed` güvenlik gereği otomatik olarak 0'a düşürülür.

`LOOP_DEMO` modunda taretin tek sahibi hareket döngüsüdür: `motion.manual.*` ve `motion.analog.*` girdileri sessizce yok sayılır, `weapon.armed` açılamaz. Döngü `IDLE`'a (acil durumda `ESTOP`'a) geçilerek durdurulur; taret bulunduğu yerde kalır.

Döngünün hareket düzeni `motion.demo.pattern` ile seçilir:

| Parametre | Tip | Erişim | Min | Max | Açıklama |
|---|---|---|---|---|---|
| `motion.demo.pattern` | int | RW | 0 | 1 | 0 = yatay tarama + çaprazlar, 1 = elips |
| `motion.demo.pan_lead` | float | RW | -1.0 | 1.0 | Elipste pan'ın tilt'ten önde sürülme süresi (s) |

`motion.demo.pattern` mod değiştirilmeden de yazılabilir; `LOOP_DEMO` sırasında değişirse yeni düzen taretin bulunduğu yerden başlar.

`motion.demo.pan_lead` pan ekseninin fiziksel gecikmesini telafi eder: doğru değerde tilt tam tepedeyken pan tam ortadadır. Elips dönerken değiştirilebilir ve yumuşakça uygulanır; varsayılanı `DEMO_ELLIPSE_PAN_LEAD_S` ayarından gelir. Tarama düzenini etkilemez.

### 9.3 Bağlantı Durumları

| Kod | Ad | Açıklama |
|---|---|---|
| 0 | `DISCONNECTED` | Seri port açılmadı veya kapandı |
| 1 | `CONNECTED` | Port açık, son yazma başarılı |
| 2 | `TIMEOUT` | Port açık ancak Arduino watchdog süresinde yanıt vermedi |

### 9.4 Manuel Hareket

Arayüz, tuş basılıyken 1, bırakıldığında 0 gönderir. Sürekli SET yerine her tuş olayında bir kez SET beklenir.

| Parametre | Tip | Erişim | Min | Max | Açıklama |
|---|---|---|---|---|---|
| `motion.manual.up` | int | RW | 0 | 1 | Tilt yukarı (W) |
| `motion.manual.down` | int | RW | 0 | 1 | Tilt aşağı (S) |
| `motion.manual.left` | int | RW | 0 | 1 | Pan sola (A) |
| `motion.manual.right` | int | RW | 0 | 1 | Pan sağa (D) |

Zıt yönler birbirini iptal eder. Bu parametreler yalnızca `MANUAL` modunda işlenir; diğer modlarda sessizce yok sayılır.

### 9.5 Silah

| Parametre | Tip | Erişim | Min | Max | Birim | Açıklama |
|---|---|---|---|---|---|---|
| `weapon.armed` | int | RW | 0 | 1 | — | Ateş yetkisi (0=kapalı, 1=açık) |
| `weapon.fire_mode` | int | RW | 0 | 1 | — | Atış modu (0=tekli, 1=seri) |
| `weapon.burst_count` | int | RW | 1 | 10 | adet | Seri atış mermi sayısı |
| `weapon.selected` | int | RW | 0 | 2 | — | Seçili namlu (0=sol, 1=sağ, 2=her ikisi) |
| `weapon.ammo` | int | RO | 0 | 100 | adet | Kalan mermi |
| `weapon.shots_fired` | int | RO | 0 | 9999 | adet | Toplam atılan mermi |
| `weapon.fire` | int | WRO | 0 | 1 | — | Ateş tetikleyici (§7) |

`weapon.armed` yalnızca `MANUAL` ve `AUTO` modlarında açılabilir; kapatma her modda serbesttir.

### 9.6 Görüntü İşleme — Renk Analizi

Dost/düşman ayrımı bounding box içindeki baskın renge göre yapılır. Kırmızı, HSV renk çemberinin başında olduğu için iki aralıkta aranır.

| Parametre | Tip | Erişim | Min | Max | Açıklama |
|---|---|---|---|---|---|
| `vision.enemy.h_min` | int | RW | 0 | 179 | Düşman ton alt eşiği (alt aralık) |
| `vision.enemy.h_max` | int | RW | 0 | 179 | Düşman ton üst eşiği (alt aralık) |
| `vision.enemy.h_min2` | int | RW | 0 | 179 | Düşman ton alt eşiği (üst aralık) |
| `vision.enemy.h_max2` | int | RW | 0 | 179 | Düşman ton üst eşiği (üst aralık) |
| `vision.enemy.s_min` | int | RW | 0 | 255 | Düşman minimum doygunluk |
| `vision.enemy.v_min` | int | RW | 0 | 255 | Düşman minimum parlaklık |
| `vision.friend.h_min` | int | RW | 0 | 179 | Dost ton alt eşiği |
| `vision.friend.h_max` | int | RW | 0 | 179 | Dost ton üst eşiği |
| `vision.friend.s_min` | int | RW | 0 | 255 | Dost minimum doygunluk |
| `vision.friend.v_min` | int | RW | 0 | 255 | Dost minimum parlaklık |

Şartname renkleri: düşman kırmızı `#F50A0A`, dost camgöbeği `#00A3E0`.

Eşikler çalışma sırasında değiştirilebilir; arayüz kalibrasyon ekranında canlı önizleme sağlayabilir.

### 9.7 Görüntü İşleme — Tespit

| Parametre | Tip | Erişim | Min | Max | Birim | Açıklama |
|---|---|---|---|---|---|---|
| `vision.conf_threshold` | float | RW | 0.0 | 1.0 | — | Minimum tespit güven eşiği |
| `vision.detection_count` | int | RO | 0 | 100 | adet | Son karedeki tespit sayısı |
| `vision.inference_ms` | float | RO | 0.0 | 10000.0 | ms | Model çıkarım süresi |

### 9.8 Kontrol

| Parametre | Tip | Erişim | Min | Max | Açıklama |
|---|---|---|---|---|---|
| `control.pid.kp` | float | RW | 0.0 | 10.0 | PID oransal kazanç |

### 9.9 Planlanan Parametreler

Aşağıdakiler henüz uygulanmamıştır; kontrol ve donanım katmanları geliştirildiğinde eklenecektir.

| Parametre | Tip | Erişim | Açıklama |
|---|---|---|---|
| `turret.pan` | float | RO | Komut edilen yatay açı |
| `turret.tilt` | float | RO | Komut edilen dikey açı |
| `turret.home` | int | WRO | 0/0 referans konumuna dönüş tetikleyicisi |
| `system.estop` | int | WRO | Acil durdurma tetikleyicisi |

Sistem açık döngü servo mimarisi kullanır; `turret.pan` ve `turret.tilt` **komut edilen** açıyı bildirir, ölçülen açıyı değil.

---

## 10. Video Yayını (UDP 5007)

Video, GET/SET protokolünden bağımsız bir kanaldır. Sunucu istemciden istek beklemez; sürekli yayın yapar.

### 10.1 Genel Özellikler

| Özellik | Değer |
|---|---|
| Protokol | UDP, tek yönlü yayın |
| Port | 5007 |
| Hız | ~30 Hz (kaynak hızına bağlı) |
| Sıkıştırma | JPEG, kalite 40–80 (dinamik) |
| Paket başına | Bir tam kare — parçalama yapılmaz |
| Tipik boyut | 20–60 KB |

Kare boyutu üst sınırı aşarsa sunucu JPEG kalitesini kademeli düşürür (80 → 70 → 60 → 50 → 40). Bu, tek datagram sınırının aşılmamasını garanti eder.

**Yayın çözünürlüğü yakalama çözünürlüğünden bağımsızdır.** Model yüksek çözünürlüklü kareyi kullanırken arayüze küçültülmüş kare gönderilir; böylece tespit doğruluğu korunur ve datagram sınırı aşılmaz.

### 10.2 Paket Yapısı

24 baytlık başlık + JPEG verisi. Tüm sayısal alanlar **little-endian**.

| Offset | Boyut | Alan | Tip | Açıklama |
|---|---|---|---|---|
| 0 | 4 | `magic` | char[4] | Sabit `"BX3F"` (0x42 0x58 0x33 0x46) |
| 4 | 4 | `frame_id` | uint32 | Kare sayacı |
| 8 | 8 | `timestamp` | double | Üretim zamanı (Unix epoch, saniye) |
| 16 | 4 | `jpeg_size` | uint32 | JPEG verisinin bayt sayısı |
| 20 | 2 | `width` | uint16 | **Yayın** genişliği (piksel) |
| 22 | 2 | `height` | uint16 | **Yayın** yüksekliği (piksel) |
| 24 | değişken | `jpeg` | byte[] | JPEG verisi |

`width` ve `height` alanları yayın çözünürlüğünü bildirir. Tespit koordinatları kaynak çözünürlüktedir; ölçekleme için §11.5'e bakınız.

### 10.3 İstemci Kuralları

**Doğrulama.** `magic` alanı `"BX3F"` değilse paket yok sayılmalıdır. Başka bir uygulamadan gelen paketler bu şekilde ayıklanır.

**Boyut kontrolü.** `jpeg_size` ile gerçek veri uzunluğu uyuşmuyorsa paket yok sayılmalıdır.

**Kare atlama.** `frame_id` sürekli artar. Atlama olması normaldir — alıcı yetişemediğinde paket düşer. İstemci eksik kareleri talep etmemelidir; bir sonraki paket daha güncel veriyi taşır.

**Gecikme ölçümü.** `timestamp` ile alım zamanı arasındaki fark, yayın hattının gecikmesini verir. Bu değer kamera yakalama ve çıkarım süresini içermez; uçtan uca gecikme daha yüksektir.

**Alıcı tampon boyutu.** Soket alıcı tamponu en az 4 MB olmalıdır. Varsayılan tampon (64–256 KB) 50 KB'lık paketler için yetersizdir; istemci bir an takılırsa paketler düşer.

---

## 11. Tespit Yayını (UDP 5008)

Tespit kutuları da bağımsız bir yayın kanalıdır. Video ile aynı `frame_id` kullanılır.

### 11.1 Genel Özellikler

| Özellik | Değer |
|---|---|
| Protokol | UDP, tek yönlü yayın |
| Port | 5008 |
| Hız | ~30 Hz (video ile senkron) |
| Format | UTF-8 kodlanmış JSON |
| Tipik boyut | 300–1500 bayt |

### 11.2 Paket Yapısı

```json
{
  "frame_id": 1935,
  "ts": 1786085603.841,
  "detections": [
    {"id": 7, "x": 640, "y": 312, "w": 80, "h": 54,
     "cls": 1, "team": 1, "conf": 0.93, "parent_id": null,
     "vx": 84.1, "vy": -12.0, "age": 0.03, "predicted": false,
     "dist": 8.7, "band": 1, "band_name": "ORTA", "dist_ok": false},
    {"id": 9, "x": 648, "y": 470, "w": 26, "h": 26,
     "cls": 4, "team": 1, "conf": 0.81, "parent_id": 7,
     "vx": 82.4, "vy": -10.6, "age": 0.03, "predicted": false,
     "dist": 8.9, "band": 1, "band_name": "ORTA", "dist_ok": true}
  ],
  "lock": { },
  "aim": { }
}
```

| Alan | Tip | Açıklama |
|---|---|---|
| `frame_id` | uint | Çıkarımın yapıldığı kare numarası |
| `ts` | double | Üretim zamanı (Unix epoch) |
| `detections` | array | Tespit listesi. Hedef yoksa boş dizi. |
| `lock` | object/null | Angajman özeti (§11.7). Aktif angajman yoksa `null`. |
| `aim` | object/null | Nişan çözümü (§11.8). Kilitli hedef yoksa `null`. |

Tespit nesnesi alanları:

| Alan | Tip | Açıklama |
|---|---|---|
| `id` | int | Takip kimliği (§11.6) |
| `x` | int | Kutunun **sol üst** köşesi, yatay (piksel) |
| `y` | int | Kutunun **sol üst** köşesi, dikey (piksel) |
| `w` | int | Kutu genişliği (piksel) |
| `h` | int | Kutu yüksekliği (piksel) |
| `cls` | int | Hedef sınıfı (§11.3) |
| `team` | int | Dost/düşman durumu (§11.4) |
| `conf` | float | Güven skoru, 0.0–1.0 |
| `parent_id` | int/null | Balonlar için bağlı olduğu maketin `id`'si (§11.9) |
| `vx` | float | Yatay hız (piksel/saniye) |
| `vy` | float | Dikey hız (piksel/saniye) |
| `age` | float | Son ölçümden bu yana geçen süre (saniye) |
| `predicted` | bool | `true` ise konum ölçüm değil, tahmindir |
| `dist` | float/null | Kestirilen mesafe (metre) |
| `band` | int | Menzil kuşağı kodu (§11.10) |
| `band_name` | string | Kuşak adı, gösterim için |
| `dist_ok` | bool | Mesafe kestiriminin güvenilir olup olmadığı |

**Hız ve tahmin.** Model çıkarımı yaklaşık 10–30 Hz çalışırken bu yayın 30 Hz'dir. Aradaki karelerde konum Kalman filtresiyle tahmin edilir; `predicted` alanı bunu bildirir. İstemci tahmin edilmiş kutuları görsel olarak ayırt edebilir (örneğin ince çerçeve).

`age` değeri büyüdükçe konum tahmini belirsizleşir. 2 saniyeyi aşan izler yayından düşer.

### 11.3 Sınıf Kodları

| Kod | Sınıf | Model etiketi |
|---|---|---|
| 0 | Drone / Mini-Micro İHA | `drone` |
| 1 | Savaş uçağı F16 | `f16` |
| 2 | Balistik füze | `fuze` |
| 3 | Helikopter | `heli` |
| 4 | Balon | `balon` |

Kodlar YOLO modelinin eğitim sırasıyla aynıdır. Farklı sırada eğitilmiş bir model kullanılırsa Python tarafında dönüşüm yapılır; protokol kodları değişmez.

### 11.4 Takım Kodları

| Kod | Durum | Arayüz gösterimi |
|---|---|---|
| 0 | Dost | Camgöbeği kutu |
| 1 | Düşman | Kırmızı kutu |
| 2 | Belirsiz | Sarı kutu |

`team = 2` (belirsiz) hedeflere angajman yapılmaz. Arayüz bu ayrımı görsel olarak belirtmelidir.

### 11.5 Koordinat Sistemi

Koordinatlar **kaynak (yakalama) çözünürlüktedir** ve kutunun **sol üst köşesini** gösterir. Merkez koordinatı değildir.

Yayın çözünürlüğü kaynak çözünürlükten farklı olabilir. Arayüz koordinatları ölçeklemelidir:

```
ekran_x = x * (video_genisligi / kaynak_genisligi)
ekran_y = y * (video_yuksekligi / kaynak_yuksekligi)
```

Video paketindeki `width` ve `height` alanları yayın çözünürlüğünü verir. Kaynak çözünürlük yapılandırmadan bilinir; ikisi eşitse ölçekleme gerekmez.

### 11.6 Takip Kimliği ve İstemci Kuralları

**`id` kalıcı değildir.** Takipçi (ByteTrack) kısa süreli kayıplarda ize yeni bir kimlik atar. Bu nedenle `id` bir hedefi uzun süre tanımlamak için kullanılamaz; kalıcı hedef kimliği `lock` alanında tutulur (§11.7).

`id` değeri `-1` ise tespit henüz onaylanmamıştır.

**Kare eşleştirme.** Kutular, aynı `frame_id`'ye sahip video karesi üzerine çizilmelidir. Video ve tespit paketleri farklı sırada gelebilir; istemci küçük bir tampon tutarak eşleştirme yapmalıdır.

Tam eşleşme her zaman bulunmayabilir: çıkarım hızı video hızından düşüktür ve kutular tahmin edilerek üretilir. Bu durumda en yakın önceki kare kullanılabilir.

**Kaybolan hedefler.** Bir `id` bir sonraki pakette görünmüyorsa hedef yayından düşmüş demektir. İstemci o kutuyu ekrandan kaldırmalıdır. Tespitler kaybolup geri gelebilir; bu normaldir.

**Bayat veri.** Belirli bir süre (örneğin 500 ms) tespit paketi gelmezse istemci tüm kutuları temizlemeli ve bağlantı uyarısı göstermelidir. Eski kutuları ekranda bırakmak yanıltıcıdır.

### 11.7 Angajman Bilgisi (`lock`)

Aktif angajman varsa `lock` alanı doludur; aksi halde `null`'dur.

```json
{
  "track_id": 14,
  "state": 1,
  "state_name": "LOCKED",
  "cls": 1,
  "team": 1,
  "x": 640.2,
  "y": 312.5,
  "w": 80,
  "h": 54,
  "vx": 84.1,
  "vy": -12.0,
  "lost_for": 0.0,
  "shots_fired": 0,
  "reacquires": 6,
  "duration": 12.4
}
```

| Alan | Tip | Açıklama |
|---|---|---|
| `track_id` | int | Kilitli izin güncel kimliği |
| `state` | int | Angajman durumu (aşağıdaki tablo) |
| `state_name` | string | Durum adı, gösterim için |
| `cls` | int | Hedef sınıfı |
| `team` | int | Dost/düşman durumu |
| `x`, `y` | float | Tahmini merkez konumu (piksel) |
| `w`, `h` | int | Kutu boyutu (piksel) |
| `vx`, `vy` | float | Hız (piksel/saniye) |
| `lost_for` | float | İz düştüğünden bu yana geçen süre (saniye) |
| `shots_fired` | int | Bu hedefe yapılan atış sayısı |
| `reacquires` | int | Kilidin kaç kez yeni bir ize devredildiği |
| `duration` | float | Angajman süresi (saniye) |

**Durum kodları:**

| Kod | Ad | Anlamı |
|---|---|---|
| 0 | `IDLE` | Hedef seçilmedi |
| 1 | `LOCKED` | Hedef kilitli ve görülüyor |
| 2 | `LOST` | İz düştü, konum tahmin ediliyor |
| 3 | `DESTROYED` | İmha teyidi alındı |
| 4 | `ABANDONED` | Tolerans doldu veya atış sınırı aşıldı |

**`track_id` ile kilidin ilişkisi.** Takipçi kısa süreli kayıplarda ize yeni kimlik atar. Angajman katmanı bunu telafi eder: kilitli iz düştüğünde konum Kalman ile tahmin edilmeye devam eder ve tahmin edilen konuma yakın, aynı sınıf ve takımdan yeni bir iz çıkarsa kilit ona devredilir.

Bu nedenle `lock.track_id` zaman içinde değişebilir; `reacquires` sayacı kaç kez devredildiğini gösterir. İstemci açısından hedef kesintisiz kilitli kalır.

**İstemci kuralı.** `state_name` değeri `LOCKED` ise hedef aktif olarak görülüyor demektir; `LOST` ise konum tahminidir ve arayüz bunu görsel olarak belirtmelidir. `lost_for` arttıkça güvenilirlik azalır.

### 11.8 Nişan Çözümü (`aim`)

Kilitli hedef varsa `aim` alanı doludur; aksi halde `null`'dur.

```json
{
  "aim_x": 648.4,
  "aim_y": 466.1,
  "error_x": 8.4,
  "error_y": 106.1,
  "distance": 106.4,
  "on_target": false
}
```

| Alan | Tip | Açıklama |
|---|---|---|
| `aim_x` | float | Nişan noktası, yatay (piksel) |
| `aim_y` | float | Nişan noktası, dikey (piksel) |
| `error_x` | float | Kare merkezine göre yatay hata (piksel) |
| `error_y` | float | Kare merkezine göre dikey hata (piksel) |
| `distance` | float | Hata büyüklüğü (piksel) |
| `on_target` | bool | Ölü bant içinde mi — ateş izni için ön koşul |

Nişan noktası üç bileşenden oluşur:

**İleri öngörü.** Sistem gecikmesi kadar (kamera, çıkarım, seri hat, servo mekaniği) hedefin ilerideki konumu tahmin edilir. Aksi halde taret sürekli geride kalır.

**Balon ofseti.** Balon maketin altında sabit bir geometrik oranda asılıdır; nişan noktası maket kutusunun yüksekliğiyle orantılı olarak aşağı kaydırılır. Oran mesafeden bağımsızdır.

**Balistik düzeltme.** Kamera ve namlu aynı eksende değildir (paralaks) ve mermi mesafeyle düşer. Düzeltme mesafeye göre hesaplanır. Bu sistemde ofset küçüktür (20–23 mm); toplam düzeltme her mesafede 5–8 piksel civarındadır.

**İstemci kuralı.** Arayüz nişangahı `aim_x`/`aim_y` konumunda çizmelidir. Kare merkezi kamera eksenidir ve nişan noktasından farklıdır; ikisi görsel olarak ayırt edilebilir olmalıdır.

### 11.9 Balon–Maket İlişkisi

Balonlar maketlerin altında asılıdır ve hepsi kırmızıdır; renk analiziyle takımları belirlenemez. Her balon, üstündeki maketten takımını devralır.

Eşleştirme kriterleri: balon maketin altında olmalı, yatayda hizalı olmalı ve dikey mesafe makul sınırlar içinde olmalıdır. En yakın uygun maket seçilir.

`parent_id` alanı balonun bağlı olduğu maketin `id`'sini taşır. Eşleşme bulunamayan balonlar `team = 2` (belirsiz) olarak işaretlenir ve angajmana girmez.

Maket tespitlerinde `parent_id` her zaman `null`'dur.

**İstemci kuralı.** Arayüz balon ile bağlı olduğu maket arasında görsel bir bağlantı (çizgi vb.) gösterebilir. Bu, operatörün hangi balonun hangi hedefe ait olduğunu doğrulamasını sağlar.

### 11.10 Menzil Kuşakları

Yarışma mesafeleri ayrık olduğu için (5 / 10 / 15 m) ham mesafe yerine kuşak sınıflandırması daha dayanıklıdır: kuşaklar arasında geniş boşluk vardır ve kestirim hatası kuşak kararını bozmaz.

| Kod | Ad | Aralık |
|---|---|---|
| 0 | `YAKIN` | < 7.5 m |
| 1 | `ORTA` | 7.5 – 12.5 m |
| 2 | `UZAK` | 12.5 – 18 m |
| 3 | `MENZIL_DISI` | > 18 m veya geçersiz |

**`dist_ok` alanı.** Mesafe, hedefin bilinen fiziksel boyutu ile görüntüdeki piksel boyutu karşılaştırılarak kestirilir. Uçak ve helikopter maketleri önden ve yandan bakıldığında farklı genişlikte görünür; bu iki kat hataya yol açabilir. Balonlar küre olduğu için her açıdan aynı çapta görünür ve güvenilir referanstır.

`dist_ok` yalnızca balon tespitlerinde `true` döner. Diğer sınıflarda mesafe bilgisi gösterilebilir ancak angajman kararında tek başına kullanılmamalıdır.

---

## 12. Kanal Özeti

| Kanal | Protokol | Port | Yön | Model |
|---|---|---|---|---|
| Komut/ayar | UDP | 5005 → 5006 | Çift yönlü | İstek-cevap |
| Video | UDP | 5007 | Sunucu → istemci | Yayın |
| Tespit | UDP | 5008 | Sunucu → istemci | Yayın |
| Tanı (MJPEG) | TCP/HTTP | 8080 | Sunucu → tarayıcı | Yayın |

MJPEG kanalı geliştirme ve saha tanısı içindir. Tarayıcıda `http://localhost:8080/` adresi açılarak kamera akışı doğrulanabilir; arayüz bu kanalı kullanmaz.

---

## 13. Kapsam Dışı

Aşağıdakiler bu protokolün kapsamında değildir:

- **EVT / EVTRSP mekanizması** — kullanılmayacaktır. Format hataları ERRRSP ile bildirilir.
- **1408 bayt bölme kuralı** — uygulanmayacaktır. Tüm cevaplar tek datagramda gönderilir.
- **Python ↔ ESP32 haberleşmesi** — ayrı bir ikili protokol kullanır (çerçeveli, CRC-8, little-endian).

---

## 14. Geliştirme Notları

### 14.1 Servislerin Ayrı Çalıştırılması

Tüm servisler `config/settings.py` içindeki `ENABLE_*` bayraklarıyla ayrı ayrı açılıp kapatılabilir. Arayüz geliştirmesi için yalnızca komut sunucusu yeterlidir; bu durumda kamera, model ve Arduino gerekmez.

`config/local_settings.py` dosyası (git'e dahil edilmez) bu ayarları geliştirici bazında geçersiz kılar:

```python
ENABLE_COMMAND_SERVER = True
ENABLE_CONTROL = False
ENABLE_VIDEO = False
ENABLE_DETECTIONS = False
ENABLE_MJPEG = False
ENABLE_TRACKING_LOOP = False
```

Bu yapılandırmada yalnızca `numpy` ve `opencv-python` paketleri gerekir; `ultralytics`, `torch` ve `pyserial` kurulmasına gerek yoktur.

### 14.2 Kamera ve Model Olmadan Test

Video ve tespit kanallarını kamera olmadan test etmek için:

```python
USE_CAMERA = False    # sentetik hareketli kare
USE_YOLO = False      # sentetik tespitler
```

Sentetik üretici dört hareketli hedef sağlar (dost, düşman ve belirsiz karışık, balon dahil). Kilit, hız vektörleri ve angajman durumu normal çalışır. Veri deterministiktir; arayüz geliştirmesi için gerçek kameradan daha uygundur.

### 14.3 Referans İstemci

`tools/test_receiver.py` her üç kanalı da dinleyen tam bir Python istemcisidir: video paketi ayrıştırma, kare–kutu eşleştirme, kilit ve nişan göstergesi çizimi. C# istemci geliştirilirken referans olarak kullanılabilir.

---

## 15. Sürüm Geçmişi

| Sürüm | Tarih | Değişiklik |
|---|---|---|
| 1.0 | — | İlk sürüm |
| 1.1 | — | Video (§10) ve tespit (§11) yayın kanalları eklendi |
| 1.2 | — | Renk analizi ve tespit parametreleri eklendi; Method büyük/küçük harf duyarsız |
| 1.3 | — | Tespit paketine hız/tahmin alanları, angajman bilgisi (§11.7) eklendi |
| 1.4 | — | Katalog sistem modu, bağlantı durumu ve manuel hareket bölümleriyle genişletildi (§9.1–9.4); tespit paketine mesafe alanları eklendi; nişan çözümü (§11.8), balon ilişkisi (§11.9) ve menzil kuşakları (§11.10) tanımlandı; yayın/kaynak çözünürlük ayrımı belgelendi; geliştirme notları eklendi (§14) |
| 1.5 | — | `LOOP_DEMO` davranışı tanımlandı (§9.2): hareket girdileri yok sayılır, `weapon.armed` açılamaz; hareket düzeni seçimi (`motion.demo.pattern`) ve elips zamanlama ayarı (`motion.demo.pan_lead`) eklendi |