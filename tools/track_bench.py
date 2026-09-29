"""Otonom takip performans olcumu.

Sabit sureli bir kosu boyunca ornekler toplar ve karsilastirilabilir
sayilar uretir. Amac "daha iyi gibi" yerine olculmus sonuc elde
etmektir.

OLCULEN BUYUKLUKLER

    Kilitli kalma orani
        Zamanin yuzde kaci LOCKED durumunda gecti. Dusukse hedef
        surekli kaybediliyor demektir.

    Kilit devri / dakika
        Ayni hedef icin kac kez yeni track_id'ye gecildi.
        Ego-motion telafisinin ana olcutu budur.

    Tespit kaybi orani
        Kac ornekte hic tespit yoktu. Model/pozlama tarafini olcer.

    Ortalama mutlak hata
        Kilitliyken nisan noktasinin merkeze uzakligi (piksel).
        Kontrolcu ayarinin olcutu.

    Hedefte kalma orani
        Hatanin olu bant icinde kaldigi ornek orani. Ates izni bu
        kosula bagli oldugu icin dogrudan puana etki eder.

ON KOSUL
    Katalogda su parametreler bulunmalidir (patch dosyasina bakin):
        engage.track_id, engage.locked, engage.reacquires
        vision.aim_error_x, vision.aim_error_y

KULLANIM
    py -m tools.track_bench 60 ego_acik

    Ilk arguman sure (saniye), ikincisi kosu etiketidir. Etiket
    ciktiya yazilir; farkli ayarlari karsilastirirken hangi kosunun
    hangi ayara ait oldugu karisir.

KARSILASTIRMA YONTEMI
    Ayni hedef hareketini iki kez tekrarlayin: bir kez eski ayarla,
    bir kez yeni ayarla. Hedefi mumkun oldugunca ayni sekilde
    hareket ettirin. Tek degisken degistirin.
"""

import json
import math
import socket
import sys
import time

from config import settings

WATCH_KEYS = (
    "system.mode",
    "engage.track_id",
    "engage.locked",
    "engage.reacquires",
    "vision.aim_error_x",
    "vision.aim_error_y",
    "vision.detection_count",
    "vision.inference_ms",
)

SAMPLE_HZ = 10.0
RECV_WAIT_S = 0.3
MODE_AUTO = 2


def _unwrap(raw):
    """Sarmalanmis GET degerini acar."""
    if not isinstance(raw, dict):
        return raw
    for field in ("value", "val", "v", "Value"):
        if field in raw:
            return raw[field]
    return None


def _percentile(values, fraction):
    """Siralanmis listeden yuzdelik deger doner.

    Ortalama tek basina yaniltir: birkac buyuk sapma ortalamayi
    sisirir. 95. yuzdelik "en kotu durum" hakkinda fikir verir.

    Args:
        values: Sayi listesi
        fraction: 0.0 - 1.0 arasi

    Returns:
        float veya liste bossa 0.0
    """
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(len(ordered) * fraction))
    return ordered[index]


class Run:
    """Tek bir olcum kosusunun biriktirdigi sayilar."""

    def __init__(self, label):
        self.label = label
        self.samples = 0
        self.auto_samples = 0
        self.locked_samples = 0
        self.no_detection = 0
        self.on_target = 0

        self.errors = []
        self.inference_ms = []

        self.track_changes = 0
        self.last_track_id = None
        self.first_reacquires = None
        self.last_reacquires = 0

    def add(self, values):
        """Tek ornegi isler.

        Args:
            values: Cozulmus parametre sozlugu
        """
        self.samples += 1

        if values.get("system.mode") != MODE_AUTO:
            return

        self.auto_samples += 1

        inference = values.get("vision.inference_ms")
        if inference:
            self.inference_ms.append(float(inference))

        detections = values.get("vision.detection_count") or 0
        if detections == 0:
            self.no_detection += 1

        reacquires = values.get("engage.reacquires")
        if reacquires is not None:
            if self.first_reacquires is None:
                self.first_reacquires = int(reacquires)
            self.last_reacquires = int(reacquires)

        track_id = values.get("engage.track_id")
        if track_id is not None and track_id >= 0:
            if self.last_track_id is not None and track_id != self.last_track_id:
                self.track_changes += 1
            self.last_track_id = track_id

        if not values.get("engage.locked"):
            return

        self.locked_samples += 1

        ex = values.get("vision.aim_error_x")
        ey = values.get("vision.aim_error_y")
        if ex is None or ey is None:
            return

        error = math.hypot(float(ex), float(ey))
        self.errors.append(error)

        if error < settings.AIM_DEAD_ZONE_PX:
            self.on_target += 1

    def report(self, duration_s):
        """Sonuclari yazdirir.

        Args:
            duration_s: Kosu suresi (saniye)
        """
        print("\n" + "=" * 62)
        print("KOSU: {}".format(self.label))
        print("Sure: {:.0f} s   Ornek: {}   AUTO'da: {}".format(
            duration_s, self.samples, self.auto_samples))
        print("=" * 62)

        if self.auto_samples == 0:
            print("AUTO modunda hic ornek alinmadi. Mod dogru mu?")
            return

        auto = float(self.auto_samples)
        minutes = duration_s / 60.0

        locked_pct = 100.0 * self.locked_samples / auto
        nodet_pct = 100.0 * self.no_detection / auto

        reacquires = 0
        if self.first_reacquires is not None:
            reacquires = self.last_reacquires - self.first_reacquires

        print("Kilitli kalma orani  : {:5.1f} %   (yuksek olmali)".format(
            locked_pct))
        print("Tespit kaybi orani   : {:5.1f} %   (dusuk olmali)".format(
            nodet_pct))
        print("Kilit devri          : {:5.1f} / dk (dusuk olmali)".format(
            self.track_changes / minutes if minutes else 0.0))
        print("Yeniden eslestirme   : {:5.1f} / dk".format(
            reacquires / minutes if minutes else 0.0))

        if self.errors:
            mean_error = sum(self.errors) / len(self.errors)
            on_target_pct = 100.0 * self.on_target / len(self.errors)

            print("\nKilitliyken nisan hatasi (piksel)")
            print("  Ortalama           : {:6.1f}".format(mean_error))
            print("  Ortanca            : {:6.1f}".format(
                _percentile(self.errors, 0.5)))
            print("  95. yuzdelik       : {:6.1f}   (en kotu durum)".format(
                _percentile(self.errors, 0.95)))
            print("  Hedefte kalma      : {:5.1f} %   (olu bant {:.0f} px)".format(
                on_target_pct, settings.AIM_DEAD_ZONE_PX))
        else:
            print("\nKilitli ornek yok - nisan hatasi olculemedi.")

        if self.inference_ms:
            print("\nCikarim suresi (ms)")
            print("  Ortalama           : {:6.1f}".format(
                sum(self.inference_ms) / len(self.inference_ms)))
            print("  95. yuzdelik       : {:6.1f}".format(
                _percentile(self.inference_ms, 0.95)))

        print("=" * 62)
        print("\nOZET SATIRI (karsilastirma icin kopyalayin):")
        print("{} | kilitli %{:.0f} | devir {:.1f}/dk | hata {:.0f} px | "
              "hedefte %{:.0f} | tespit_kaybi %{:.0f}".format(
                  self.label,
                  locked_pct,
                  self.track_changes / minutes if minutes else 0.0,
                  sum(self.errors) / len(self.errors) if self.errors else 0.0,
                  100.0 * self.on_target / len(self.errors) if self.errors else 0.0,
                  nodet_pct))


def main():
    duration = 60.0
    label = "kosu"

    if len(sys.argv) > 1:
        duration = float(sys.argv[1])
    if len(sys.argv) > 2:
        label = sys.argv[2]

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(RECV_WAIT_S)
    addr = (settings.COMMAND_UDP_HOST, settings.COMMAND_UDP_PORT)

    print(__doc__)
    print("Olcum basliyor: {:.0f} saniye, etiket '{}'".format(duration, label))
    print("AUTO moda gecin ve hedefi hareket ettirin.\n")

    run = Run(label)
    msg_id = 0
    period = 1.0 / SAMPLE_HZ
    started = time.monotonic()
    missing_warned = False

    try:
        while time.monotonic() - started < duration:
            msg_id += 1
            packet = {"Method": "GET", "messageID": msg_id}
            packet.update({key: "?" for key in WATCH_KEYS})
            sock.sendto(json.dumps(packet).encode(), addr)

            try:
                data, _ = sock.recvfrom(settings.UDP_BUFFER_SIZE)
                reply = json.loads(data.decode(errors="replace"))
            except (socket.timeout, OSError, json.JSONDecodeError):
                time.sleep(period)
                continue

            values = {k: _unwrap(v) for k, v in reply.items()}

            if values.get("engage.locked") is None and not missing_warned:
                missing_warned = True
                print("UYARI: engage.* parametreleri katalogda yok.")
                print("       Patch uygulanmadan sonuclar eksik olur.\n")

            run.add(values)

            elapsed = time.monotonic() - started
            if run.samples % 50 == 0:
                print("  {:.0f}/{:.0f} s   kilitli={}  hata=({}, {})".format(
                    elapsed, duration,
                    values.get("engage.locked"),
                    values.get("vision.aim_error_x"),
                    values.get("vision.aim_error_y")))

            time.sleep(period)

    except KeyboardInterrupt:
        print("\nOlcum erken bitirildi.")
    finally:
        sock.close()

    run.report(time.monotonic() - started)


if __name__ == "__main__":
    main()