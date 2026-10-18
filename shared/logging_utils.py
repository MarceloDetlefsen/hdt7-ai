"""Utilidades pequeñas para mantener visibles los logs del proceso."""

from __future__ import annotations

import logging
import sys


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
            replacement = logging.StreamHandler(sys.stderr)
            replacement.setFormatter(handler.formatter)
            logger.addHandler(replacement)
