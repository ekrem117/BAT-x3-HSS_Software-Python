"""En kucuk etkili komut adimi — taret kac birimlik degisime tepki veriyor?

Hassas moddaki "kucuk komut hic hareket uretmiyor, sonra aniden sicriyor"
sorununun kok nedenini belirlemek icin yazildi. Python tarafindaki tum
telafiler (lead, backlash, yercekimi payi) "komut acisini gercek konumdan
uzaklastirirsam servo daha cok tork uretir" varsayimina dayaniyordu. Bu
arac o varsayimi curuttu.

Bu arac SystemManager'i BYPASS eder ve dogrudan mutlak aci cercevesi
gonderir; boylece lead/backlash/yercekimi paylari devrede olmadan saf
"komut -> hareket" iliskisi olculur.

OLCULEN SEY: eksenin gorunur sekilde hareket ettigi EN KUCUK komut
degisimi. Bu deger, hassas moddaki adim buyuklugunun altina inilemeyecek
tabani belirler.

IKI YON AYRI OLCULUR. Tilt ekseni yercekimi yuku tasir: yukari hareket
asagiya gore belirgin daha buyuk bir kirilma toku ister, dolayisiyla iki
yonun esigi ayni degildir. Aracin ilk surumu yalnizca yukari adim atiyordu
ve bu korluk, asagi yonun genliginin olcum yerine hisse gore
ayarlanmasina yol acmisti.

SEBEP KONUSUNDA TARAFSIZDIR: olculen esik servo ölu bandindan da,
statik surtunmeden (stiction) de, yetersiz torktan da kaynaklanabilir.
Arac hangisi oldugunu soylemez; yalnizca esigin KAC BIRIM oldugunu ve
salinimla (dither) asilip asilamadigini soyler.

NOT: darbe cozunurlugu bu esigin sebebi DEGILDIR. Her iki eksen de
500-1800 us araligini kullanir; tilt icin bu birim basina ~28.9 us
eder ve tipik servo ölu bandinin (5-10 us) cok uzerindedir.

CIKTI: olculen esiklerden config/settings.py'ye yazilacak
ANALOG_DITHER_TILT_UP_DEG / ANALOG_DITHER_TILT_DOWN_DEG degerlerini
dogrudan onerir.

main.py CALISMAMALIDIR (port cakisir).

Kullanim:
    py -m tools.deadband_test
"""

import time

import serial.tools.list_ports

from config import settings
from core.enums import LinkState
from core.logging_setup import setup_logging
from hardware import serial_protocol as proto
from hardware.arduino_link import ArduinoLink

# Cerceve gonderim hizi. ArduinoLink cok baytli cerceveleri heartbeat
# olarak TEKRARLAMAZ (senkron kaymasin diye), bu yuzden watchdog'u
# beslemek bu dongunun sorumlulugundadir.
TICK_S = 1.0 / settings.CONTROL_LOOP_HZ

# Denenecek adim buyuklukleri (taret birimi). Kucukten buyuge gidilir;
# ilk "hareket ediyor" denen deger olu bandin ust sinirini verir.
STEP_SIZES = (0.1, 0.2, 0.3, 0.5, 1.0, 1.5, 2.0, 3.0)

# Her adim buyuklugu icin kac adim atilacagi ve adimlar arasi bekleme.
STEPS_PER_SIZE = 6
STEP_INTERVAL_S = 0.6

# Dither (titresim) probu: komut, hedefin etrafinda bu genlikte ve
# taranan frekanslarda salinir. Amac servoyu surekli esigin disina itmek.
#
# NOT: bu deger yalnizca PROBUN genligidir, settings'e yazilacak deger
# degil. Onerilen ayar degeri adim testinden turetilir (bkz. onerilen_genlik).
DITHER_AMPLITUDE = 1.0

# FREKANS TARANIR, cunku belirleyici degisken genlik degil SUREDIR.
#
# Olcumde ortaya cikti: asagi yonde 2.0 birimlik adim 0.6 saniye
# tutuldugunda PURUZSUZ hareket uretti, ama ayni buyuklukteki degisim
# (+/-1.0 = tepe-tepe 2.0) 8 Hz'de HIC hareket uretmedi. 8 Hz'de yarim
# periyot 62 ms; servo yol almaya baslayamadan komut ters donuyor.
#
# Bu yuzden genlik sabit tutulup frekans taranir. Aranan sey: eksenin
# puruzsuz ilerledigi EN YUKSEK frekans (yuksek frekans = daha az
# gorunur salinim, daha az mekanik yipranma).
#
# Yarim periyot karsiliklari: 1 Hz -> 500 ms, 2 Hz -> 250 ms,
# 3 Hz -> 167 ms, 5 Hz -> 100 ms, 8 Hz -> 62 ms.
DITHER_HZ_SWEEP = (1.0, 2.0, 3.0, 5.0, 8.0)

DITHER_DURATION_S = 4.0
DITHER_DRIFT_UNITS = 3.0    # Dither suresince hedefin toplam ilerleyisi

# Sweep baslangici, hareket edilecek yonde yol kalmasi icin ters uca
# yakin secilir: aralikta bu oran kadar iceriden baslanir.
START_MARGIN_RATIO = 0.2

# Yon sabitleri. Isaret kurali proje genelindekiyle ayni:
# +1 = tilt acisinin ARTTIGI yon (UP), -1 = azaldigi yon (DOWN).
UP = 1
DOWN = -1

_YON_ADI = {UP: "YUKARI", DOWN: "ASAGI"}

_SONUC_ADI = {"e": "puruzsuz", "s": "sicrayarak", "h": "HAREKET YOK"}


def ask(message):
    """Kullanicidan onay bekler.

    Returns:
        bool — devam edilsin mi
    """
    answer = input(f"\n>>> {message} [Enter=devam / a=atla / q=cikis] ")
    answer = answer.strip().lower()
    if answer == "q":
        raise KeyboardInterrupt
    return answer != "a"


def ask_moved():
    """Eksenin hareket edip etmedigini sorar.

    Returns:
        str — "e" (evet, puruzsuz), "s" (sicrayarak), "h" (hayir)
    """
    while True:
        answer = input("    Hareket etti mi? "
                       "[e=evet puruzsuz / s=sicrayarak / h=hayir] ")
        answer = answer.strip().lower()
        if answer in ("e", "s", "h"):
            return answer


def ask_directions():
    """Hangi yonlerin olculecegini sorar.

    Iki yonun tam sweep'i 16 soru demektir; kullanici tek yonle
    ilgileniyorsa bosuna sorulmaz.

    Returns:
        tuple — olculecek yonler (UP ve/veya DOWN)
    """
    while True:
        answer = input(
            "\n>>> Hangi yon olculsun? "
            "[1=yukari / 2=asagi / 3=ikisi (varsayilan)] ").strip()

        if answer in ("", "3"):
            return (UP, DOWN)
        if answer == "1":
            return (UP,)
        if answer == "2":
            return (DOWN,)


def start_position(direction):
    """Verilen yonde yol kalacak sekilde baslangic acisini secer.

    Limit kenarinda komut kirpilir ve olcum bozulur; bu yuzden sweep,
    hareket yonunun TERSI ucuna yakin bir noktadan baslar.

    Args:
        direction: UP veya DOWN

    Returns:
        float — baslangic tilt acisi
    """
    span = settings.TILT_MAX_DEG - settings.TILT_MIN_DEG
    margin = span * START_MARGIN_RATIO

    if direction == UP:
        return settings.TILT_MIN_DEG + margin

    return settings.TILT_MAX_DEG - margin


def room_left(tilt, direction):
    """Verilen yonde limite kadar kalan mesafeyi dondurur.

    Args:
        tilt: Guncel komut acisi
        direction: UP veya DOWN

    Returns:
        float — kalan mesafe (taret birimi)
    """
    if direction == UP:
        return settings.TILT_MAX_DEG - tilt

    return tilt - settings.TILT_MIN_DEG


def hold(link, pan, tilt, duration_s):
    """Verilen aciyi belirtilen sure boyunca 50 Hz'de gonderir.

    Cerceve akisi kesilirse firmware watchdog'u devreye girer; bu yuzden
    "bekle" bile aktif gonderim gerektirir.

    Args:
        link: ArduinoLink ornegi
        pan: Yatay komut acisi (taret birimi)
        tilt: Dikey komut acisi (taret birimi)
        duration_s: Gonderim suresi
    """
    payload = proto.encode_absolute(pan, tilt)
    deadline = time.monotonic() + duration_s

    while time.monotonic() < deadline:
        link.send(payload)
        time.sleep(TICK_S)


def test_step_size(link, pan, start_tilt, step, direction):
    """Tek bir adim buyuklugunu tek bir yonde dener.

    Komut acisini `step` kadar kaydirarak STEPS_PER_SIZE kez ilerletir.
    Her adim arasinda aci sabit tutulur; boylece "surekli hareket" ile
    "adim adim sicrama" ayirt edilebilir.

    Args:
        link: ArduinoLink ornegi
        pan: Sabit tutulacak yatay aci
        start_tilt: Baslangic dikey acisi
        step: Adim buyuklugu (taret birimi, daima pozitif)
        direction: UP veya DOWN

    Returns:
        float — son ulasilan tilt acisi
    """
    tilt = start_tilt

    for _ in range(STEPS_PER_SIZE):
        tilt = max(settings.TILT_MIN_DEG,
                   min(settings.TILT_MAX_DEG, tilt + direction * step))
        hold(link, pan, tilt, STEP_INTERVAL_S)

    return tilt


def test_dither(link, pan, start_tilt, direction, hz):
    """Dither probu: komutu hedef etrafinda salindirarak esigi kirar.

    Esik, komut DEGISIMI belirli bir sinirin altinda kaldiginda servonun
    tepki uretmemesidir. Sabit bir offset bu sorunu cozmez (servo bir kez
    konumlanir ve durur), ama surekli salinim servoyu her yarim periyotta
    esigin disina iter.

    SURE DE GENLIK KADAR ONEMLIDIR: yarim periyot cok kisaysa servo yol
    almaya baslayamadan komut ters doner ve eksen yerinde sayar. Bu
    yuzden frekans disaridan verilir ve main() tarafindan taranir.

    Args:
        link: ArduinoLink ornegi
        pan: Sabit tutulacak yatay aci
        start_tilt: Baslangic dikey acisi
        direction: Hedefin ilerletilecegi yon (UP veya DOWN)
        hz: Salinim frekansi

    Returns:
        float — son ulasilan tilt acisi (dither merkezi)
    """
    half_period = 1.0 / (2.0 * hz)
    steps = max(1, int(DITHER_DURATION_S / (2.0 * half_period)))
    drift_per_step = DITHER_DRIFT_UNITS / steps

    center = start_tilt
    sign = 1.0

    for _ in range(steps):
        center = max(settings.TILT_MIN_DEG,
                     min(settings.TILT_MAX_DEG,
                         center + direction * drift_per_step))

        for _ in range(2):
            target = max(settings.TILT_MIN_DEG,
                         min(settings.TILT_MAX_DEG,
                             center + sign * DITHER_AMPLITUDE))
            hold(link, pan, target, half_period)
            sign = -sign

    return center


def onerilen_genlik(sonuclar):
    """Adim testi sonucundan dither genligi onerir.

    Dither tepe-tepe genligi 2 * genlik'tir. Adim testinde PURUZSUZ
    cikan adim, tepe-tepe olarak ulasmak istedigimiz degerdir; dolayisiyla
    onerilen genlik onun yarisidir.

    Args:
        sonuclar: {adim: "e"/"s"/"h"} sozlugu

    Returns:
        (float, str) — onerilen genlik ve dayanagi. Hicbir adim hareket
        uretmediyse (None, None).
    """
    puruzsuz = [adim for adim, r in sonuclar.items() if r == "e"]
    if puruzsuz:
        return min(puruzsuz) / 2.0, "puruzsuz cikan en kucuk adim"

    hareketli = [adim for adim, r in sonuclar.items() if r != "h"]
    if hareketli:
        return (min(hareketli) / 2.0,
                "hareket ureten en kucuk adim (puruzsuz cikan yok, "
                "deger yetersiz kalabilir)")

    return None, None


def run_direction(link, pan, direction):
    """Bir yon icin tam adim sweep'ini calistirir.

    Args:
        link: ArduinoLink ornegi
        pan: Sabit tutulacak yatay aci
        direction: UP veya DOWN

    Returns:
        dict — {adim: "e"/"s"/"h"}
    """
    ad = _YON_ADI[direction]
    tilt = start_position(direction)

    print(f"\n--- {ad} YON ---")
    print(f"    Baslangic tilt={tilt:.1f} "
          f"(bu yonde {room_left(tilt, direction):.1f} birim yol var)")

    hold(link, pan, tilt, 1.0)

    sonuclar = {}

    for step in STEP_SIZES:
        toplam = step * STEPS_PER_SIZE

        if room_left(tilt, direction) < toplam:
            print("\n  (limit yaklasti, basa donuluyor)")
            tilt = start_position(direction)
            hold(link, pan, tilt, 1.0)

        if not ask(f"{ad}  ADIM = {step} birim  "
                   f"({STEPS_PER_SIZE} adim, toplam {toplam:.1f} birim)"):
            continue

        tilt = test_step_size(link, pan, tilt, step, direction)
        sonuclar[step] = ask_moved()

    return sonuclar


def run_dither(link, pan, direction):
    """Bir yon icin dither frekans taramasini calistirir.

    Genlik sabit tutulur, frekans taranir: olcumde belirleyici degiskenin
    genlik degil SURE oldugu ortaya cikti (bkz. DITHER_HZ_SWEEP notu).

    Args:
        link: ArduinoLink ornegi
        pan: Sabit tutulacak yatay aci
        direction: UP veya DOWN

    Returns:
        dict — {hz: "e"/"s"/"h"}. Atlanan frekanslar sozlukte yer almaz.
    """
    ad = _YON_ADI[direction]

    print(f"\n  {ad}: genlik +/-{DITHER_AMPLITUDE} birim SABIT tutulur, "
          "frekans taranir.")
    print(f"    Her turda hedef {DITHER_DRIFT_UNITS} birim {ad.lower()} "
          "ilerletilir; eksen bunu PURUZSUZ izlemeli.")

    sonuclar = {}

    for hz in DITHER_HZ_SWEEP:
        half_ms = 1000.0 / (2.0 * hz)

        if not ask(f"{ad} dither  {hz:.0f} Hz  "
                   f"(yarim periyot {half_ms:.0f} ms)"):
            continue

        tilt = start_position(direction)
        hold(link, pan, tilt, 1.0)
        test_dither(link, pan, tilt, direction, hz)
        sonuclar[hz] = ask_moved()

    return sonuclar


def rapor(direction, sonuclar, dither_sonuc):
    """Tek yonun sonuclarini ve onerilen ayar degerini basar.

    Args:
        direction: UP veya DOWN
        sonuclar: {adim: "e"/"s"/"h"}
        dither_sonuc: ask_moved() sonucu veya None
    """
    ad = _YON_ADI[direction]
    ayar = ("ANALOG_DITHER_TILT_UP_DEG" if direction == UP
            else "ANALOG_DITHER_TILT_DOWN_DEG")

    print(f"\n--- {ad} ---")

    if not sonuclar:
        print("  (olculmedi)")
        return

    for step, sonuc in sorted(sonuclar.items()):
        print(f"  adim {step:>4} birim -> {_SONUC_ADI[sonuc]}")

    hareketli = [s for s, r in sonuclar.items() if r != "h"]
    if hareketli:
        print(f"\n  Hareket ureten en kucuk adim: {min(hareketli)} birim")
    else:
        print("\n  Hicbir adim hareket uretmedi: sorun komut "
              "cozunurlugunde degil, mekanik/firmware tarafinda.")

    genlik, dayanak = onerilen_genlik(sonuclar)
    if genlik is not None:
        print(f"\n  ONERILEN GENLIK:  {ayar} = {genlik:.2f}")
        print(f"    (dayanak: {dayanak} = {genlik * 2:.1f} birim, "
              "dither tepe-tepe genligi 2 * genlik oldugu icin yarisi)")

    if not dither_sonuc:
        return

    print("\n  Dither frekans taramasi (genlik "
          f"+/-{DITHER_AMPLITUDE} birim sabit):")
    for hz, sonuc in sorted(dither_sonuc.items()):
        half_ms = 1000.0 / (2.0 * hz)
        print(f"    {hz:>4.0f} Hz (yarim periyot {half_ms:>3.0f} ms) "
              f"-> {_SONUC_ADI[sonuc]}")

    calisan = [hz for hz, r in dither_sonuc.items() if r == "e"]
    if calisan:
        # En YUKSEK calisan frekans secilir: yuksek frekans daha az
        # gorunur salinim ve daha az mekanik yipranma demektir.
        print(f"\n  ONERILEN FREKANS:  ANALOG_DITHER_HZ = {max(calisan):.0f}")
        print("    (puruzsuz sonuc veren en yuksek frekans; daha yuksegi "
              "servoya yol almaya vakit birakmiyor)")
        return

    kismi = [hz for hz, r in dither_sonuc.items() if r == "s"]
    if kismi:
        print(f"\n  Hicbir frekans puruzsuz degil; en dusuk sicramali: "
              f"{min(kismi):.0f} Hz. DITHER_HZ_SWEEP'e daha dusuk "
              "frekanslar ekleyip tekrar dene.")
        return

    print("\n  HICBIR FREKANS HAREKET URETMEDI.")
    print("    Bu, sorunun genlikle degil SUREYLE ilgili oldugunu "
          "gosterir: adim testinde ayni buyuklukteki degisim "
          f"{STEP_INTERVAL_S} sn tutuldugunda hareket uretiyorsa, servo "
          "yol almak icin taranan tum yarim periyotlardan daha uzun sure "
          "istiyor demektir. DITHER_HZ_SWEEP'e 0.5 Hz gibi daha dusuk "
          "degerler ekle; orada da sonuc alinamazsa dither bu eksen icin "
          "uygun mekanizma degildir.")


def main():
    setup_logging()

    print(__doc__)
    print("\nBulunan seri portlar:")
    for port in serial.tools.list_ports.comports():
        print(f"  {port.device:<8} {port.description}")
    print(f"\nsettings.SERIAL_PORT = {settings.SERIAL_PORT}")
    print(f"TILT araligi = {settings.TILT_MIN_DEG} .. {settings.TILT_MAX_DEG}")

    link = ArduinoLink()
    link.start()

    try:
        print("\n[1] Baglanti bekleniyor...")
        for _ in range(50):
            if link.get_link_state() == LinkState.CONNECTED:
                break
            time.sleep(0.1)

        if link.get_link_state() != LinkState.CONNECTED:
            print("  Arduino'ya baglanilamadi. Port dogru mu? "
                  "main.py kapali mi?")
            return

        print("  Baglandi.")

        pan = settings.HOME_PAN_DEG
        directions = ask_directions()

        print("\n[2] ADIM TESTI — hangi komut degisimi hareket uretiyor?")
        print(f"    Her turda eksen {STEPS_PER_SIZE} kez ilerletilir. "
              "Gozle takip et.")

        adim_sonuclari = {}
        for direction in directions:
            adim_sonuclari[direction] = run_direction(link, pan, direction)

        print("\n[3] DITHER PROBU — salinim esigi kiriyor mu?")

        dither_sonuclari = {}
        for direction in directions:
            dither_sonuclari[direction] = run_dither(link, pan, direction)

        print("\n" + "=" * 60)
        print("SONUC")
        print("=" * 60)

        for direction in directions:
            rapor(direction, adim_sonuclari.get(direction, {}),
                  dither_sonuclari.get(direction))

        if len(directions) == 2:
            up_g, _ = onerilen_genlik(adim_sonuclari.get(UP, {}))
            down_g, _ = onerilen_genlik(adim_sonuclari.get(DOWN, {}))
            if up_g is not None and down_g is not None and up_g != down_g:
                print(f"\n  ASIMETRI: yukari {up_g:.2f}, asagi {down_g:.2f}. "
                      "Yercekimi yuku beklenen sebeptir; iki genligin "
                      "settings'te ayri tutulmasinin gerekcesi budur.")

    except KeyboardInterrupt:
        print("\n\nKullanici durdurdu.")
    finally:
        link.send(proto.encode_command(proto.CMD_STOP))
        time.sleep(0.1)
        link.stop()
        print("Baglanti kapatildi.")


if __name__ == "__main__":
    main()
