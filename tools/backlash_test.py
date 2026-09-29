"""Disli boslugu olcumu.

Ekseni bir yone hareket ettirir, durdurur, sonra TERS yone kucuk
adimlarla ilerletir. Taretin gorunur sekilde hareket ettigi ilk adim
bosluk miktarini verir.

main.py CALISMAMALIDIR (port cakisir).

Kullanim:
    py -m tools.backlash_test
"""

import time

from config import settings
from control.system_manager import SystemManager
from core.enums import SystemMode
from core.logging_setup import setup_logging

TICK_S = 1.0 / settings.CONTROL_LOOP_HZ

# Ters yonde her adimda hedefin kayacagi miktar.
STEP_DEG = 0.05

# Kac adim denenecek.
STEP_COUNT = 200


def settle(mgr, seconds):
    """Girdi vermeden dongoyu cevirir."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        mgr.update()
        time.sleep(TICK_S)


def main():
    setup_logging()

    mgr = SystemManager()
    mgr.start()
    time.sleep(2.5)

    if mgr.get_status()["system.link"] != 1:
        print("Arduino baglantisi yok.")
        mgr.stop()
        return

    mgr.set_mode(SystemMode.MANUAL)

    print("\nEksen secimi: 1=PAN  2=TILT")
    axis = input("Secim: ").strip()
    is_pan = axis != "2"

    try:
        print("\n[1] Eksen bir yone suruluyor (slack bu yonde kapali)...")
        mgr.set_analog_input(pan=0.5 if is_pan else 0.0,
                             tilt=0.0 if is_pan else 0.5)
        settle(mgr, 1.5)
        mgr.set_analog_input(pan=0.0, tilt=0.0)
        settle(mgr, 1.0)

        input("\nTaretin konumunu isaretle, sonra Enter'a bas... ")

        print(f"\n[2] Ters yonde {STEP_DEG} derecelik adimlar. "
              "Hareketi GORDUGUN anda Ctrl+C bas.\n")

        # Hedefi dogrudan kaydiriyoruz: analog girdi yerine adim adim
        # ilerletmek olcumu kesinlestirir.
        for i in range(1, STEP_COUNT + 1):
            with mgr._lock:
                if is_pan:
                    mgr._pan_target -= STEP_DEG
                else:
                    mgr._tilt_target -= STEP_DEG

            mgr.update()
            print(f"  adim {i:2d}  ->  toplam {i * STEP_DEG:.2f} derece")
            time.sleep(0.6)

        print("\nHareket gorulmedi. STEP_COUNT degerini artir.")

    except KeyboardInterrupt:
        print("\n\nDurduruldu. Ekrandaki son 'toplam' degeri bosluktur.")
        print("Bu degeri settings.py'deki BACKLASH_*_DEG alanina yaz.")
    finally:
        mgr.set_mode(SystemMode.IDLE)
        mgr.stop()


if __name__ == "__main__":
    main()