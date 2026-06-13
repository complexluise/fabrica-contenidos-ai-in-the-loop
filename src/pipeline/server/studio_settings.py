"""Ajustes operativos del Studio local (D-092).

Lee y escribe `config/studio.yaml` — configuracion de OPERACION del servidor
(no secretos ni config del pipeline de video).

El modulo expone:
  - `StudioConfig`: modelo Pydantic con los campos configurables.
  - `load_studio_config(config_dir)`: lee el YAML; defaults si no existe.
  - `save_studio_config(cfg, config_dir)`: escribe el YAML preservando comentarios
    para los campos que no cambiaron (sobreescritura controlada por campo).

Por que aqui y no en .env ni en routing.yaml:
  - .env es para secretos/API keys (pydantic-settings, gitignored).
  - routing.yaml es config del pipeline de video (providers, estrategias, gate).
  - studio.yaml es config OPERATIVA del studio: cuantos jobs en paralelo, etc.
    No depende de ningun proveedor, no viaja a ningun modelo, no es un secreto.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

_STUDIO_YAML = "studio.yaml"

# Valor minimo aceptado para max_concurrency (al menos 1 job a la vez).
_MIN_CONCURRENCY = 1
# Maximo razonable (defensivo; un usuario no deberia poner 100).
_MAX_CONCURRENCY = 16


class StudioConfig(BaseModel):
    """Configuracion operativa del Studio. Valores por defecto = configuracion
    razonable sin archivo en disco."""

    max_concurrency: int = Field(
        default=2,
        ge=_MIN_CONCURRENCY,
        le=_MAX_CONCURRENCY,
        description=(
            "Numero maximo de jobs de generacion que corren en paralelo. "
            "El resto espera en cola (QUEUED)."
        ),
    )


def load_studio_config(config_dir: Path) -> StudioConfig:
    """Lee config/studio.yaml y devuelve un StudioConfig validado.

    Si el archivo no existe o falta un campo, usa el default del modelo.
    Nunca lanza excepcion: un error de lectura/parse devuelve el default.
    """
    path = Path(config_dir) / _STUDIO_YAML
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return StudioConfig(**{k: v for k, v in raw.items()
                               if k in StudioConfig.model_fields})
    except Exception:  # noqa: BLE001 — lectura defensiva; no debe romper el arranque
        return StudioConfig()


def save_studio_config(cfg: StudioConfig, config_dir: Path) -> None:
    """Escribe config/studio.yaml con los valores del StudioConfig.

    Reemplaza solo las lineas `key: value` conocidas; preserva el encabezado
    de comentarios del archivo original si existe.
    """
    path = Path(config_dir) / _STUDIO_YAML
    # Leer el archivo existente para conservar comentarios del encabezado
    if path.exists():
        existing_lines = path.read_text(encoding="utf-8").splitlines()
    else:
        existing_lines = []

    updated = cfg.model_dump()
    out_lines: list[str] = []
    seen: set[str] = set()

    for line in existing_lines:
        stripped = line.strip()
        # Detectar lineas de clave: value (no comentarios, no vacias)
        if ":" in line and not stripped.startswith("#") and stripped:
            key = line.split(":", 1)[0].strip()
            if key in updated:
                out_lines.append(f"{key}: {updated[key]}")
                seen.add(key)
                continue
        out_lines.append(line)

    # Agregar campos nuevos que no estaban en el archivo original
    for key, value in updated.items():
        if key not in seen:
            out_lines.append(f"{key}: {value}")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
