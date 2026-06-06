"""Core Sprint 6.7: export bundle para edición humana (D-029).

Test-first del core puro: formato de tiempo SRT, numeración global, el .srt
sincronizado, y la estructura del guion (importante antes que definiciones). La
copia de archivos (`export_bundle`) es I/O y se valida con smoke.
"""

from pipeline.contracts import Scene
from pipeline.export import _ts, numbered, render_guion, srt_from_timeline
from pipeline.project import Character, ProjectSpec


def test_ts_format():
    assert _ts(0) == "00:00:00,000"
    assert _ts(5) == "00:00:05,000"
    assert _ts(65.5) == "00:01:05,500"
    assert _ts(3661.25) == "01:01:01,250"


def test_numbered_assigns_order_and_base():
    out = numbered([{"id": "s1"}, {"id": "s2"}, {"id": "s2.2"}])
    assert [(p["n"], p["base"]) for p in out] == [(1, "01_s1"), (2, "02_s2"), (3, "03_s2.2")]


def test_srt_timeline_advances_but_only_voice_emits():
    planos = [
        {"duration_s": 3, "voiceover": ""},       # sin voz: avanza, no emite
        {"duration_s": 5, "voiceover": "hola"},   # 3 -> 8
        {"duration_s": 2, "voiceover": "chau"},   # 8 -> 10
    ]
    srt = srt_from_timeline(planos)
    assert "00:00:03,000 --> 00:00:08,000\nhola" in srt
    assert "00:00:08,000 --> 00:00:10,000\nchau" in srt
    assert srt.startswith("1\n")     # numeración de cues solo cuenta los que tienen voz
    assert "\n2\n" in srt and "\n3\n" not in srt


def test_render_guion_importante_antes_de_definiciones():
    spec = ProjectSpec(slug="p", style="crochet", format="9:16", title="Mi Spot", brief="un brief")
    planos = numbered([
        {"id": "s2", "beat": "villains", "duration_s": 5, "framing": "wide",
         "voiceover": "hola", "caption": ""},
    ])
    md = render_guion(spec, planos)
    assert "Mi Spot" in md and "un brief" in md
    assert md.index("Cómo está organizado") < md.index("Definiciones")  # onboarding primero
    assert "media/01_s2.mp4" in md and "villains" in md and "hola" in md


def test_export_tolerates_old_manifest_bool_voiceover():
    # Manifests pre-D-028/D-029 guardaban voiceover como bool; no debe romper.
    planos = numbered([
        {"id": "s1", "duration_s": 5, "voiceover": True, "caption": None, "framing": None},
        {"id": "s2", "duration_s": 4, "voiceover": False},
    ])
    assert srt_from_timeline(planos) == ""  # sin texto -> sin cues, sin crash
    spec = ProjectSpec(slug="p", style="lego", format="9:16")
    md = render_guion(spec, planos)  # tampoco rompe
    assert "media/01_s1.mp4" in md


def test_render_guion_has_script_sections_in_order():
    spec = ProjectSpec(
        slug="demo_spot", style="crochet", format="9:16", title="Demo Spot", brief="Un spot.",
        characters={"rex": Character(name="rex"), "max": Character(name="max")},
        scenes=[Scene(id="s2", prompt="Sala de control con un mapa", duration_s=5, beat="villains")],
    )
    planos = numbered([
        {"id": "s2", "scene": "s2", "beat": "villains", "duration_s": 5,
         "framing": "wide de la sala", "voiceover": "Todo está listo", "caption": ""},
        {"id": "s2.2", "scene": "s2", "beat": "villains", "duration_s": 3,
         "framing": "close a la mano", "voiceover": "Perfecto", "caption": ""},
    ])
    md = render_guion(spec, planos)
    assert md.startswith("---\ntitle:")                       # frontmatter para el .docx
    assert "## Sinopsis" in md and "Un spot." in md
    assert "**rex**" in md and "**max**" in md                # personajes
    assert "### Escena s2 · villains" in md
    assert "Sala de control con un mapa" in md                # descripción de la escena (scene.prompt)
    assert '- **Plano 01** — *wide de la sala* — "Todo está listo"' in md  # libreto
    assert '- **Plano 02** — *close a la mano* — "Perfecto"' in md
    # orden: sinopsis -> guion -> desglose -> definiciones
    assert (md.index("## Sinopsis") < md.index("## Guion")
            < md.index("Desglose por plano") < md.index("Definiciones"))


def test_render_guion_falls_back_to_slug_without_title():
    spec = ProjectSpec(slug="demo_spot", style="crochet", format="9:16")
    md = render_guion(spec, numbered([{"id": "s1", "duration_s": 3}]))
    assert "demo_spot" in md
    assert "(plano base)" in md  # framing vacío -> placeholder
