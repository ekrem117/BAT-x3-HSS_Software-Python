"""Capraz hareket dogrulamasi — klavye devre disi.

Yon girdileri dogrudan verilir; boylece klavye otomatik tekrar kisiti
denklemden cikar. Bu test gecerse zincir es zamanli hareketi
destekliyor demektir ve sorun yalnizca test betiginin girdi yontemidir.

main.py CALISMAMALIDIR (port cakisir).

Kullanim:
    py -m tools.diagonal_test
"""

import time

from config import settings
from control.system_manager import SystemManager
from core.enums import SystemMode
from core.logging_setup import setup_logging
from hardware import serial_protocol as proto

TICK_S = 1.0 / settings.CONTROL_LOOP_HZ


def drive(mgr, seconds, label, **directions):
    """Verilen yonleri belirtilen sure boyunca uygular.

    Args:
        mgr: SystemManager ornegi
        seconds: Sure
        label: Ekrana yazilacak aciklama
        **directions: up/down/left/right
    """
    mgr.set_manual_input(up=False, down=False, left=False, right=False)
    mgr.set_manual_input(**directions)

    # Gonderilecek bayti bir kez goster: capraz komutta iki bit birden
    # set olmali (ornegin RIGHT+UP = 0x09).
    payload = proto.encode_motion(**{
        key: directions.get(key, False)
        for key in ("up", "down", "left", "right")
    })
    print(f"  {label:<24} bayt = {proto.describe(payload)}")

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

    try:
         
        """
        print("\nTek eksen (referans):")
        drive(mgr, 1.5, "sadece SAGA", right=True)
        drive(mgr, 0.5, "dur")
        drive(mgr, 1.5, "sadece YUKARI", up=True)
        drive(mgr, 0.5, "dur")
        """

        print("\nCapraz (asil test):")
        drive(mgr, 2.0, "SAGA + YUKARI", right=True, up=True)
        drive(mgr, 0.5, "dur")
        drive(mgr, 2.0, "SOLA + ASAGI", left=True, down=True)
        drive(mgr, 0.5, "dur")

        print("\nCapraz + ates:")
        mgr.set_armed(True)
        mgr.set_manual_input(left=True)
        mgr.fire()
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            mgr.update()
            time.sleep(TICK_S)

        drive(mgr, 0.5, "dur")
        mgr.set_mode(SystemMode.IDLE)
        mgr.home()
        time.sleep(2.0)

    except KeyboardInterrupt:
        mgr.emergency_stop()
        mgr.update()
    finally:
        mgr.stop()


if __name__ == "__main__":
    main()