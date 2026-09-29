"""Kontrol katmani mantik testi — donanim ve ag gerektirmez.

SystemManager'i sahte bir seri baglanti ile calistirir; gonderilen
baytlar ekrana yazilir. Mod gecis kurallari, ates guvenlik zinciri ve
yon bitmask'i Arduino olmadan dogrulanir.

Uretim kodunun parcasi degildir.

Kullanim:
    python -m tools.control_test
"""

from control.system_manager import SystemManager
from core.enums import LinkState, SystemMode
from core.logging_setup import setup_logging
from hardware import serial_protocol as proto


class FakeLink:
    """ArduinoLink yerine gecen sahte baglanti.

    Ayni arayuzu sunar; porta yazmak yerine son bayti saklar. Boylece
    SystemManager gercek donanim olmadan test edilebilir.
    """

    def __init__(self):
        self.last = None

    def start(self):
        pass

    def stop(self):
        pass

    def get_link_state(self):
        return LinkState.CONNECTED

    def send(self, payload):
        self.last = payload
        return True


def show(link, label):
    """Son gonderilen bayti okunur bicimde yazar."""
    print(f"  {label:<32} -> {proto.describe(link.last)}")


def main():
    setup_logging()

    link = FakeLink()
    mgr = SystemManager(link=link)
    mgr.start()

    print("\n[1] IDLE modunda yon girdisi yok sayilmali")
    mgr.set_manual_input(left=True)
    mgr.update()
    show(link, "IDLE + A basili")

    print("\n[2] MANUAL moda gecis ve yon bitleri")
    print("  set_mode(MANUAL):", mgr.set_mode(SystemMode.MANUAL))
    mgr.set_manual_input(left=True)
    mgr.update()
    show(link, "MANUAL + A")
    mgr.set_manual_input(up=True)
    mgr.update()
    show(link, "MANUAL + A + W")

    print("\n[3] Zit yonler birbirini iptal etmeli")
    mgr.set_manual_input(right=True)
    mgr.update()
    show(link, "A + D birlikte (pan durmali)")

    print("\n[4] Ates guvenlik zinciri")
    print("  ARM kapaliyken fire():", mgr.fire())
    print("  set_armed(True):", mgr.set_armed(True))
    print("  ARM acikken fire():", mgr.fire())
    mgr.update()
    show(link, "ates darbesi 1. dongu")
    mgr.update()
    show(link, "ates darbesi 2. dongu")
    mgr.update()
    show(link, "darbe bitti (FIRE dusmeli)")
    print("  cooldown icinde fire():", mgr.fire())

    print("\n[5] Dogrudan mod gecisi yasak olmali")
    print("  MANUAL -> AUTO:", mgr.set_mode(SystemMode.AUTO))

    print("\n[6] ESTOP")
    print("  emergency_stop():", mgr.emergency_stop())
    mgr.update()
    show(link, "ESTOP komutu")
    mgr.update()
    show(link, "ESTOP sonrasi heartbeat")
    print("  ESTOP'ta fire():", mgr.fire())
    print("  ESTOP -> MANUAL (yasak):", mgr.set_mode(SystemMode.MANUAL))
    print("  ESTOP -> IDLE:", mgr.set_mode(SystemMode.IDLE))
    mgr.update()
    show(link, "ESTOP cikis komutu")

    print("\n[7] LOOP_DEMO: taretin tek sahibi koreografi")
    print("  IDLE -> LOOP_DEMO:", mgr.set_mode(SystemMode.LOOP_DEMO))
    mgr.update()
    show(link, "hedef gelmeden (durus)")
    mgr.set_analog_input(pan=1.0)
    mgr.update()
    show(link, "analog kol (yok sayilmali)")
    mgr.set_demo_target(60.0, 130.0)
    mgr.update()
    show(link, "demo hedefi 60 / 130")
    mgr.set_demo_target(0.0, 999.0)
    mgr.update()
    show(link, "sinir disi hedef (kirpilmali)")
    print("  LOOP_DEMO'da set_armed(True):", mgr.set_armed(True))
    print("  LOOP_DEMO -> IDLE:", mgr.set_mode(SystemMode.IDLE))
    mgr.set_demo_target(80.0, 140.0)
    mgr.update()
    show(link, "IDLE'da demo hedefi (durus)")

    print("\n[8] Durum ozeti")
    for key, value in mgr.get_status().items():
        print(f"  {key:<22} = {value}")

    mgr.stop()


if __name__ == "__main__":
    main()