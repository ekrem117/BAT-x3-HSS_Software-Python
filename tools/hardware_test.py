"""Arduino donanim testi — ag katmani olmadan.

SystemManager'i gercek seri baglanti ile adim adim calistirir. Her adim
oncesi onay ister; beklenmedik hareket olursa Ctrl+C ile durdurulabilir.

main.py CALISMAMALIDIR (port cakisir).

Kullanim:
    py -m tools.hardware_test
"""

import time

import serial.tools.list_ports

from config import settings
from control.system_manager import SystemManager
from core.enums import LinkState, SystemMode
from core.logging_setup import setup_logging

# SystemManager.update() cagri araligi. ParamBridge calismadigi icin
# dongoyu burada elle cevirmemiz gerekiyor.
TICK_S = 1.0 / settings.CONTROL_LOOP_HZ


def list_ports():
    """Sistemdeki seri portlari listeler."""
    print("\nBulunan seri portlar:")
    ports = list(serial.tools.list_ports.comports())
    if not ports:
        print("  (hicbiri bulunamadi)")
    for port in ports:
        print(f"  {port.device:<8} {port.description}")
    print(f"\nsettings.SERIAL_PORT = {settings.SERIAL_PORT}")
    print(f"settings.BAUD_RATE   = {settings.BAUD_RATE}")


def ask(message):
    """Kullanicidan onay bekler.

    Returns:
        bool — devam edilsin mi
    """
    answer = input(f"\n>>> {message} [Enter=devam / a=atla / q=cikis] ")
    if answer.strip().lower() == "q":
        raise KeyboardInterrupt
    return answer.strip().lower() != "a"


def hold(mgr, seconds, **directions):
    """Verilen yonleri belirtilen sure boyunca basili tutar.

    Kontrol dongusu burada elle cevrilir; gercek sistemde bunu
    ParamBridge yapar.

    Args:
        mgr: SystemManager ornegi
        seconds: Tutulacak sure
        **directions: up/down/left/right bayraklari
    """
    mgr.set_manual_input(**directions)
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        mgr.update()
        time.sleep(TICK_S)

    # Tuslari birak ve durus komutunu gonder.
    mgr.set_manual_input(up=False, down=False, left=False, right=False)
    mgr.update()


def idle(mgr, seconds):
    """Hareket vermeden dongoyu cevirir (heartbeat surekliligi icin)."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        mgr.update()
        time.sleep(TICK_S)


def main():
    setup_logging()
    list_ports()

    input("\nSerial Monitor kapali ve namlular bos mu? Enter'a bas... ")

    mgr = SystemManager()
    mgr.start()

    try:
        # --- 1. Baglanti ---------------------------------------------
        print("\n[1] Baglanti bekleniyor (Arduino reset suresi)...")
        time.sleep(2.5)
        status = mgr.get_status()
        print(f"  system.link = {status['system.link']} "
              f"(1 olmali)")
        if status["system.link"] != 1:
            print("  BAGLANTI YOK. SERIAL_PORT ve Serial Monitor'u kontrol et.")
            return

        # --- 2. HOME --------------------------------------------------
        if ask("HOME komutu gonderilsin mi? (taret park konumuna gider)"):
            mgr.home()
            idle(mgr, 3.0)
            print("  HOME tamam")

        # --- 3. MANUAL mod --------------------------------------------
        print("\n[3] MANUAL moda geciliyor")
        print("  set_mode:", mgr.set_mode(SystemMode.MANUAL))

        # --- 4. Pan -----------------------------------------------------
        if ask("PAN SOLA 1.5 saniye?"):
            hold(mgr, 1.5, left=True)
            idle(mgr, 0.5)

        if ask("PAN SAGA 1.5 saniye?"):
            hold(mgr, 1.5, right=True)
            idle(mgr, 0.5)

        # --- 5. Tilt ----------------------------------------------------
        if ask("TILT YUKARI 1.0 saniye?"):
            hold(mgr, 1.0, up=True)
            idle(mgr, 0.5)

        if ask("TILT ASAGI 1.0 saniye?"):
            hold(mgr, 1.0, down=True)
            idle(mgr, 0.5)

        # --- 6. Cakisan yon ---------------------------------------------
        if ask("A ve D BIRLIKTE 1.5 saniye? (taret HIC oynamamali)"):
            hold(mgr, 1.5, left=True, right=True)
            idle(mgr, 0.5)

        # --- 7. ESTOP mandali -------------------------------------------
        if ask("ESTOP testi? (pan baslar, 0.7 sn sonra durdurulur)"):
            mgr.set_manual_input(left=True)
            deadline = time.monotonic() + 0.7
            while time.monotonic() < deadline:
                mgr.update()
                time.sleep(TICK_S)

            mgr.emergency_stop()
            print("  ESTOP gonderildi - taret ANINDA durmali")
            # Yon tuslari hala basili; mandal calisiyorsa hareket etmemeli.
            idle(mgr, 2.0)
            print("  Taret hareketsiz kaldiysa mandal calisiyor")

            input("  Devam icin Enter (ESTOP birakilacak)... ")
            mgr.set_mode(SystemMode.IDLE)
            idle(mgr, 0.5)
            print("  ESTOP birakildi")

        # --- 8. Tetik ---------------------------------------------------
        if ask("TETIK testi? (NAMLULARIN BOS OLDUGUNDAN EMIN OL)"):
            mgr.set_mode(SystemMode.MANUAL)
            print("  set_armed:", mgr.set_armed(True))
            print("  fire:", mgr.fire())
            idle(mgr, 2.0)
            mgr.set_armed(False)
            print("  Her iki tetik hareket edip dinlenmeye dondu mu?")

        # --- 9. Kapanis --------------------------------------------------
        print("\n[9] HOME'a donuluyor")
        mgr.set_mode(SystemMode.IDLE)
        mgr.home()
        idle(mgr, 3.0)

        print("\nDurum ozeti:")
        for key, value in mgr.get_status().items():
            print(f"  {key:<22} = {value}")

    except KeyboardInterrupt:
        print("\n\nKULLANICI DURDURDU - acil durdur gonderiliyor")
        mgr.emergency_stop()
        mgr.update()
    finally:
        mgr.stop()
        print("\nTest bitti, port kapatildi.")


if __name__ == "__main__":
    main()