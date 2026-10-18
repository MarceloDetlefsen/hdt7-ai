"""Utilidades pequeñas para mantener visibles los logs del proceso."""

from __future__ import annotations

import logging
import sys


def configure_process_logging(level: str, log_format: str = "%(message)s") -> None:
    """Configura una sola salida estándar estable para un proceso servidor."""
    root = logging.getLogger()
    if getattr(root, "_parachute_logging_configured", False):
        return
    # No se cierran handlers existentes: pueden conservar streams gestionados
    # por el runner. Se retiran y se reemplazan por un handler estable.
    for handler in list(root.handlers):
        root.removeHandler(handler)
    handler = logging.StreamHandler(sys.__stderr__)
    handler.setFormatter(logging.Formatter(log_format))
    root.addHandler(handler)
    root.setLevel(level)
    root._parachute_logging_configured = True


def repair_closed_streams() -> None:
    """Retira handlers cuyo stream fue cerrado y conserva salida visible.

    Algunos runners de terminales, pruebas o supervisores cierran el stream
    original mientras quedan tareas asíncronas terminando. El handler cerrado
    se reemplaza por un ``StreamHandler`` sobre el stderr vigente; no se
    silencian errores ni se deshabilita el logging.
    """

    loggers = [logging.getLogger()]
    loggers.extend(
        logger
        for logger in logging.Logger.manager.loggerDict.values()
        if isinstance(logger, logging.Logger)
    )
    for logger in loggers:
        for handler in list(logger.handlers):
            stream = getattr(handler, "stream", None)
            if stream is None or not getattr(stream, "closed", False):
                continue
            logger.removeHandler(handler)
            replacement = logging.StreamHandler(sys.__stderr__)
            replacement.setFormatter(handler.formatter)
            logger.addHandler(replacement)
