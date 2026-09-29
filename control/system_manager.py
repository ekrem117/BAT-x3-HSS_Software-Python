"""Sistemin tek karar merkezi.

TUM guvenlik kurallari ve mod gecis kurallari bu dosyadadir. Ust
katmanlar (protocols/, param_bridge) donanima dogrudan erisemez;
yalnizca buradaki metotlari cagirir.

Bu modul core/state.py'yi TANIMAZ. Kendi ic durumunu tutar; katalog ile
senkronizasyon control/param_bridge.py sorumlulugundadir. Boylece burasi
UDP ve Arduino olmadan test edilebilir.

Iki hareket bicimi destekler:
    Bitmask     Yon bitleri (klavye). Hiz firmware sabitleriyle belirlidir.
    Mutlak aci  0xFB cercevesi (analog kol, otonom, sunum). Hedef aci
                Python'da tutulur; analog girdide girdi buyuklugune gore
                kaydirilir, sunum modunda hazir yorungeden gelir.

MANUAL ve AUTO'da hangisinin gecerli oldugu son cagrilan girdi metoduna
gore belirlenir. LOOP_DEMO'da taretin tek sahibi koreografidir
(control/loop_demo.py); diger hareket girdileri yok sayilir.

Bagimlilik yonu: control/ -> core/enums, hardware/
"""

import logging
import threading
import time

from config import settings
from core.enums import LinkState, SystemMode
from hardware import serial_protocol as proto
from hardware.arduino_link import ArduinoLink

log = logging.getLogger("system_manager")

# ---------------------------------------------------------------------------
# Mod / baglanti kod esleme
# ---------------------------------------------------------------------------
# core/state.py katalogunda "system.mode" ve "system.link" SAYISAL kod
# tasir (katalogun geri kalaniyla tutarli olsun diye). Kod <-> isim
# cevirisi yalnizca burada yapilir.

MODE_BY_CODE = {
    0: SystemMode.IDLE,
    1: SystemMode.MANUAL,
    2: SystemMode.AUTO,
    3: SystemMode.LOOP_DEMO,
    4: SystemMode.ESTOP,
}
CODE_BY_MODE = {mode: code for code, mode in MODE_BY_CODE.items()}

LINK_CODE = {
    LinkState.DISCONNECTED: 0,
    LinkState.CONNECTED: 1,
    LinkState.TIMEOUT: 2,
}

# ---------------------------------------------------------------------------
# Mod gecis kurallari
# ---------------------------------------------------------------------------
# Kural: calisma modlari arasinda DOGRUDAN gecis yoktur; her gecis
# IDLE'dan gecer. Boylece MANUAL'den AUTO'ya atlarken taret bir an
# sahipsiz kalmaz ve basili tuslar temizlenir.
#
# ESTOP her yerden girilebilir, yalnizca IDLE'a cikilir.

_ALLOWED_TRANSITIONS = {
    SystemMode.IDLE: {SystemMode.MANUAL, SystemMode.AUTO,
                      SystemMode.LOOP_DEMO, SystemMode.ESTOP},
    SystemMode.MANUAL: {SystemMode.IDLE, SystemMode.ESTOP},
    SystemMode.AUTO: {SystemMode.IDLE, SystemMode.ESTOP},
    SystemMode.LOOP_DEMO: {SystemMode.IDLE, SystemMode.ESTOP},
    SystemMode.ESTOP: {SystemMode.IDLE},
}

# Yon biti gonderilebilen modlar. IDLE ve ESTOP disaridadir.
_MOTION_MODES = (SystemMode.MANUAL, SystemMode.AUTO, SystemMode.LOOP_DEMO)

# Analog kol / otonom girdisinin kabul edildigi modlar. LOOP_DEMO
# disaridadir: orada taretin tek sahibi koreografidir; arayuzden gelen
# gecikmis bir kol paketi hedefi ele gecirip sunumu bozmamalidir.
_ANALOG_MODES = (SystemMode.MANUAL, SystemMode.AUTO)

# Ates edilebilen ve ARM acilabilen modlar. Hareket modlarindan ayri
# tutulmasinin sebebi LOOP_DEMO'dur: sunumda taret kimse nisan almadan
# tarama yapar ve izleyicilerin arasinda calisir, bu yuzden orada ARM
# acilamaz (docs/protocol_spec.md §9.5 ile uyumlu).
_ARMED_MODES = (SystemMode.MANUAL, SystemMode.AUTO)

# Ates biti kac update() dongusu boyunca set kalir.
# Firmware kenar algilama yapiyor (fireKeyState && !lastFireKeyState),
# bu yuzden bitin once 1, sonra 0 olmasi sart. 2 dongu (~40 ms) Arduino'nun
# bayti okumasi icin fazlasiyla yeterli.
_FIRE_PULSE_CYCLES = 2

# Kontrol dongusu takilirsa hedef acinin bir anda siframasini onleyen
# ust sinir. 100 ms, 50 Hz dongude bes tur gecikmeye karsilik gelir.
_MAX_DT_S = 0.1


def _apply_expo(value):
    """Analog girdiye tepki egrisi uygular.

    Isaret korunur, buyukluk usse yukseltilir. Sonuc: merkeze yakin
    bolgede hassas, uclarda hizli hareket.

    Args:
        value: -1.0 ... 1.0 arasi girdi

    Returns:
        float — egri uygulanmis deger
    """
    magnitude = abs(value) ** settings.ANALOG_EXPO
    return magnitude if value >= 0 else -magnitude


def _rate(value, max_rate, sign, use_expo=True):
    """Analog girdiyi acisal hiza cevirir.

    Args:
        value: -1.0 ... 1.0 arasi yumusatilmis girdi
        max_rate: Kol tam itildigindeki hiz (derece/saniye)
        sign: Eksen yonu duzeltmesi (-1.0 veya +1.0)
        use_expo: Tepki egrisi uygulansin mi

    Returns:
        float — derece/saniye
    """
    shaped = _apply_expo(value) if use_expo else value
    rate = shaped * max_rate * sign

    if abs(rate) < settings.ANALOG_MIN_RATE_DPS:
        return 0.0

    return rate


def _lead_error(rate, lead_s, min_lead_deg):
    """Komuta eklenecek ileri besleme (feed-forward) payini hesaplar.

    Pay yalnizca `rate * lead_s` olsaydi, kol hafif itildiginde pay da
    ORANTILI olarak kuculurdu ve servo hareket baslatacak torku
    uretemezdi. "Yavas = gucsuz" sorununun kaynagi buydu: tek bir
    carpan hem "ne kadar hizli gideyim" hem de "ne kadar tork payi
    alayim" sorusunu birden cevapliyordu. Taban deger bu ikisini
    ayirir: hiz ne kadar dusuk olursa olsun pay min_lead_deg'in altina
    inmez, yani en hafif dokunusta bile tork garanti edilir.

    Taban YALNIZCA hareket varken uygulanir. rate == 0 (kol ortada)
    iken pay sifirdir; boylece kol birakildiginda komut hedefin
    ilerisinde kalmaz ve geri sicrama olusmaz.

    Args:
        rate: Isaretli acisal hiz (derece/saniye)
        lead_s: Hizla orantili pay suresi (saniye)
        min_lead_deg: Hareket varken uygulanacak en kucuk pay (derece)

    Returns:
        float — komuta eklenecek isaretli pay (derece)
    """
    if rate == 0.0:
        return 0.0

    magnitude = max(abs(rate) * lead_s, min_lead_deg)
    return magnitude if rate > 0 else -magnitude


def _dither_offset(now, rate, amplitude, hz, max_rate):
    """Komuta bindirilecek kare dalga salinimini (dither) uretir.

    GEREKCE (tools/deadband_test.py ile OLCULDU): taret 1.0 birimden
    kucuk komut DEGISIMLERINE hic tepki vermiyor (0.1/0.2/0.3/0.5 ->
    hareket yok). Hassas modda tick basina yalnizca ~0.03 birim
    ilerliyorduk, yani esigin ~30 kati altinda: komut suruniyor, servo
    yok sayiyor, biriken fark esigi asinca tek seferde sicriyordu.

    Komutu esik buyuklugunde bir izgaraya oturtmak COZUM DEGILDIR:
    olcumde 1.0 ve 2.0 birimlik tek tek adimlar "sicrayarak" çikti,
    pürüzsüz olan tek adim 3.0 birimdi — hassas modda iki saniyede bir
    3 birimlik sicrama demek.

    Ise yarayan: SALINIM. Olcumde +/-1.0 birim @ 8 Hz salinirken hedef
    ~0.75 birim/s ilerletildi ve hareket PURUZSUZ oldu. Salinim servoyu
    her yarim periyotta esigin disina iterek statik surtunmeyi kirar;
    ORTALAMA konum hedefi birebir takip ettigi icin nisan dogrulugu
    bozulmaz.

    Salinim yalnizca YAVAS hareket ederken gereklidir. Hizli harekette
    tick basina ilerleme zaten esigin ustundedir; orada salinim yalnizca
    gereksiz titresim ve mekanik yipranma demektir. Kol ortadayken de
    (rate == 0) uygulanmaz: taret nisan alirken titrememelidir.

    Args:
        now: time.monotonic() degeri (faz kaynagi)
        rate: Eksenin isaretli acisal hizi (derece/saniye)
        amplitude: Salinim genligi (derece). 0 ise kapali.
        hz: Salinim frekansi (Hz). 0 ise kapali.
        max_rate: Bu hizin uzerinde salinim uygulanmaz (derece/saniye).
            0 veya negatifse hiz siniri yok sayilir.

    Returns:
        float — komuta eklenecek isaretli salinim payi (derece)
    """
    if amplitude <= 0.0 or hz <= 0.0:
        return 0.0

    # Hareket yokken titretme: operator nisan alirken taret sabit
    # durmalidir.
    if rate == 0.0:
        return 0.0

    if max_rate > 0.0 and abs(rate) > max_rate:
        return 0.0

    # Kare dalga: olcumde denenen dalga bicimi budur. Sinus, esigi
    # asan bolgede daha az zaman gecirir ve ayni genlikte daha zayif
    # "kirma" etkisi uretir.
    half_periods = int(now * 2.0 * hz)
    return amplitude if half_periods % 2 == 0 else -amplitude


def _min_change(value, last, step):
    """Komutu, ancak adim buyuklugu kadar degistiginde yayinlar.

    GEREKCE (tools/deadband_test.py ile OLCULDU): taret kucuk komut
    degisimlerine tepki vermiyor, ama SUREKLI tutulan yeterince buyuk
    adimlara puruzsuz tepki veriyor:

        YUKARI: 0.5/1.0/1.5 birim sicramali, 2.0 birim PURUZSUZ
        ASAGI : 0.5 birim sicramali, 1.0 birim PURUZSUZ

    Hassas modda tick basina yalnizca ~0.03 birim ilerliyoruz; komut
    suruniyor, servo yok sayiyor, biriken fark esigi asinca tek seferde
    sicriyordu. Bu filtre komutu bekletir ve ancak hedef bir tam adim
    uzaklastiginda yayinlar — boylece her yayin, olcumde puruzsuz cikan
    buyuklukte olur.

    Yayinlanan deger hedefin KENDISIDIR (izgaraya yuvarlanmis hali
    degil); boylece ortalama konum hatasi birikmez.

    Kol birakildiginda hedef ilerlemeyi durdurur, dolayisiyla yeni yayin
    tetiklenmez ve taret oldugu yerde kalir. Bunun bedeli, komut ile
    hedef arasinda en fazla bir adim kadar fark kalmasidir; eksen zaten
    bundan daha ince cozemedigi icin bu kacinilmazdir.

    Args:
        value: Ham komut degeri
        last: Son yayinlanan deger (ilk turda None)
        step: En kucuk yayin adimi (derece). 0 veya negatifse filtre kapali.

    Returns:
        float — yayinlanacak komut degeri
    """
    if step <= 0.0:
        return value

    if last is None or abs(value - last) >= step:
        return value

    return last


class _BacklashComp:
    """Tek eksen icin disli boslugu telafisi.

    Uc tasarim karari:

    1. Offset hedef aciya YAZILMAZ. Ayri tutulur ve yalnizca gonderilen
       komuta eklenir. Boylece _pan_target sistemin gercek konum modeli
       olarak kalir, limit kirpmasi dogru yerde calisir ve arayuze
       bildirilen aci offset kadar kaymaz.

    2. Yon degisimi ESIK ve SURE ile teyit edilir. Eski surumde her
       isaret degisiminde hedefe tam slack ekleniyordu; kol merkezindeki
       ADC gurultusu bunu saniyede defalarca tetikliyor ve eksen
       firliyordu. BACKLASH_ARM_INPUT esigi ile merkez gurultusu
       tamamen disarida kalir.

    3. Offset anlik basamak degil, RAMPA ile uygulanir. Anlik basamak
       firmware'in moveToImmediate() yolunda servoyu tam hizda sicratir;
       gercek bosluk tahminden kucukse bu sicrama dogrudan cikisa gecer.

    Isaret kuralı: pozitif yon, EKSEN ACISININ ARTTIGI yondur.
    """

    def __init__(self, positive_deg, negative_deg):
        """
        Args:
            positive_deg: Aci artarken kapatilacak slack (derece)
            negative_deg: Aci azalirken kapatilacak slack (derece)
        """
        self._positive = float(positive_deg)
        self._negative = float(negative_deg)
        self.reset()

    def reset(self):
        """Durumu sifirlar. Mod degisiminde cagrilir.

        Birikmis offset yeni moda tasinmamalidir: operator MANUAL'e
        dondugunde taret, offset kadar kaymis bir komutla baslamamali.
        """
        self._last_dir = 0
        self._candidate = 0
        self._candidate_ts = 0.0
        self._offset = 0.0
        self._target = 0.0

    def update(self, input_value, now, dt):
        """Offseti gunceller ve guncel degerini dondurur.

        Args:
            input_value: Eksen ACI yonunde isaretli girdi (-1.0 ... 1.0).
                Cagiran, ANALOG_*_SIGN duzeltmesini uygulamis olmalidir.
            now: time.monotonic() degeri
            dt: Onceki turdan bu yana gecen sure (saniye)

        Returns:
            float — gonderilecek komuta eklenecek offset (derece)
        """
        if not settings.BACKLASH_ENABLED:
            return 0.0

        # Yon yalnizca girdi esigi asarsa dikkate alinir. Esigin altinda
        # yon "kararsiz" (0) sayilir; boylece kol merkezdeyken isaret
        # gurultusu telafiyi tetikleyemez.
        if abs(input_value) >= settings.BACKLASH_ARM_INPUT:
            direction = 1 if input_value > 0 else -1
        else:
            direction = 0

        if direction != self._candidate:
            # Aday yon degisti: sayaci bastan baslat.
            self._candidate = direction
            self._candidate_ts = now
        elif (direction != 0
              and direction != self._last_dir
              and now - self._candidate_ts >= settings.BACKLASH_CONFIRM_S):
            # Yon teyit edildi: slack'i tek seferde kapat.
            self._last_dir = direction
            self._target = direction * (self._positive if direction > 0
                                        else self._negative)

        # Offset hedefe rampalanir.
        if settings.BACKLASH_SLEW_S <= 0.0:
            self._offset = self._target
            return self._offset

        # Rampa hizi, en buyuk tek yonlu slack'in SLEW_S icinde
        # kapanacagi sekilde secilir. Tam ters yon degisiminde
        # (pozitiften negatife) yol iki kat oldugundan sure de iki kat
        # olur; bu istenen davranistir, cunku o gecis daha buyuktur.
        span = max(self._positive, self._negative)
        if span <= 0.0:
            self._offset = 0.0
            return 0.0

        adim = (span / settings.BACKLASH_SLEW_S) * dt
        fark = self._target - self._offset

        if abs(fark) <= adim:
            self._offset = self._target
        else:
            self._offset += adim if fark > 0 else -adim

        return self._offset


class SystemManager:
    """Sistemin tek giris noktasi.

    Thread-guvenlidir: komut metotlari (protokol thread'inden) ve
    update() (kontrol dongusu thread'inden) ayni kilidi paylasir.
    """

    def __init__(self, link=None):
        # Enjekte edilebilir: testte sahte bir link verilebilir.
        self._link = link or ArduinoLink()
        self._lock = threading.Lock()

        self._mode = SystemMode.IDLE

        # Yon girdileri (bitmask modu). Klavye ve demo koreografisi
        # bunlari kullanir.
        self._up = False
        self._down = False
        self._left = False
        self._right = False

        # Analog kontrol durumu. Bitmask ile mutlak aci modu arasindaki
        # secim burada tutulur: hangi girdi metodu son cagrildiysa o
        # bicim gecerlidir.
        self._analog_active = False
        self._analog_pan = 0.0
        self._analog_tilt = 0.0
        self._analog_precision = False
        # Yumusatilmis girdi. Ham deger dogrudan kullanilirsa kolun ADC
        # gurultusu hiza yansir ve hareket titrek hissedilir.
        self._smooth_pan = 0.0
        self._smooth_tilt = 0.0

        # Son YAYINLANAN komut. _min_change filtresi buna gore karar
        # verir: hedef bir tam adim uzaklasmadan yeni komut gonderilmez.
        self._pan_cmd_last = None
        self._tilt_cmd_last = None

        # Bosluk telafisi. Offset hedef aciya yazilmaz; ayri tutulur ve
        # yalnizca gonderilen komuta eklenir.
        #
        # Tilt asimetriktir: yercekimi ekseni surekli tek yone bastirir,
        # o yonde slack zaten kapalidir. Pozitif yon = tilt acisinin
        # ARTTIGI yon. Mekanizmanda ters ise settings'teki UP/DOWN
        # degerlerini yer degistirin.
        self._pan_backlash = _BacklashComp(
            settings.BACKLASH_PAN_DEG, settings.BACKLASH_PAN_DEG)
        self._tilt_backlash = _BacklashComp(
            settings.BACKLASH_TILT_UP_DEG, settings.BACKLASH_TILT_DOWN_DEG)

        # Hedef aci. Python bu degeri sahiplenir ve kaydirir; Arduino'dan
        # konum geri bildirimi gelmedigi icin tek dogruluk kaynagi budur.
        # Firmware ayni sinirlarla kirptigi surece ikisi senkron kalir.
        self._pan_target = settings.HOME_PAN_DEG
        self._tilt_target = settings.HOME_TILT_DEG
        self._last_update_ts = None

        # Sunum modunda koreografi hedef aciyi dogrudan yukaridaki
        # degiskenlere yazar (bkz. set_demo_target). Ilk hedef gelene
        # kadar cerceve gonderilmez.
        self._demo_active = False

        # Silah durumu
        self._armed = False
        self._ammo = 30
        self._shots_fired = 0
        self._last_fire_ts = 0.0
        self._fire_cycles_left = 0

        # Tek seferlik komut (HOME, ESTOP, ates darbesi). Bir sonraki
        # update()'te gonderilir, ardindan normal akisa donulur. Boylece
        # heartbeat bu komutu surekli tekrarlamaz.
        self._oneshot = None

    # -----------------------------------------------------------------
    # Yasam dongusu
    # -----------------------------------------------------------------

    def start(self):
        """Seri baglantiyi baslatir."""
        self._link.start()
        log.info("SystemManager basladi, mod=%s", self._mode)

    def stop(self):
        """Guvenli kapanis: hareketi durdurup portu kapatir."""
        try:
            self._link.send(proto.encode_command(proto.CMD_STOP))
        finally:
            self._link.stop()
        log.info("SystemManager durdu")

    # -----------------------------------------------------------------
    # Mod yonetimi
    # -----------------------------------------------------------------

    def set_mode(self, mode):
        """Sistem modunu degistirir.

        Gecis izinliyse tum girdiler temizlenir ve ARM guvenlik geregi
        dusurulur (mod degisiminde silah asla yetkili kalmaz).

        Args:
            mode: SystemMode.* degerlerinden biri

        Returns:
            (bool, str) — basarili mi, degilse sebep
        """
        with self._lock:
            if mode not in _ALLOWED_TRANSITIONS:
                return False, f"bilinmeyen mod: {mode}"

            if mode == self._mode:
                return True, ""

            if mode not in _ALLOWED_TRANSITIONS[self._mode]:
                return False, f"{self._mode} -> {mode} gecisi yasak"

            previous = self._mode
            self._mode = mode
            self._clear_motion_locked()
            self._armed = False

            if mode == SystemMode.ESTOP:
                self._oneshot = proto.CMD_ESTOP
            elif previous == SystemMode.ESTOP:
                # ESTOP'tan cikis: once firmware'i serbest birak
                self._oneshot = proto.CMD_ESTOP_RELEASE

        log.info("Mod degisti: %s -> %s", previous, mode)
        return True, ""

    def set_mode_code(self, code):
        """Sayisal mod kodunu SystemMode'a cevirip set_mode cagirir.

        Args:
            code: 0-4 arasi mod kodu

        Returns:
            (bool, str) — basarili mi, degilse sebep
        """
        mode = MODE_BY_CODE.get(code)
        if mode is None:
            return False, f"gecersiz mod kodu: {code}"
        return self.set_mode(mode)

    def emergency_stop(self):
        """Acil durdur. Hangi modda olunursa olunsun calisir."""
        return self.set_mode(SystemMode.ESTOP)

    def home(self):
        """Tum eksenleri park konumuna gonderir.

        ESTOP etkinken reddedilir: acil durdurdan cikmadan hareket
        baslatilamaz.

        Returns:
            (bool, str) — basarili mi, degilse sebep
        """
        with self._lock:
            if self._mode == SystemMode.ESTOP:
                return False, "ESTOP etkin"

            self._clear_motion_locked()

            # Hedef aciyi da park konumuna al: aksi halde analog moda
            # gecildiginde taret eski hedefe geri sicrar.
            self._pan_target = settings.HOME_PAN_DEG
            self._tilt_target = settings.HOME_TILT_DEG

            self._oneshot = proto.CMD_HOME
        return True, ""

    def get_mode(self):
        """Guncel modu dondurur.

        get_status()'tan hafiftir: seri baglanti durumunu sorgulamaz.
        Kontrol dongusunun her turunda cagrilabilir.

        Returns:
            SystemMode.* degerlerinden biri
        """
        with self._lock:
            return self._mode

    def get_target_angles(self):
        """Python'un tuttugu hedef aciyi dondurur.

        Arduino'dan konum geri bildirimi gelmedigi icin taretin nerede
        oldugunu bildigimiz tek yer budur. Sunum koreografisi ilk
        hareketine buradan baslar.

        Returns:
            (pan, tilt) — derece
        """
        with self._lock:
            return self._pan_target, self._tilt_target

    # -----------------------------------------------------------------
    # Girdi metotlari
    # -----------------------------------------------------------------

    def set_manual_input(self, up=None, down=None, left=None, right=None):
        """Manuel yon tuslarinin basili/birakilmis durumunu gunceller.

        None verilen eksen degistirilmez; arayuz tek tus icin SET
        gonderdiginde digerleri korunur.

        Cagrildigi anda bitmask moduna donulur: klavye ve analog kol ayni
        anda kullanilmaz.

        MANUAL modu disinda girdi sessizce yok sayilir. Bunun sebebi
        kural eksikligi degil, arayuz mod degistirdikten sonra gecikmeli
        gelen tus paketlerinin hata uretmemesi gerektigidir.

        Args:
            up/down/left/right: bool veya None
        """
        with self._lock:
            if self._mode != SystemMode.MANUAL:
                return

            self._analog_active = False

            if up is not None:
                self._up = bool(up)
            if down is not None:
                self._down = bool(down)
            if left is not None:
                self._left = bool(left)
            if right is not None:
                self._right = bool(right)

    def set_demo_target(self, pan_deg, tilt_deg):
        """Sunum koreografisinin o anki hedef acisini yazar.

        Yalnizca LOOP_DEMO modunda kabul edilir; boylece mod degistikten
        sonra gelen gecikmis bir cagri tareti hareket ettiremez.

        Diger girdi metotlarindan farki HIZ degil KONUM tasimasidir.
        Yorunge (duz cizgi, sabit hiz, yumusak kalkis/durus)
        control/loop_demo.py'de hesaplanir; burasi yalnizca eksen
        sinirlarina kirpar ve bir sonraki update()'te gonderir.

        Analog yolun yumusatma, ileri besleme, bosluk telafisi ve en
        kucuk adim filtreleri BILINCLI olarak uygulanmaz. Hepsi kolun
        veya takip dongusunun gurultusune gore ayarlanmistir; onceden
        hesaplanmis puruzsuz bir yorungeyi yalnizca bozarlar (ornegin
        2 birimlik tilt adim filtresi capraz hareketi gozle gorulen
        basamaklara boler).

        Hedef, sistemin konum modeline dogrudan yazilir: firmware bu
        cerceveyi servoya aninda uygular (moveToImmediate), dolayisiyla
        komut edilen aci taretin konumunun en iyi tahminidir. Sunumdan
        cikilip analog kola gecildiginde hareket buradan devam eder.

        Args:
            pan_deg: Yatay hedef aci (derece)
            tilt_deg: Dikey hedef aci (derece)
        """
        with self._lock:
            if self._mode != SystemMode.LOOP_DEMO:
                return

            self._pan_target = max(
                settings.PAN_MIN_DEG,
                min(settings.PAN_MAX_DEG, float(pan_deg)),
            )
            self._tilt_target = max(
                settings.TILT_MIN_DEG,
                min(settings.TILT_MAX_DEG, float(tilt_deg)),
            )
            self._demo_active = True

    def set_analog_input(self, pan=0.0, tilt=0.0, precision=False):
        """Analog eksen girdilerini gunceller (-1.0 ... 1.0).

        Cagrildigi anda sistem mutlak aci moduna gecer; bitmask yon
        bitleri artik gonderilmez.

        Deger yalnizca YON ve BUYUKLUK tasir, konum degil. Hedef aci
        update() icinde bu degere ve gecen sureye gore kaydirilir.

        Yalnizca MANUAL ve AUTO modlarinda kabul edilir; LOOP_DEMO'da
        taretin tek sahibi koreografidir.

        Args:
            pan: Yatay girdi (- sol, + sag)
            tilt: Dikey girdi (- asagi, + yukari)
            precision: hassas mod. etkinken tum hizlar duser
        """
        with self._lock:
            if self._mode not in _ANALOG_MODES:
                return

            self._analog_active = True
            self._analog_pan = max(-1.0, min(1.0, float(pan)))
            self._analog_tilt = max(-1.0, min(1.0, float(tilt)))
            self._analog_precision = bool(precision)

    # -----------------------------------------------------------------
    # Silah
    # -----------------------------------------------------------------

    def fire(self):
        """Ates guvenlik zincirini isletir ve gecerse atis tetikler.

        Zincir sirasi bilincli: once ucuz kontroller, en sonda donanim.

        Returns:
            (bool, str) — atis tetiklendi mi, degilse sebep
        """
        now = time.monotonic()

        with self._lock:
            if self._mode not in _ARMED_MODES:
                return False, f"{self._mode} modunda ates edilemez"

            if not self._armed:
                return False, "silah yetkili degil (ARM kapali)"

            if self._ammo <= 0:
                return False, "mermi bitti"

            if now - self._last_fire_ts < settings.FIRE_COOLDOWN_S:
                return False, "atis bekleme suresi dolmadi"

            if self._link.get_link_state() != LinkState.CONNECTED:
                return False, "Arduino baglantisi yok"

            self._last_fire_ts = now
            self._ammo -= 1
            self._shots_fired += 1

            if self._analog_active:
                # Mutlak aci modunda bitmask ates biti kullanilamaz:
                # bitmask isleyicisi cagrildiginda pan/tilt yonunu de
                # degerlendirir ve mutlak aci hedefini bozar.
                self._oneshot = proto.CMD_FIRE_PULSE
            else:
                self._fire_cycles_left = _FIRE_PULSE_CYCLES

        log.info("Ates tetiklendi, kalan mermi=%d", self._ammo)
        return True, ""

    def set_armed(self, armed):
        """Ates yetkisini acar/kapatir.

        Yalnizca MANUAL ve AUTO modlarinda acilabilir; kapatma her zaman
        serbesttir (guvenli yon her zaman izinli olmalidir).

        Args:
            armed: bool

        Returns:
            (bool, str) — basarili mi, degilse sebep
        """
        with self._lock:
            if armed and self._mode not in _ARMED_MODES:
                return False, f"{self._mode} modunda ARM acilamaz"
            self._armed = bool(armed)
        return True, ""

    # -----------------------------------------------------------------
    # Kontrol dongusu
    # -----------------------------------------------------------------

    def update(self):
        """Guncel duruma karsilik gelen yuku Arduino'ya gonderir.

        param_bridge tarafindan CONTROL_LOOP_HZ hizinda cagrilir.
        Gonderilen yuk ayni zamanda ArduinoLink'in heartbeat yuku olur.
        """
        with self._lock:
            payload = self._build_payload_locked()

        self._link.send(payload)

    def _build_payload_locked(self):
        """Gonderilecek yuku uretir. Cagiran kilidi tutmalidir.

        Returns:
            bytes — serial_protocol ile kodlanmis komut veya cerceve
        """
        # Tek seferlik komut varsa oncelik onundur.
        if self._oneshot is not None:
            command = self._oneshot
            self._oneshot = None
            return proto.encode_command(command)

        # Hareket uretmeyen modlarda (IDLE, ESTOP) yalnizca durus biti.
        if self._mode not in _MOTION_MODES:
            return proto.encode_command(proto.CMD_STOP)

        if self._mode == SystemMode.LOOP_DEMO:
            return self._build_demo_payload_locked()

        if self._analog_active:
            return self._build_analog_payload_locked()

        fire_bit = self._fire_cycles_left > 0
        if fire_bit:
            self._fire_cycles_left -= 1

        # Zit yonler birbirini iptal eder. Firmware de ayni kontrolu
        # yapiyor; burada da yapiyoruz cunku kural Python tarafinda
        # gorunur olmali (tek dogruluk kaynagi ilkesi).
        up = self._up and not self._down
        down = self._down and not self._up
        left = self._left and not self._right
        right = self._right and not self._left

        return proto.encode_motion(
            up=up, down=down, left=left, right=right, fire=fire_bit,
        )

    def _build_demo_payload_locked(self):
        """Sunum modunda koreografinin son hedefini cerceveye kodlar.

        Cagiran kilidi tutmalidir.

        Returns:
            bytes — 0xFB cercevesi; hedef henuz gelmediyse durus komutu
        """
        if not self._demo_active:
            return proto.encode_command(proto.CMD_STOP)

        return proto.encode_absolute(self._pan_target, self._tilt_target)

    def _build_analog_payload_locked(self):
        """Analog girdiye gore hedef aciyi kaydirip cerceve uretir.

        Hedef, gecen sureyle orantili kaydirilir; boylece kontrol
        dongusunun hizi degisse bile hareket hizi ayni kalir.

        Cagiran kilidi tutmalidir.

        Returns:
            bytes — 0xFB cercevesi
        """
        now = time.monotonic()

        if self._last_update_ts is None:
            dt = 0.0
        else:
            dt = min(now - self._last_update_ts, _MAX_DT_S)

        self._last_update_ts = now

        is_auto = (self._mode == SystemMode.AUTO)
        is_precision = self._analog_precision and not is_auto

        alpha = (settings.AUTO_SMOOTHING if is_auto
                 else settings.ANALOG_SMOOTHING)

        self._smooth_pan += alpha * (self._analog_pan - self._smooth_pan)
        self._smooth_tilt += alpha * (self._analog_tilt - self._smooth_tilt)

        # Azami hizlar dogrudan derece/saniye olarak secilir. Tek bir
        # "factor" carpani, hassas modda gercek hizi gizliyordu; hangi
        # modda saniyede kac derece gittigimiz artik okunabilir.
        if is_auto:
            pan_max = settings.ANALOG_PAN_RATE_DPS * settings.AUTO_RATE_FACTOR
            tilt_max = settings.ANALOG_TILT_RATE_DPS * settings.AUTO_RATE_FACTOR
            use_expo = settings.AUTO_USE_EXPO
            lead = settings.AUTO_LEAD_TIME_S
        elif is_precision:
            pan_max = settings.ANALOG_PAN_PRECISION_DPS
            tilt_max = settings.ANALOG_TILT_PRECISION_DPS
            use_expo = settings.PRECISION_USE_EXPO
            lead = settings.ANALOG_LEAD_PRECISION_S
        else:
            pan_max = settings.ANALOG_PAN_RATE_DPS
            tilt_max = settings.ANALOG_TILT_RATE_DPS
            use_expo = True
            lead = settings.ANALOG_LEAD_TIME_S

        pan_rate = _rate(self._smooth_pan, pan_max,
                         settings.ANALOG_PAN_SIGN, use_expo)
        tilt_rate = _rate(self._smooth_tilt, tilt_max,
                          settings.ANALOG_TILT_SIGN, use_expo)

        # --- Hedef aci (sistemin konum modeli) ---
        # Bosluk offseti buraya KARISMAZ. Burasi taretin nerede oldugunu
        # bildigimiz tek yerdir; telafi degeri karisirsa arayuze
        # bildirilen aci ve limit kirpmasi kayar.
        self._pan_target = max(
            settings.PAN_MIN_DEG,
            min(settings.PAN_MAX_DEG, self._pan_target + pan_rate * dt),
        )
        self._tilt_target = max(
            settings.TILT_MIN_DEG,
            min(settings.TILT_MAX_DEG, self._tilt_target + tilt_rate * dt),
        )

        # --- Bosluk telafisi ---
        # Girdi, ANALOG_*_SIGN ile ACI yonune cevrilerek verilir; boylece
        # _BacklashComp'un "pozitif = aci artiyor" kurali korunur.
        #
        # OTONOMDA UYGULANMAZ: takipte hedef etrafinda surekli kucuk yon
        # degisimi olur; her birinde eklenen sicrama salinimi besler.
        # Operatorun duzeltebildigi bir davranis otonomda kendini
        # besleyen donguye donusur.
        if is_auto:
            pan_offset = 0.0
            tilt_offset = 0.0
        else:
            pan_offset = self._pan_backlash.update(
                self._smooth_pan * settings.ANALOG_PAN_SIGN, now, dt)
            tilt_offset = self._tilt_backlash.update(
                self._smooth_tilt * settings.ANALOG_TILT_SIGN, now, dt)

        # --- Ileri besleme payi (taban degerli) ---
        # Taban, "yavas = gucsuz" sorununu cozer: pay artik hizla
        # orantili kuculup sifira inmiyor, hareket varken en az
        # ANALOG_MIN_LEAD_*_DEG kadar kaliyor. Ayrintili gerekce
        # _lead_error() docstring'inde.
        #
        # OTONOMDA UYGULANMAZ: takipte hedef etrafinda surekli kucuk yon
        # degisimi olur; her birine sabit bir taban eklemek salinimi
        # besler. Bosluk telafisinin otonomda kapatilmasiyla ayni
        # gerekce.
        if is_auto:
            pan_min_lead = 0.0
            tilt_min_lead = 0.0
        else:
            pan_min_lead = settings.ANALOG_MIN_LEAD_PAN_DEG
            tilt_min_lead = settings.ANALOG_MIN_LEAD_TILT_DEG

        pan_lead = _lead_error(pan_rate, lead, pan_min_lead)
        tilt_lead = _lead_error(tilt_rate, lead, tilt_min_lead)

        # --- Gonderilecek komut ---
        # Ileri besleme payi ve bosluk offseti yalnizca burada eklenir.
        pan_cmd = max(
            settings.PAN_MIN_DEG,
            min(settings.PAN_MAX_DEG,
                self._pan_target + pan_lead + pan_offset),
        )
        # Yercekimi telafisi: YALNIZCA yercekimine KARSI (TILT_GRAVITY_SIGN
        # ile ayni yonde) hareket edilirken uygulanir. DOWN yonunde
        # (yercekimi zaten yardimci, disliler DOWN'a dogru kendiliginden
        # zorlanir) sabit bir pay eklemek operatorun komutuyla ters
        # yonde tork uretip DOWN hareketini bozuyordu (gozlemlendi:
        # "DOWN'da biraz tutarsiz"). Idle'da da uygulanmaz: disliler
        # kendinden kilitli (self-locking), gucsuzken bile dusmuyor,
        # yani tutma torku icin paya gerek yok — yalnizca AKTIF olarak
        # yerçekimine karsi hareket ederken (kirilma/breakaway toku
        # gerektiren an) devreye girer.
        gravity_sign = settings.TILT_GRAVITY_SIGN
        moving_against_gravity = (tilt_rate * gravity_sign) > 0
        gravity_bias = (settings.TILT_GRAVITY_BIAS_DEG * gravity_sign
                         if moving_against_gravity else 0.0)

        # --- Dither (salinim) ---
        # Taretin tepki verdigi en kucuk komut DEGISIMI olculmustur
        # (bkz. _dither_offset ve tools/deadband_test.py). Yavas
        # harekette tick basina ilerleme bu esigin cok altinda kalir;
        # salinim, servoyu her yarim periyotta esigin disina iterek
        # hareketin baslamasini saglar. Ortalama konum degismedigi icin
        # hedef modeli ve arayuze bildirilen aci etkilenmez.
        #
        # OTONOMDA UYGULANMAZ: kamera taretin ustundedir; 8 Hz'lik bir
        # salinim goruntude titreme yaratir, bu da tespit ve takip
        # dogrulugunu dogrudan bozar. Otonom takipte hiz zaten
        # genellikle esigin ustundedir.
        if is_auto:
            pan_dither = 0.0
            tilt_dither = 0.0
        else:
            pan_dither = _dither_offset(
                now, pan_rate, settings.ANALOG_DITHER_PAN_DEG,
                settings.ANALOG_DITHER_HZ,
                settings.ANALOG_DITHER_MAX_RATE_DPS)
            # Tilt genligi YONE GORE secilir. Eksen yercekimi yuku
            # tasidigi icin yukari (aci artan yon) hareket, asagiya gore
            # belirgin daha buyuk bir kirilma toku ister: simetrik
            # salinimda eksen "-" yarim periyotta yercekimiyle kolayca
            # iniyor ama "+" yarim periyotta yukari cikamiyor, yukselen
            # ortalamanin gerisinde kalip birikiyor ve sicriyordu.
            #
            # Olcum de bunu destekliyor: tools/deadband_test.py adimlari
            # hep YUKARI atar, yani olculen esik yukari yonun esigidir ve
            # orada 1.0 birim "sicrayarak", 3.0 birim "puruzsuz" cikti.
            tilt_amplitude = (settings.ANALOG_DITHER_TILT_UP_DEG
                              if tilt_rate > 0
                              else settings.ANALOG_DITHER_TILT_DOWN_DEG)

            tilt_dither = _dither_offset(
                now, tilt_rate, tilt_amplitude,
                settings.ANALOG_DITHER_HZ,
                settings.ANALOG_DITHER_MAX_RATE_DPS)

        pan_cmd = max(
            settings.PAN_MIN_DEG,
            min(settings.PAN_MAX_DEG, pan_cmd + pan_dither),
        )

        tilt_cmd = max(
            settings.TILT_MIN_DEG,
            min(settings.TILT_MAX_DEG,
                self._tilt_target + tilt_lead + tilt_offset
                + gravity_bias + tilt_dither),
        )

        # --- En kucuk yayin adimi ---
        # Olcum, taretin ancak yeterince buyuk ve SUREKLI tutulan
        # adimlara puruzsuz tepki verdigini gosterdi (bkz. _min_change).
        # Adim buyuklugu tilt'te YONE GORE degisir: yukari hareket
        # yercekimi yuku yuzunden daha buyuk adim ister (olculen:
        # yukari 2.0, asagi 1.0 birim).
        #
        # OTONOMDA DA GECERLIDIR: fiziksel esik moddan bagimsizdir. Bu
        # filtre sisteme enerji EKLEMEZ, yalnizca esik alti komutlari
        # bekletir; bu yuzden salinim beslemez.
        tilt_step = (settings.ANALOG_STEP_TILT_UP_DEG if tilt_rate > 0
                     else settings.ANALOG_STEP_TILT_DOWN_DEG)

        self._pan_cmd_last = _min_change(
            pan_cmd, self._pan_cmd_last, settings.ANALOG_STEP_PAN_DEG)
        self._tilt_cmd_last = _min_change(
            tilt_cmd, self._tilt_cmd_last, tilt_step)

        return proto.encode_absolute(self._pan_cmd_last, self._tilt_cmd_last)

    def _clear_motion_locked(self):
        """Tum yon girdilerini sifirlar. Cagiran kilidi tutmalidir.

        Hedef aci KORUNUR: mod degisiminde taret oldugu yerde kalmali,
        eski bir hedefe sicramamalidir.
        """
        self._up = False
        self._down = False
        self._left = False
        self._right = False
        self._fire_cycles_left = 0

        self._analog_active = False
        self._analog_pan = 0.0
        self._analog_tilt = 0.0
        self._analog_precision = False
        self._last_update_ts = None

        # Sunum hedefi de dusurulur: yeni modda eski koreografi hedefi
        # gonderilmemeli. Hedef acinin kendisi yukaridaki kurala gore
        # korunur.
        self._demo_active = False

        self._smooth_pan = 0.0
        self._smooth_tilt = 0.0

        # Bosluk telafisi de sifirlanir: birikmis offset yeni moda
        # tasinirsa taret, mod degisir degismez offset kadar kaymis bir
        # komut alir.
        self._pan_backlash.reset()
        self._tilt_backlash.reset()

        # Yayin filtresi de sifirlanir: eski deger yeni moda tasinirsa
        # ilk komut hedefe gore bir adim kaymis gelebilir.
        self._pan_cmd_last = None
        self._tilt_cmd_last = None

    # -----------------------------------------------------------------
    # Durum sorgulama (param_bridge yukari tasir)
    # -----------------------------------------------------------------

    def get_status(self):
        """Arayuze bildirilecek salt-okunur durumu dondurur.

        Bildirilen aci, bosluk offseti EKLENMEMIS hedef acidir: arayuz
        taretin nerede olmasi gerektigini gormeli, telafi payini degil.

        Returns:
            dict — katalog anahtarlarina karsilik gelen degerler
        """
        with self._lock:
            mode_code = CODE_BY_MODE[self._mode]
            armed = int(self._armed)
            ammo = self._ammo
            shots = self._shots_fired
            pan_angle = self._pan_target
            tilt_angle = self._tilt_target

        return {
            "system.mode": mode_code,
            "system.link": LINK_CODE[self._link.get_link_state()],
            "system.pan_angle": round(pan_angle, 2),
            "system.tilt_angle": round(tilt_angle, 2),
            "weapon.armed": armed,
            "weapon.ammo": ammo,
            "weapon.shots_fired": shots,
        }