"""Sunum modu koreografisi.

Taretin yeteneklerini gosteren, kendini tekrar eden iki hareket duzeni
uretir; hangisinin calisacagi "motion.demo.pattern" ile secilir:

    PATTERN_SWEEP    Yatay tarama ve iki capraz eksende gidip gelme.
                     Her hareket duz cizgidir ve durarak biter.
    PATTERN_ELLIPSE  Ayni kutuya icten teget elips; hic durmadan doner.

Hareket MUTLAK ACI yolundan yapilir. Bitmask yolu bu is icin uygun
degildir: firmware yon bitini "eksen limitine git" olarak yorumlar ve
her ekseni kendi azami hiziyla (pan 800, tilt 600 derece/s) surer. Hiz
ayarlanamaz, capraz harekette eksenler ayni anda varmaz ve yol duz bir
cizgi olmaz.

Burada yorunge Python'da hesaplanir ve her turda o anki konum
gonderilir:

    Senkron     Iki eksen tek bir parametreden turetilir. Capraz hareket
                gercek bir kosegendir; elipste pan tam ortadan gecerken
                tilt tam tepede veya tam diptedir. Pan'in fiziksel
                gecikmesi elipste ayrica telafi edilir (bkz. _EllipseLap).
    Hiz         Taramada hiz yol boyunca sabittir. Elipste her eksen saf
                sinusle surulur; hiz tepede/dipte artar, uclarda azalir.
    Yumusak     Her hareket kosinus rampasiyla hizlanir; tarama
                duzeninde her kosede yavaslayip durur.

Firmware bu cerceveyi moveToImmediate() ile uygular: kendi yorunge
ureticisini ATLAR ve aciyi dogrudan servoya yazar. Yani servonun
izledigi hareket, burada uretilen yorungenin kendisidir; komuttaki her
sicrama servoda da tam hizda bir sicrama olur. Bu yuzden yorunge surekli
olmali ve kontrol dongusu takilsa bile ileri atlamamalidir (bkz.
_MAX_DT_S).

Bu modul KARAR VERMEZ, yalnizca ISTEK uretir. Uretilen her hedef
SystemManager'da eksen sinirlarina kirpilir; mod degisirse (ESTOP dahil)
dizi durur ve bir sonraki giriste bastan baslar.

Zaman tabanlidir ve BLOKLAMAZ: sleep() kullanmaz, her tick() cagrisinda
"su an yolun neresindeyim" sorusunu cevaplar. Bu sayede ayni kontrol
dongusu icinde seri port ve ag trafigi kesintiye ugramaz.

Bagimlilik yonu: control/ -> core/enums
"""

import logging
import math
import time

from config import settings
from core.enums import SystemMode

log = logging.getLogger("loop_demo")

# Hareket duzenleri. Degerler "motion.demo.pattern" katalog kodlariyla
# aynidir (docs/protocol_spec.md §9.2).
PATTERN_SWEEP = 0
PATTERN_ELLIPSE = 1

# Kontrol dongusu takilirsa yorungenin ileri atlamasini onleyen ust
# sinir (s). Takilma aninda duvar saati kadar degil en fazla bu kadar
# ilerlenir; hareket kisa bir an yavaslar ama sicramaz. 25 birim/s
# hizda tek turda en fazla ~1.25 birimlik adim demektir.
_MAX_DT_S = 0.05

# Pan onde surme degerinin canli degisim hizi (s / s). Deger aninda
# uygulansaydi pan komutu sicrardi ve moveToImmediate() servoyu tam hizda
# oynatirdi. 0.25 ile 0.02 s'lik bir klavye adimi ~0.1 s'de uygulanir;
# pan komutuna eklenen hiz 60 birim/s elipste ~20 birim/s'yi gecmez.
_PAN_LEAD_SLEW = 0.25

# ---------------------------------------------------------------------------
# Tarama duzeni
# ---------------------------------------------------------------------------
# Konum adlari settings'teki sabitlere karsilik gelir. Degerler her
# hareketin basinda okunur; config/local_settings.py ile yapilan ayar da
# boylece gecerli olur.
#
# Yon esleme firmware ile aynidir: SOL = pan acisi BUYUK (A tusu
# PAN_MAX_DEG'e gider), YUKARI = tilt acisi BUYUK (W tusu TILT_MAX_DEG'e
# gider).

_RIGHT = "DEMO_PAN_RIGHT_DEG"
_LEFT = "DEMO_PAN_LEFT_DEG"
_LOW = "DEMO_TILT_LOW_DEG"
_HIGH = "DEMO_TILT_HIGH_DEG"

# Her adim: (aciklama, pan konumu, tilt konumu). Konum adimin VARIS
# noktasidir; her adim bir oncekinin bittigi yerden baslar. Ilk turun
# ilk adimi taretin o an bulundugu yerden baslar.
#
# Yatay hareketler alt seviyededir; capraz hareketler alt kose ile ust
# kose arasinda gidip gelir:
#
#     sol-ust                 sag-ust
#         \                  /
#            \            /
#               \      /
#                  \/
#                  /\
#               /      \
#            /            \
#         /                  \
#     sol-alt ---------------- sag-alt
#
#     Alt kenar      : 1 saga, 2 sola, 5 saga, 8 sola
#     "/" kosegeni   : 3 yukari, 4 asagi   (sol-alt <-> sag-ust)
#     "\" kosegeni   : 6 yukari, 7 asagi   (sag-alt <-> sol-ust)
#
# Pan her adimda bir uctan otekine gider; tilt yalnizca capraz
# adimlarda degisir.

_STEPS = (
    ("En saga",             _RIGHT, _LOW),    # 1
    ("En sola",             _LEFT,  _LOW),    # 2
    ("Capraz: sag-yukari",  _RIGHT, _HIGH),   # 3
    ("Capraz: sol-asagi",   _LEFT,  _LOW),    # 4
    ("Saga duz",            _RIGHT, _LOW),    # 5
    ("Capraz: sol-yukari",  _LEFT,  _HIGH),   # 6
    ("Capraz: sag-asagi",   _RIGHT, _LOW),    # 7
    ("En sola",             _LEFT,  _LOW),    # 8
)

# ---------------------------------------------------------------------------
# Elips duzeni
# ---------------------------------------------------------------------------
# Elips, tarama duzeniyle ayni DEMO_* kutusuna icten teget cizilir:
# merkez kutunun ortasi, yari eksenler kutunun yarisi. Varsayilan kutuda
# pan ortasi HOME_PAN_DEG ile ayni noktadir.
#
#                  tepe (pan ortada)
#               .-''''''''''''''-.
#            .'                    '.
#   sol-orta :                      : sag-orta  <- baslangic
#            '.                    .'
#               '-..............-'
#                  dip (pan ortada)
#
# Yon: sag-orta -> tepe -> sol-orta -> dip -> sag-orta. Pan sagdan sola
# giderken tilt ortadan tepeye cikip ortaya iner; soldan saga donerken
# ortadan dibe inip ortaya cikar.

# Cevre hesabindaki ornek sayisi. Cevre yalnizca ortalama hizi tur
# suresine cevirmek icin kullanilir; bu siklikta hata ihmal edilebilir.
_ELLIPSE_SAMPLES = 720


def _point(step):
    """Adimin varis noktasini settings'ten okur.

    Args:
        step: _STEPS elemani

    Returns:
        (pan, tilt) — derece
    """
    _, pan_key, tilt_key = step
    return float(getattr(settings, pan_key)), float(getattr(settings, tilt_key))


def _ellipse_geometry():
    """Elipsin merkezini ve isaretli yari eksenlerini settings'ten okur.

    Nokta(theta) = merkez + (yari_pan * cos(theta), yari_tilt * sin(theta))

    Yari eksenler isaretlidir: theta=0 sag-orta, theta=pi/2 tepe olur.

    Returns:
        ((merkez_pan, merkez_tilt), (yari_pan, yari_tilt)) — derece
    """
    right = float(settings.DEMO_PAN_RIGHT_DEG)
    left = float(settings.DEMO_PAN_LEFT_DEG)
    low = float(settings.DEMO_TILT_LOW_DEG)
    high = float(settings.DEMO_TILT_HIGH_DEG)

    center = ((left + right) / 2.0, (low + high) / 2.0)
    return center, (right - center[0], high - center[1])


def _ellipse_lap_seconds(radius):
    """Bir elips turunun suresini ortalama yol hizindan hesaplar.

    Args:
        radius: (yari_pan, yari_tilt) — isaretli, derece

    Returns:
        float — tur suresi (s); dejenere elipste 0
    """
    perimeter = 0.0
    prev = (radius[0], 0.0)
    for i in range(1, _ELLIPSE_SAMPLES + 1):
        theta = 2.0 * math.pi * i / _ELLIPSE_SAMPLES
        cur = (radius[0] * math.cos(theta), radius[1] * math.sin(theta))
        perimeter += math.hypot(cur[0] - prev[0], cur[1] - prev[1])
        prev = cur

    return perimeter / max(float(settings.DEMO_ELLIPSE_SPEED_DPS), 1e-3)


def _ellipse_start(pan_lead_s):
    """Elipsin ilk turunun basladigi noktayi dondurur.

    Tilt her zaman ortadadir. Pan onde suruluyorsa ucta degil, onde
    surme fazi kadar ileride baslar; boylece giris hareketi ilk turun
    ilk noktasinda biter ve tura geciste sicrama olmaz.

    Args:
        pan_lead_s: Pan'in tilt'ten onde surulme suresi (s)

    Returns:
        (pan, tilt) — derece
    """
    center, radius = _ellipse_geometry()
    lap_s = _ellipse_lap_seconds(radius)
    phase = 2.0 * math.pi * pan_lead_s / lap_s if lap_s > 1e-9 else 0.0
    return center[0] + radius[0] * math.cos(phase), center[1]


def _ramp_distance(t, speed, ramp_s):
    """Kosinus rampasinin ilk t saniyesinde alinan yol.

    Hiz 0'dan `speed`e v(t) = speed * (1 - cos(pi * t / ramp_s)) / 2
    egrisiyle cikar. Dogrusal rampadan farki ivmenin de sifirdan
    baslamasidir: servo harekete sarsintisiz girer ve sarsintisiz durur.
    Rampa sonunda alinan yol speed * ramp_s / 2'dir.

    Args:
        t: Rampa basindan beri gecen sure (0 ... ramp_s)
        speed: Rampa sonundaki hiz (yol icin birim/s, elips fazi icin
            rad/s)
        ramp_s: Rampa suresi (s), sifirdan buyuk

    Returns:
        float — alinan yol (birim veya rad)
    """
    return 0.5 * speed * (t - ramp_s / math.pi * math.sin(math.pi * t / ramp_s))


class _Move:
    """Iki nokta arasinda tek bir duz cizgi hareketi.

    Hiz profili: kosinus rampasiyla kalkis, sabit hiz, kosinus rampasiyla
    durus. Ardindan varis noktasinda DEMO_DWELL_S kadar beklenir.
    """

    def __init__(self, label, start, end, t0):
        """
        Args:
            label: Log icin aciklama
            start: (pan, tilt) baslangic noktasi
            end: (pan, tilt) varis noktasi
            t0: Hareketin baslayacagi an (koreografi saati, s)
        """
        self.label = label
        self.end = end
        self._start = start
        self._t0 = t0

        self._length = math.hypot(end[0] - start[0], end[1] - start[1])
        self._speed = max(float(settings.DEMO_SPEED_DPS), 1e-3)
        self._ramp = max(float(settings.DEMO_RAMP_S), 0.0)

        if self._length < 1e-6:
            self._duration = 0.0
        else:
            # Yol iki rampaya yetmiyorsa tepe hiz dusurulur: hareket yine
            # yumusak baslar ve biter, yalnizca sabit hizli bolumu olmaz.
            if self._length < self._speed * self._ramp:
                self._speed = self._length / self._ramp
            self._duration = self._length / self._speed + self._ramp

        dwell = max(float(settings.DEMO_DWELL_S), 0.0)
        self.end_time = t0 + self._duration + dwell

    def position(self, clock):
        """Verilen andaki hedef noktayi dondurur.

        Iki eksen AYNI oranla ilerletilir; yol bu yuzden duz cizgidir.

        Args:
            clock: Koreografi saati (s)

        Returns:
            (pan, tilt) — derece
        """
        if self._duration <= 0.0:
            return self.end

        ratio = self._distance(clock - self._t0) / self._length
        return (self._start[0] + ratio * (self.end[0] - self._start[0]),
                self._start[1] + ratio * (self.end[1] - self._start[1]))

    def _distance(self, t):
        """Hareket basindan t saniye sonra alinan yol (0 ... uzunluk)."""
        if t <= 0.0:
            return 0.0
        if t >= self._duration:
            return self._length

        speed, ramp = self._speed, self._ramp

        if ramp <= 0.0:
            return speed * t
        if t < ramp:
            return _ramp_distance(t, speed, ramp)

        remaining = self._duration - t
        if remaining < ramp:
            return self._length - _ramp_distance(remaining, speed, ramp)

        return speed * ramp / 2.0 + speed * (t - ramp)


class _EllipseLap:
    """Elips uzerinde tek bir tam tur.

    Her eksen SAF SINUS ile surulur: pan = a*cos(wt), tilt = b*sin(wt),
    ayni faz hiziyla. Bu, bir eksenin yapabilecegi en yumusak periyodik
    harekettir; ivme tura esit dagilir.

    Onceki surumde elips yol boyunca SABIT hizla suruluyordu ve sahada
    puruzsuz gorunmedi (2026-09-15). Sabit hizda her eksen yon
    degistirdigi noktada zorlanir:

        Pan   Sag/sol uclarda cok sert doner (45 birim/s'de ~260
              birim/s^2). Pan'in disli boslugunu yercekimi kapatmaz;
              sert donus boslugu vurdurur.
        Tilt  Tepede ve dipte uzun sure cok yavas ilerler (45'te her
              donuste ~0.5 s). Bu bolgede komut degisimleri tilt'in
              olculen tepki esiginin altinda kalir; eksen takilip
              sicrar (bkz. settings.ANALOG_STEP_TILT_*_DEG).

    Ayni tur suresinde sinus, pan uclarindaki ivmeyi yarinin altina
    indirir ve tilt'in yavas bolgesini kisaltir. Bedeli yol hizinin sabit
    olmamasidir: tepede ve dipte ortalamanin ~1.3 kati, uclarda ~0.7
    katidir.

    PAN ONDE SURME: sahada pan ekseni komutun gerisinde kaliyordu (agir
    taret, yon degisiminde disli boslugu ve surtunme); tilt tepeye
    vardiginda pan henuz ortaya gelmemis oluyordu (2026-09-15). Komutta
    iki eksen tam senkrondu, yani kayma fizikseldi. Pan fazi bu yuzden
    tilt fazinin w * pan_lead_s ilerisinde surulur; pan tam bu kadar
    geciktiginde fiziksel yol hedeflenen elipstir. Tilt'e dokunulmaz.

    Turlar arasi gecis kesintisizdir: bir tur tam faz hiziyla biter,
    sonraki ayni noktadan ayni hizla baslar. Yalnizca ILK tur kosinus
    rampasiyla kalkar; o ana kadar taret baslangic noktasinda
    bekliyordur.
    """

    def __init__(self, t0, soft_start):
        """
        Args:
            t0: Turun baslayacagi an (koreografi saati, s)
            soft_start: True ise tur durustan rampayla baslar
        """
        self.label = "Elips"
        self._t0 = t0
        self._center, self._radius = _ellipse_geometry()

        # Tur suresi ortalama yol hizindan turetilir: cevre / hiz.
        lap_s = _ellipse_lap_seconds(self._radius)
        self._omega = 2.0 * math.pi / lap_s if lap_s > 1e-9 else 0.0

        # Rampa ilk turun icine sigmalidir; sigmazsa ikinci tur tam hizla
        # baslar ve hiz sicrar. Yalnizca asiri ayarlarda devreye girer.
        ramp = max(float(settings.DEMO_RAMP_S), 0.0) if soft_start else 0.0
        self._ramp = min(ramp, lap_s)

        # Rampa bolumu, ayni surede tam hizla alinacak fazin yarisini
        # alir; tur bu yuzden ramp/2 kadar uzar.
        self.end_time = t0 + lap_s + self._ramp / 2.0

    def position(self, clock, pan_lead_s=0.0):
        """Verilen andaki hedef noktayi dondurur.

        Args:
            clock: Koreografi saati (s)
            pan_lead_s: Pan'in tilt'ten onde surulme suresi (s)

        Returns:
            (pan, tilt) — derece
        """
        t = clock - self._t0

        if t <= 0.0:
            phase = 0.0
        elif t < self._ramp:
            phase = _ramp_distance(t, self._omega, self._ramp)
        else:
            phase = self._omega * (t - self._ramp / 2.0)

        phase = min(phase, 2.0 * math.pi)
        pan_phase = phase + self._omega * pan_lead_s

        return (self._center[0] + self._radius[0] * math.cos(pan_phase),
                self._center[1] + self._radius[1] * math.sin(phase))


class LoopDemoController:
    """Sunum dizisini yuruten zaman tabanli durum makinesi.

    Kendi thread'i YOKTUR; param_bridge tarafindan kontrol dongusunun
    her turunda tick() ile ilerletilir. Boylece sistemde tek bir zaman
    kaynagi kalir ve iki dongunun birbirine karismasi onlenir.
    """

    def __init__(self):
        self.reset()

    # -----------------------------------------------------------------
    # Yasam dongusu
    # -----------------------------------------------------------------

    def reset(self):
        """Diziyi basa alir.

        Moddan her cikista cagrilir; boylece demo her seferinde ayni
        noktadan baslar ve onceki calismadan kalan adim tasinmaz.
        """
        self._active = False
        self._pattern = None
        self._index = 0
        self._move = None
        self._clock = 0.0
        self._last_now = None
        self._cycle_count = 0
        self._pan_lead = 0.0

    # -----------------------------------------------------------------
    # Dongu
    # -----------------------------------------------------------------

    def tick(self, manager, pattern=PATTERN_SWEEP, pan_lead_s=0.0):
        """Diziyi bir tur ilerletir ve o anki hedefi SystemManager'a yazar.

        Mod LOOP_DEMO degilse hicbir sey yapmaz ve diziyi sifirlar.

        Args:
            manager: SystemManager ornegi
            pattern: PATTERN_* hareket duzeni. Sunum sirasinda degisirse
                yeni duzen taretin bulundugu yerden bastan baslar.
            pan_lead_s: Elipste pan'in tilt'ten onde surulme suresi (s).
                Elips donerken degisirse yavasca uygulanir; taramada
                kullanilmaz.
        """
        if manager.get_mode() != SystemMode.LOOP_DEMO:
            if self._active:
                self.reset()
            return

        now = time.monotonic()

        if not self._active or pattern != self._pattern:
            self._begin(manager, now, pattern, pan_lead_s)
        else:
            # Koreografi kendi saatiyle ilerler: dongu takilirsa duvar
            # saati kadar degil en fazla _MAX_DT_S kadar ilerlenir.
            dt = min(now - self._last_now, _MAX_DT_S)
            self._clock += dt
            self._last_now = now

            if self._clock >= self._move.end_time:
                self._next_move()

            # Giris hareketi sirasinda deger SABIT kalir: giris noktasi
            # bu degerle hesaplandi; degisseydi ilk tur baska noktadan
            # baslar ve pan sicrardi.
            if isinstance(self._move, _EllipseLap):
                self._slew_pan_lead(pan_lead_s, dt)

        if isinstance(self._move, _EllipseLap):
            target = self._move.position(self._clock, self._pan_lead)
        else:
            target = self._move.position(self._clock)

        manager.set_demo_target(*target)

    def _begin(self, manager, now, pattern, pan_lead_s):
        """Secilen duzeni taretin bulundugu noktadan baslatir.

        Ilk hareket Python'un tuttugu hedef acidan baslar. Baska bir
        noktadan baslasaydi ilk cercevede servo o noktaya tam hizda
        sicrardi.

        Args:
            manager: SystemManager ornegi
            now: time.monotonic() degeri
            pattern: PATTERN_* hareket duzeni
            pan_lead_s: Elipste pan'in tilt'ten onde surulme suresi (s)
        """
        self._active = True
        self._pattern = pattern
        self._index = 0
        self._clock = 0.0
        self._last_now = now
        self._cycle_count = 0
        self._pan_lead = float(pan_lead_s)

        start = manager.get_target_angles()

        if pattern == PATTERN_ELLIPSE:
            # Elips hareket halinde doner; once duz bir hareketle
            # baslangic noktasina gidilir ve orada DEMO_DWELL_S beklenir.
            self._move = _Move("Elips baslangicina gecis", start,
                               _ellipse_start(self._pan_lead), 0.0)
            log.info("Sunum dizisi basladi: elips (pan %.2f s onde)",
                     self._pan_lead)
        else:
            step = _STEPS[0]
            self._move = _Move(step[0], start, _point(step), 0.0)
            log.info("Sunum dizisi basladi: tarama + capraz")

        log.debug("Sunum adimi: %s", self._move.label)

    def _slew_pan_lead(self, requested, dt):
        """Pan onde surme degerini istenen degere yavasca yaklastirir.

        Args:
            requested: Istenen deger (s)
            dt: Bu turda ilerleyen koreografi suresi (s)
        """
        step = _PAN_LEAD_SLEW * dt
        diff = float(requested) - self._pan_lead

        if abs(diff) <= step:
            self._pan_lead = float(requested)
        else:
            self._pan_lead += step if diff > 0 else -step

    def _next_move(self):
        """Siradaki harekete gecer.

        Yeni hareket bir oncekinin bittigi AN'dan baslar; boylece tur
        suresi kaymaz ve yol kopmaz.
        """
        if self._pattern == PATTERN_ELLIPSE:
            self._next_ellipse_lap()
        else:
            self._next_sweep_step()

    def _next_sweep_step(self):
        """Tarama duzeninin siradaki adimina gecer.

        Yeni adim bir oncekinin bittigi NOKTADAN baslar.
        """
        self._index += 1
        if self._index >= len(_STEPS):
            self._index = 0
            self._cycle_count += 1
            log.info("Sunum dizisi tamamlandi (%d. tur)", self._cycle_count)

        step = _STEPS[self._index]
        self._move = _Move(step[0], self._move.end, _point(step),
                           self._move.end_time)

        log.debug("Sunum adimi: %s", step[0])

    def _next_ellipse_lap(self):
        """Elipsin siradaki turuna gecer.

        Ilk tur yaklasma hareketinden sonra durustan baslar ve rampalidir;
        sonrakiler bir oncekinin bittigi hizla, rampasiz devam eder.
        """
        first = not isinstance(self._move, _EllipseLap)
        if not first:
            self._cycle_count += 1
            log.info("Elips tamamlandi (%d. tur)", self._cycle_count)

        self._move = _EllipseLap(self._move.end_time, soft_start=first)
