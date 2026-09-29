"""Arduino seri protokolu — bayt tanimlari ve cerceve kodlama.

Bu dosya firmware ile BIREBIR eslesmek zorundadir. Buradaki bir sabit
degistirilirse Servo_WASD_DualTrigger_Control.ino de ayni anda
degistirilmelidir; aksi halde sistem sessizce yanlis komut uygular.

Iki komut bicimi vardir:

1. Tek baytlik bitmask — manuel yon ve ates. Bitler birlestirilebilir,
   ornegin ayni anda "tilt yukari + pan saga" = 0x01 | 0x08 = 0x09.
2. Bes baytlik cerceve (0xFB) — mutlak hedef acisi. Otonom takip kullanir.

Ozel komutlar (0xFD-0xFF) bitmask araligiyla cakismaz: bitmask'in
alabilecegi en buyuk deger 0x1F'tir.

Bu modul KURAL ICERMEZ. Ornegin "yukari ve asagi ayni anda basiliysa ne
olur" bir is kuralidir ve control/system_manager.py icinde cozulur;
burada istenilen bitmask oldugu gibi kodlanir.

Protokol kaynagi: BAT-X3 Referans Belgesi, Bolum 7
"""


# NOT: Mevcut firmware (arduino_for_joystick_hss.ino) 0xFB
# cercevesini ayristiriyor (FRAME_HEADER + 4 baytlik payload,
# processFrame() -> moveToImmediate()). encode_absolute() bu yuzden
# control/ katmaninda (AUTO modu, analog kol) guvenle kullanilabilir.



import struct

# ---------------------------------------------------------------------------
# Tek baytlik komut — yon bitleri (bitmask)
# ---------------------------------------------------------------------------

BIT_TILT_UP = 0x01     # W — tilt yukari
BIT_TILT_DOWN = 0x02   # S — tilt asagi
BIT_PAN_LEFT = 0x04    # A — pan sola
BIT_PAN_RIGHT = 0x08   # D — pan saga
BIT_FIRE = 0x10        # J — ates (her iki tetik, kenar algilamali)

# Hicbir bit set degil: tum hareket dur. Watchdog beslemesi olarak da
# kullanilir — "hareket etme ama baglantidayim" anlamina gelir.
CMD_STOP = 0x00

# Bitmask'te gecerli olabilecek tum bitlerin birlesimi. Dogrulama icin.
BITMASK_ALL = BIT_TILT_UP | BIT_TILT_DOWN | BIT_PAN_LEFT | BIT_PAN_RIGHT | BIT_FIRE

# ---------------------------------------------------------------------------
# Tek baytlik komut — ozel komutlar
# ---------------------------------------------------------------------------

CMD_HOME = 0xFD             # Park konumuna don
CMD_ESTOP_RELEASE = 0xFE    # Acil durdurdan cik
CMD_ESTOP = 0xFF            # ACIL DURDUR — tum eksenler dondurulur

# Eksenlere dokunmadan tek atis. Bitmask'teki 0x10 bitinden ayridir:
# bitmask isleyicisi cagrildiginda pan/tilt yonunu de degerlendirir ve
# mutlak aci hedefini bozar.
CMD_FIRE_PULSE = 0xFC


# ---------------------------------------------------------------------------
# Cok baytli cerceve — mutlak aci
# ---------------------------------------------------------------------------

FRAME_HEADER = 0xFB   # [0xFB][pan_lo][pan_hi][tilt_lo][tilt_hi]
FRAME_LENGTH = 5      # Toplam bayt sayisi (baslik dahil)

# Acilar int16 little-endian, 0.1 derece biriminde tasinir.
# Ornek: 47.3 derece -> 473
# Firmware'deki ANGLE_SCALE ile BIREBIR ayni olmalidir; yalnizca bir
# tarafta degistirilirse aci on kat yanlis yorumlanir.
ANGLE_SCALE = 10.0      # 0.1 derece cozunurluk

# int16 tasma siniri. Bu araligin disina cikan aci sessizce yanlis
# yorumlanir, bu yuzden kodlama sirasinda kirpilir.
ANGLE_RAW_MIN = -32768
ANGLE_RAW_MAX = 32767

# Yarim kalan cerceve bu sure sonunda iptal edilir (firmware tarafinda).
# Python tarafinda yalnizca bilgi amaclidir.
FRAME_TIMEOUT_MS = 100

# Cerceve paketleyici: iki adet isaretli 16-bit, little-endian.
_FRAME_STRUCT = struct.Struct("<hh")

# ---------------------------------------------------------------------------
# Kodlama fonksiyonlari
# ---------------------------------------------------------------------------

def encode_motion(up=False, down=False, left=False, right=False, fire=False):
    """Yon bayraklarindan tek baytlik bitmask komutu uretir.

    Cakisan bayraklar (ornegin up ve down birlikte) BURADA cozulmez;
    verilen ne ise o kodlanir. Cakisma cozumu SystemManager'in isidir.

    Args:
        up: Tilt yukari
        down: Tilt asagi
        left: Pan sola
        right: Pan saga
        fire: Ates biti

    Returns:
        bytes — tek baytlik komut
    """
    value = CMD_STOP

    if up:
        value |= BIT_TILT_UP
    if down:
        value |= BIT_TILT_DOWN
    if left:
        value |= BIT_PAN_LEFT
    if right:
        value |= BIT_PAN_RIGHT
    if fire:
        value |= BIT_FIRE

    return bytes([value])


def encode_command(command):
    """Ozel bir komutu (HOME, ESTOP vb.) bayta cevirir.

    Args:
        command: CMD_* sabitlerinden biri

    Returns:
        bytes — tek baytlik komut

    Raises:
        ValueError: Deger 0-255 araliginin disindaysa
    """
    if not 0 <= command <= 0xFF:
        raise ValueError(f"Gecersiz komut bayti: {command}")

    return bytes([command])


def encode_absolute(pan_deg, tilt_deg):
    """Mutlak hedef acisini bes baytlik cerceveye kodlar.

    Aci degerleri 0.1 derece birimine olceklenir ve int16 sinirlarina
    kirpilir. Kirpma sessizce yapilir cunku bu noktaya gelen deger
    SystemManager tarafindan zaten eksen limitlerine gore dogrulanmistir;
    buradaki kirpma yalnizca tasma korumasidir.

    Args:
        pan_deg: Yatay hedef aci (derece)
        tilt_deg: Dikey hedef aci (derece)

    Returns:
        bytes — [0xFB][pan_lo][pan_hi][tilt_lo][tilt_hi]
    """
    pan_raw = _clamp_raw(round(pan_deg * ANGLE_SCALE))
    tilt_raw = _clamp_raw(round(tilt_deg * ANGLE_SCALE))

    return bytes([FRAME_HEADER]) + _FRAME_STRUCT.pack(pan_raw, tilt_raw)

def _clamp_raw(raw):
    """Olceklenmis aci degerini int16 sinirlarina kirpar.

    Args:
        raw: Olceklenmis tamsayi aci

    Returns:
        int — int16 araligindaki deger
    """
    return max(ANGLE_RAW_MIN, min(ANGLE_RAW_MAX, raw))


# ---------------------------------------------------------------------------
# Tani yardimcilari
# ---------------------------------------------------------------------------

# Log ciktilarinda ham bayt yerine okunur ad gostermek icin.
_COMMAND_NAMES = {
    CMD_HOME: "HOME",
    CMD_ESTOP_RELEASE: "ESTOP_RELEASE",
    CMD_ESTOP: "ESTOP",
    CMD_STOP: "STOP",
    CMD_FIRE_PULSE: "FIRE_PULSE",
}

_BIT_NAMES = (
    (BIT_TILT_UP, "UP"),
    (BIT_TILT_DOWN, "DOWN"),
    (BIT_PAN_LEFT, "LEFT"),
    (BIT_PAN_RIGHT, "RIGHT"),
    (BIT_FIRE, "FIRE"),
)


def describe(payload):
    """Gonderilen baytlari insan okunur metne cevirir.

    Yalnizca loglama ve hata ayiklama icindir; kontrol akisinda kullanilmaz.

    Args:
        payload: Gonderilen bytes nesnesi

    Returns:
        str — okunabilir aciklama
    """
    if not payload:
        return "<bos>"

    first = payload[0]

    if first == FRAME_HEADER and len(payload) == FRAME_LENGTH:
        pan_raw, tilt_raw = _FRAME_STRUCT.unpack(payload[1:])
        return (f"FRAME pan={pan_raw / ANGLE_SCALE:.1f} "
                f"tilt={tilt_raw / ANGLE_SCALE:.1f}")

    if first in _COMMAND_NAMES:
        return _COMMAND_NAMES[first]

    if first <= BITMASK_ALL:
        active = [name for bit, name in _BIT_NAMES if first & bit]
        return "MOTION " + ("+".join(active) if active else "STOP")

    return f"<bilinmeyen 0x{first:02X}>"