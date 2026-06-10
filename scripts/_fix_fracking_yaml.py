"""One-off: corrige defectos del project.yaml del fracking (review D-050/D-044).

1. `s1.prompt` estaba en ESPAÑOL (se recompiló sin la regla de idioma) -> lo
   restaura en INGLÉS, consistente con el resto y con D-050 (el prompt de escena
   alimenta el modelo de imagen).
2. El ref del personaje y casting.yaml apuntaban a OTRO proyecto con ruta absoluta
   (`fracking_marketing_sostenible`, rompe portabilidad D-044). La MISMA cara existe
   local en este proyecto -> se repunta a `cache/cast/<hash>.png` (project-relative).
3. Sella los prompts actuales (ricos, en inglés) como en-sintonia (mark_synced),
   para que no aparezcan como "desactualizados" sin recompilarlos (los degradaría).

Correr: uv run python scripts/_fix_fracking_yaml.py
"""

from __future__ import annotations

from pathlib import Path

import yaml

from pipeline.project import Project, load_project_spec, write_spec
from pipeline.prompt_compile import mark_synced

SLUG = "desmintiendo_fracking_sostenible"

# s1 en inglés (restaurado): presentador + prop + overlay de texto + sello FALSO.
S1_PROMPT = (
    "Charming amigurumi crochet presenter character — cute knitted humanoid figure with "
    "caramel-beige yarn body, round face with black button eyes and embroidered smile, tiny "
    "dark navy knitted sweater — in tight close-up, holding in both stubby yarn arms a small "
    "crochet oil-well cross-section prop: three concentric silver-gray knitted tubes nested like "
    "a telescope with thick cream yarn filling the gaps; warm cream-mustard solid background; "
    'white bold rounded text overlay reads "El fracking es seguro si se construye bien"; a large '
    'red circular stamp "FALSO" in red yarn texture overlaps the text at a slight angle; macro '
    "photography, visible knitted stitches, soft natural side lighting; 9:16 vertical"
)


def _local_ref(project: Project, ref: Path) -> Path | None:
    """Repunta una ref cross-project a la copia LOCAL por nombre de archivo, si existe.
    Devuelve la ruta project-relative, la misma si ya es local, o None si no hay copia."""
    rp = Path(ref)
    resolved = rp if rp.is_absolute() else (project.dir / rp)
    try:
        if str(project.dir) in str(resolved.resolve()):
            return rp  # ya está dentro del proyecto
    except Exception:
        pass
    local = project.dir / "cache" / "cast" / rp.name
    return Path("cache/cast") / rp.name if local.exists() else None


def main() -> None:
    project = Project(SLUG)
    spec = load_project_spec(project.spec_path)

    # 1) refs del personaje -> local project-relative (D-044)
    for ch in spec.characters.values():
        fixed = []
        for r in ch.refs:
            local = _local_ref(project, r)
            if local is not None:
                fixed.append(local)
        ch.refs = fixed

    # 2) s1.prompt -> inglés (D-050)
    for s in spec.scenes:
        if s.id == "s1":
            s.prompt = S1_PROMPT

    # 3) sellar los prompts actuales como en-sintonia (no recompilar: son ricos)
    for s in spec.scenes:
        mark_synced(s)

    write_spec(spec, project.spec_path)

    # 4) casting.yaml -> project-relative (misma cara, copia local)
    cy = project.dir / "casting.yaml"
    if cy.exists():
        data = yaml.safe_load(cy.read_text(encoding="utf-8")) or {}
        changed = False
        for name, val in list(data.items()):
            local = _local_ref(project, Path(str(val)))
            if local is not None and str(local) != str(val):
                data[name] = str(local).replace("\\", "/")
                changed = True
        if changed:
            cy.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
                          encoding="utf-8")

    print(f"OK: s1 en inglés, refs/casting locales, {len(spec.scenes)} prompts sellados.")


if __name__ == "__main__":
    main()
