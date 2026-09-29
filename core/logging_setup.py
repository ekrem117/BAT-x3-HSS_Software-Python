"""Loglama yapilandirmasi.

Loglar hem konsola hem donen dosyaya (RotatingFileHandler) yazilir.
Log dosyasi proje kokundeki logs/ klasorune yazilir; calisma dizininden
bagimsizdir.

main() basinda bir kez cagrilmalidir; oncesindeki loglar kaydedilmez.
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)-18s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
MAX_BYTES = 5_000_000
BACKUP_COUNT = 3


def setup_logging(log_name="batx3.log", level=logging.INFO):
    """Kok logger'i yapilandirir.

    Args:
        log_name: Log dosyasi adi. Proje kokundeki logs/ klasorune yazilir.
        level: Minimum log seviyesi. Hata ayiklama icin logging.DEBUG kullanin.

    Returns:
        Path — olusturulan log dosyasinin yolu
    """
    log_dir = Path(__file__).resolve().parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / log_name

    fmt = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    file_handler = RotatingFileHandler(
        log_file, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(file_handler)
    root.addHandler(console_handler)

    # Ucuncu taraf kutuphanelerin DEBUG loglarini bastir
    for name in ("matplotlib", "PIL", "ultralytics"):
        logging.getLogger(name).setLevel(logging.WARNING)

    logging.getLogger("logging_setup").info("Log dosyasi: %s", log_file)
    return log_file