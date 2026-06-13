"""Smoke de contrato de las skills (D-023).

Una skill (`skills/<nombre>/SKILL.md`) es prosa que codifica conocimiento del CLI.
Si un subcomando o flag que la skill menciona desaparece, la skill queda obsoleta
**sin que nada falle** -> el mismo "Known drift" que el spec de referencia documenta
(docs/notas/idea-organic-illustration-pipeline.md §10/F10).

Contramedida: cada SKILL.md declara al final un bloque

    <!-- smoke
    pipeline <subcomando> --help
    -->

con las invocaciones mínimas que menciona. Este test las ejecuta en modo no-op
(solo `--help`, sin llamar a modelos ni gastar). Si un subcomando referenciado ya
no existe, el CLI sale != 0 y el test **grita** en vez de que la skill se pudra
callada. Es el equivalente, para la capa de skills, del aviso de drift F10.
"""

from __future__ import annotations

import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO_ROOT / "skills"

# Captura cada bloque <!-- smoke ... -->; nos quedamos con las líneas `pipeline ...`.
_SMOKE_BLOCK = re.compile(r"<!--\s*smoke\b(.*?)-->", re.DOTALL)


def _smoke_commands(skill_md: Path) -> list[str]:
    """Extrae las invocaciones `pipeline ...` de los bloques smoke de un SKILL.md."""
    text = skill_md.read_text(encoding="utf-8")
    commands: list[str] = []
    for block in _SMOKE_BLOCK.findall(text):
        for line in block.splitlines():
            line = line.strip()
            if line.startswith("pipeline "):
                commands.append(line)
    return commands


def _skill_files() -> list[Path]:
    return sorted(SKILLS_DIR.glob("*/SKILL.md"))


def _run(command: str) -> subprocess.CompletedProcess:
    """Ejecuta `pipeline ...` como `python -m pipeline.cli ...` (sin install previo)."""
    args = shlex.split(command)
    assert args[0] == "pipeline"
    return subprocess.run(
        [sys.executable, "-m", "pipeline.cli", *args[1:]],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_skills_dir_has_skills() -> None:
    """Hay al menos una skill; si no, el glob de abajo no probaría nada."""
    assert _skill_files(), "No se encontró ninguna skills/*/SKILL.md"


@pytest.mark.parametrize("skill_md", _skill_files(), ids=lambda p: p.parent.name)
def test_skill_declares_smoke(skill_md: Path) -> None:
    """Toda skill DEBE declarar un bloque smoke con >=1 invocación del CLI."""
    assert _smoke_commands(skill_md), (
        f"{skill_md.parent.name} no declara un bloque '<!-- smoke ... -->' con "
        "invocaciones 'pipeline ...'. Sin él, el drift del CLI no se detecta (D-023)."
    )


@pytest.mark.parametrize(
    "command",
    [c for f in _skill_files() for c in _smoke_commands(f)],
)
def test_smoke_command_contract(command: str) -> None:
    """Cada invocación smoke debe existir en el CLI (sale 0). Detecta drift de contrato."""
    proc = _run(command)
    assert proc.returncode == 0, (
        f"`{command}` salió {proc.returncode}: el subcomando/flag que una skill "
        f"menciona ya no existe en el CLI (drift, D-023).\n{proc.stderr or proc.stdout}"
    )
