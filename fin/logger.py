import logging
import os
from logging.handlers import RotatingFileHandler

from fin.config import LOG_DIR as _CONFIG_LOG_DIR

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class RelativePathFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        try:
            record.relpath = os.path.relpath(record.pathname, _PROJECT_ROOT)
        except ValueError:
            record.relpath = record.pathname

        try:
            from fin.context import request_id_ctx

            rid = request_id_ctx.get()
            record.request_id = rid if rid else "-"
        except (ImportError, AttributeError):
            record.request_id = "-"

        return super().format(record)


def setup_logging(
    script_name: str,
    log_filename: str = "fin.log",
    console_level: int | None = logging.INFO,
) -> logging.Logger:
    log_dir = str(_CONFIG_LOG_DIR)
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, log_filename)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    if root.hasHandlers():
        root.handlers.clear()

    file_fmt = RelativePathFormatter(
        "%(asctime)s - [%(levelname)s] [%(request_id)s] - %(relpath)s:%(lineno)d - %(message)s"
    )
    fh = RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(file_fmt)
    root.addHandler(fh)

    if console_level is not None:
        ch = logging.StreamHandler()
        ch.setLevel(console_level)
        ch.setFormatter(
            RelativePathFormatter(
                "%(asctime)s [%(levelname)s] [%(request_id)s] %(message)s"
            )
        )
        root.addHandler(ch)

    root.setLevel(logging.INFO)
    for noisy in (
        "multipart",
        "python_multipart",
        "urllib3",
        "uvicorn",
        "yfinance",
        "peewee",
    ):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    if script_name:
        logging.getLogger(script_name).setLevel(logging.DEBUG)

    root.info("=" * 60)
    root.info(f"START: {script_name}")
    root.info("-" * 60)
    return root


def get_access_logger(log_filename: str = "access.log") -> logging.Logger:
    log_dir = str(_CONFIG_LOG_DIR)
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, log_filename)

    logger = logging.getLogger("fin.access")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if not logger.handlers:
        fh = RotatingFileHandler(
            log_file, maxBytes=10 * 1024 * 1024, backupCount=10, encoding="utf-8"
        )
        fh.setLevel(logging.INFO)
        fh.setFormatter(
            RelativePathFormatter("%(asctime)s - [%(request_id)s] %(message)s")
        )
        logger.addHandler(fh)

    return logger
