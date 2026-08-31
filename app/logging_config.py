"""Schlankes strukturiertes Logging (abhaengigkeitsfrei, structlog-kompatible API).

get_logger(name).info("event.name", key=value, ...) -> eine Zeile auf stdout.
"""
import logging
import sys


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        stream=sys.stdout,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


class _StructLogger:
    def __init__(self, name: str) -> None:
        self._log = logging.getLogger(name)

    @staticmethod
    def _fmt(event: str, kw: dict) -> str:
        if not kw:
            return event
        return event + " " + " ".join(f"{k}={v}" for k, v in kw.items())

    def info(self, event: str, **kw) -> None:
        self._log.info(self._fmt(event, kw))

    def warning(self, event: str, **kw) -> None:
        self._log.warning(self._fmt(event, kw))

    def error(self, event: str, **kw) -> None:
        self._log.error(self._fmt(event, kw))

    def debug(self, event: str, **kw) -> None:
        self._log.debug(self._fmt(event, kw))


def get_logger(name: str = "game-dashboard") -> _StructLogger:
    return _StructLogger(name)
