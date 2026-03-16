import logging
import os
import sys
from functools import partialmethod
from pathlib import Path
from typing import Callable

from loguru import logger as _logger

LOG_DIR = Path("log")
QQBOT_LOG_DIR = LOG_DIR / "qqbot"

LOG_DIR.mkdir(parents=True, exist_ok=True)
QQBOT_LOG_DIR.mkdir(parents=True, exist_ok=True)

DEBUG_MODE: bool = (
    os.getenv("AC_DEBUG") == "1"
    or os.getenv("DEBUG") == "1"
    or "--debug" in sys.argv
    or "-d" in sys.argv
)

_logger.remove()
_logger.__class__.detail = partialmethod(_logger.__class__.log, "DEBUG")  # type: ignore[attr-defined]


def _inject_origin(record: dict) -> None:
    extra = record["extra"]
    if "origin" not in extra:
        extra["origin"] = f"{record['name']}:{record['function']}:{record['line']}"
    extra["level_short"] = {
        "DEBUG": "DEBG",
        "INFO": "INFO",
        "WARNING": "WARN",
        "ERROR": "ERRO",
    }.get(record["level"].name, "INFO")


_logger = _logger.patch(_inject_origin)

console_level = "DEBUG" if DEBUG_MODE else "INFO"
file_level = "DEBUG" if DEBUG_MODE else "INFO"
base_format = "{time:YYYY-MM-DD HH:mm:ss.SSS} | {extra[level_short]} | {extra[origin]} | {message}"
_console_sink_id: int | None = None

_console_sink_id = _logger.add(
    sys.stdout,
    level=console_level,
    colorize=True,
    backtrace=True,
    diagnose=DEBUG_MODE,
    format=(
        "<green>{time:MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{extra[level_short]}</level> | "
        "<cyan>{extra[origin]}</cyan> | "
        "<level>{message}</level>"
    ),
)

_logger.add(
    LOG_DIR / "app.log",
    rotation="00:00",
    retention="7 days",
    encoding="utf-8",
    level=file_level,
    backtrace=True,
    diagnose=DEBUG_MODE,
    format=base_format,
)

_logger.add(
    LOG_DIR / "warning.log",
    retention="30 days",
    encoding="utf-8",
    level="WARNING",
    backtrace=True,
    diagnose=DEBUG_MODE,
    format=base_format,
)

logger = _logger
log = _logger
_botpy_logging_configured = False


def add_runtime_log_sink(callback: Callable[[str], None], level: str = "DEBUG") -> int:
    return logger.add(
        lambda message: callback(str(message).rstrip()),
        level=level,
        colorize=False,
        backtrace=False,
        diagnose=False,
        format=base_format,
    )


def remove_runtime_log_sink(sink_id: int) -> None:
    logger.remove(sink_id)


def disable_console_logging() -> None:
    global _console_sink_id
    if _console_sink_id is not None:
        logger.remove(_console_sink_id)
        _console_sink_id = None


def enable_console_logging() -> None:
    global _console_sink_id
    if _console_sink_id is not None:
        return
    _console_sink_id = logger.add(
        sys.stdout,
        level=console_level,
        colorize=True,
        backtrace=True,
        diagnose=DEBUG_MODE,
        format=(
            "<green>{time:MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{extra[level_short]}</level> | "
            "<cyan>{extra[origin]}</cyan> | "
            "<level>{message}</level>"
        ),
    )


class InterceptHandler(logging.Handler):
    """Forward stdlib ``logging`` records into loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        level_name = record.levelname.upper()
        if level_name not in {"DEBUG", "INFO", "WARNING", "ERROR"}:
            level_name = "ERROR" if record.levelno >= logging.ERROR else "INFO"

        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        origin = f"{record.name}:{record.funcName}:{record.lineno}"
        logger.bind(
            origin=origin,
            logger_name=record.name,
        ).opt(depth=depth, exception=record.exc_info).log(level_name, record.getMessage())


def setup_botpy_logging() -> logging.Logger:
    """Intercept ``botpy`` library logs into loguru and route them to ``log/qqbot/``."""
    global _botpy_logging_configured

    if _botpy_logging_configured:
        return logging.getLogger("botpy")

    _logger.add(
        QQBOT_LOG_DIR / "qqbot.log",
        rotation="00:00",
        retention="30 days",
        encoding="utf-8",
        level=file_level,
        format=base_format,
        filter=lambda record: record["extra"].get("logger_name", "").startswith("botpy")
        or record["name"].startswith(("powers.qq_bot", "powers.message_handler")),
    )

    botpy_logger = logging.getLogger("botpy")
    botpy_logger.handlers.clear()
    botpy_logger.propagate = False
    botpy_logger.addHandler(InterceptHandler())
    botpy_logger.setLevel(logging.DEBUG if DEBUG_MODE else logging.INFO)

    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    _botpy_logging_configured = True

    return botpy_logger
