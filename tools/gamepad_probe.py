"""Oyun kolu kesif araci.

Kolun eksen ve buton numaralarini ekrana yazar. Kol markasina gore bu
numaralar degistigi icin, kontrol betigini yapilandirmadan once bir kez
calistirilir.

Gereksinim:
    pip install pygame

Kullanim:
    py -m tools.gamepad_probe
"""

import os
import time

# pygame'in acilista bastigi tanitim mesajini bastir.
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

import pygame

# Eksen degeri bu esigi asarsa "hareket var" sayilir. Ucuz kollarda
# merkez tam sifirda durmaz; bu esik o sapmayi filtreler.
REPORT_THRESHOLD = 0.30


def main():
    pygame.init()
    pygame.joystick.init()

    if pygame.joystick.get_count() == 0:
        print("Kol bulunamadi. USB baglantisini kontrol et.")
        return

    pad = pygame.joystick.Joystick(0)
    pad.init()

    print(f"Kol: {pad.get_name()}")
    print(f"Eksen sayisi : {pad.get_numaxes()}")
    print(f"Buton sayisi : {pad.get_numbuttons()}")
    print(f"Hat (dpad)   : {pad.get_numhats()}")
    print("\nTuslara bas ve analoglari oynat. Ctrl+C ile cik.\n")

    try:
        while True:
            pygame.event.pump()

            # Esigi asan eksenleri yaz.
            for i in range(pad.get_numaxes()):
                value = pad.get_axis(i)
                if abs(value) > REPORT_THRESHOLD:
                    print(f"  EKSEN {i} = {value:+.2f}")

            # Basili butonlari yaz.
            for i in range(pad.get_numbuttons()):
                if pad.get_button(i):
                    print(f"  BUTON {i}")

            # Dpad.
            for i in range(pad.get_numhats()):
                hat = pad.get_hat(i)
                if hat != (0, 0):
                    print(f"  HAT {i} = {hat}")

            time.sleep(0.15)

    except KeyboardInterrupt:
        print("\nCikildi.")
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()