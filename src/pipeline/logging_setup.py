"""Logging de la capa L9 (observability): progreso y errores visibles.

El código de librería (`runner`, `studio`, …) usa `logging.getLogger(__name__)`;
el CLI llama a `setup_logging()` una vez para enchufar un `RichHandler` a stderr
(stdout queda limpio para el resumen final → contrato CLI dual-audiencia, D-023).
Cada corrida adjunta además un `run.log` DEBUG dentro de su carpeta de run.
"""

from __future__ import annotations

import logging
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler

_PKG = "pipeline"  # logger raíz del paquete; los módulos cuelgan por __name__


def setup_logging(verbose: bool = False) -> None:
    """Configura el logger del paquete con salida rich a stderr. Idempotente.

    `verbose` -> DEBUG en consola (incluye tracebacks); por defecto INFO (progreso
    limpio + errores). El nivel del logger es DEBUG: el handler decide qué se ve.
    """
    logger = logging.getLogger(_PKG)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False  # no contaminar el root (httpx/anthropic son ruidosos)

    # Idempotencia: quita un handler de consola previo antes de re-añadir.
    for h in [h for h in logger.handlers if getattr(h, "_pipeline_console", False)]:
        logger.removeHandler(h)

    handler = RichHandler(
        console=Console(stderr=True),
        markup=False,          # '[s2]' es texto literal, no markup rich
        show_path=False,
        rich_tracebacks=True,
    )
    handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    handler._pipeline_console = True  # marca para la idempotencia
    logger.addHandler(handler)


def add_run_logfile(path: Path) -> logging.Handler:
    """Adjunta un FileHandler DEBUG (detalle completo + tracebacks) al logger del
    paquete y lo devuelve para quitarlo con `remove_handler` al cerrar el run."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(path, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s | %(message)s"))
    logging.getLogger(_PKG).addHandler(fh)
    return fh


def remove_handler(handler: logging.Handler) -> None:
    """Quita y cierra un handler del logger del paquete (p.ej. el `run.log`)."""
    logging.getLogger(_PKG).removeHandler(handler)
    handler.close()
