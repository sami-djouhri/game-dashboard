"""Schlankes strukturiertes Logging (abhaengigkeitsfrei, structlog-kompatible API).

get_logger(name).info("event.name", key=value, ...) -> eine Zeile auf stdout.
"""
import logging
import sys


class _OhneDauerpruefung(logging.Filter):
    """Blendet die Zugriffszeilen der Selbstueberwachung aus.

    Der Healthcheck fragt alle 30 s `/health`, und das Statusfenster holt alle 20 s
    den Arbiter-Status. Beides ist Herzschlag, kein Ereignis, und beides landete in
    derselben Ausgabe wie echte Vorgaenge: ueber 7000 Zeilen am Tag, in denen eine
    Fehlermeldung praktisch unauffindbar ist. Wer wissen will, ob die Pruefung laeuft,
    liest den Health-Zustand des Containers, nicht sein Log.

    Ausgeblendet wird nur der Erfolgsfall. Ein Healthcheck, der fehlschlaegt, hat
    keinen 200er im Text und bleibt sichtbar; httpx meldet Fehler ueber eine eigene
    Ausnahme, nicht ueber diese Zeile.
    """

    _STILL = ("GET /health HTTP/1.1\" 200", "/status \"HTTP/1.0 200 OK",
              "/status \"HTTP/1.1 200 OK")

    def filter(self, record: logging.LogRecord) -> bool:
        text = record.getMessage()
        return not any(muster in text for muster in self._STILL)


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        stream=sys.stdout,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    stiller = _OhneDauerpruefung()
    for name in ("uvicorn.access", "httpx"):
        logging.getLogger(name).addFilter(stiller)


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
