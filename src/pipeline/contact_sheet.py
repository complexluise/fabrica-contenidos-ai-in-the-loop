"""Hoja de contactos HTML para elegir candidatos (D-022, checkpoint keyframe).

Un grid por escena con los N candidatos etiquetados `escena=índice`, para que el
humano vea de un vistazo y elija con `pipeline pick`. El builder es lógica pura
(testeable); escribir/abrir es I/O.
"""

from __future__ import annotations

import webbrowser
from pathlib import Path

_CSS = """body{font-family:system-ui,sans-serif;background:#111;color:#eee;margin:24px}
h1{font-size:18px} h2{font-size:15px;margin:24px 0 8px;color:#9cf}
.grid{display:flex;flex-wrap:wrap;gap:12px}
.cand{background:#1c1c1c;border:1px solid #333;border-radius:8px;padding:8px;text-align:center}
.cand img{max-width:240px;max-height:240px;border-radius:4px;display:block}
.tag{margin-top:6px;font-family:monospace;font-size:13px;color:#fc9}
.name{font-family:monospace;font-size:11px;color:#789;word-break:break-all;max-width:240px}
.hint{color:#888;font-size:13px}"""


def build_contact_sheet(title: str, groups: dict[str, list[Path]]) -> str:
    """HTML con un grid de candidatos por escena. Cada uno etiquetado `escena=idx`."""
    parts = [
        "<!doctype html><html><head><meta charset='utf-8'>",
        f"<title>{title}</title><style>{_CSS}</style></head><body>",
        f"<h1>{title}</h1>",
        "<p class='hint'>Elige con: <code>pipeline pick &lt;proj&gt; "
        + " ".join(f"{s}=N" for s in groups) + "</code></p>",
    ]
    for scene_id, candidates in groups.items():
        # D-070: los planos cámara-actúa no tienen apertura (start=None) y un
        # destino que falló también es None — no son rutas, se omiten (antes
        # `Path(None)` tumbaba el job de animatic ENTERO por un still cosmético).
        real = [p for p in candidates if p is not None]
        if not real:
            continue
        parts.append(f"<h2>{scene_id}</h2><div class='grid'>")
        for idx, path in enumerate(real):
            p = Path(path)
            src = p.resolve().as_uri()
            parts.append(
                f"<div class='cand'><img src='{src}'>"
                f"<div class='tag'>{scene_id}={idx}</div>"
                f"<div class='name'>{p.name}</div></div>"  # nombre legible (D-026)
            )
        parts.append("</div>")
    parts.append("</body></html>")
    return "".join(parts)


def write_and_open(html: str, out_path: Path, open_browser: bool = True) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    if open_browser:
        try:
            webbrowser.open(out_path.resolve().as_uri())
        except Exception:
            pass
    return out_path
