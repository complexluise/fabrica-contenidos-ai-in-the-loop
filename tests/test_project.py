"""Core: modelo de proyecto + cache content-addressed (Sprint 1.5).

TDD test-first. Estos tests se escriben ANTES de implementar project.py y
definen el contrato:
  - hashing determinista (T1.5.1)
  - Project/Run: paths e inmutabilidad de runs (T1.5.2)
  - cache lookup/store: hit/miss (T1.5.3)
"""

from pathlib import Path

import pytest

from pipeline.contracts import Scene
from pipeline.project import Character, Project, cache_key, character_refs, load_project_spec


# --- T1.5.1: hashing content-addressed -------------------------------------

def test_cache_key_is_deterministic():
    inputs = {"prompt": "ciudad LEGO", "model": "flux", "strength": 0.9}
    assert cache_key("keyframe", inputs) == cache_key("keyframe", inputs)


def test_cache_key_changes_when_input_changes():
    a = cache_key("keyframe", {"prompt": "ciudad LEGO"})
    b = cache_key("keyframe", {"prompt": "bosque LEGO"})
    assert a != b


def test_cache_key_independent_of_dict_order():
    a = cache_key("video", {"seed": 0, "provider": "kling"})
    b = cache_key("video", {"provider": "kling", "seed": 0})
    assert a == b


def test_cache_key_namespaced_by_step():
    same = {"x": 1}
    assert cache_key("keyframe", same) != cache_key("video", same)


# --- T1.5.2: Project / Run -------------------------------------------------

def test_project_resolves_paths(tmp_path):
    proj = Project(slug="lego_demo", root=tmp_path)
    assert proj.cache_dir == tmp_path / "lego_demo" / "cache"
    assert proj.runs_dir == tmp_path / "lego_demo" / "runs"


def test_new_run_creates_unique_immutable_dir(tmp_path):
    proj = Project(slug="lego_demo", root=tmp_path)
    r1 = proj.new_run()
    r2 = proj.new_run()
    assert r1.run_id != r2.run_id           # no se pisan
    assert r1.dir.exists() and r2.dir.exists()
    assert r1.dir != r2.dir


def test_run_outputs_live_inside_run_dir(tmp_path):
    proj = Project(slug="lego_demo", root=tmp_path)
    run = proj.new_run()
    assert run.report_path.parent == run.dir
    assert run.manifest_path.parent == run.dir


# --- T1.5.3: cache lookup / store ------------------------------------------

def test_cache_miss_then_hit(tmp_path):
    proj = Project(slug="lego_demo", root=tmp_path)
    key = cache_key("keyframe", {"prompt": "ciudad LEGO"})
    assert proj.cache_lookup("keyframes", key, ".png") is None      # miss
    # store un artefacto y ahora debe ser hit
    src = tmp_path / "tmp.png"
    src.write_bytes(b"fake-png")
    stored = proj.cache_store("keyframes", key, src, ".png")
    hit = proj.cache_lookup("keyframes", key, ".png")
    assert hit is not None and hit == stored
    assert hit.read_bytes() == b"fake-png"


def _scene(**kw):
    base = dict(id="s", prompt="p", duration_s=4)
    base.update(kw)
    return Scene(**base)


def test_character_refs_gathers_for_scene_characters():
    chars = {
        "alex": Character(name="alex", refs=[Path("a.png")]),
        "robin": Character(name="robin", refs=[Path("r.png")]),
    }
    refs = character_refs(_scene(characters=["alex", "robin"]), chars)
    assert refs == [Path("a.png"), Path("r.png")]


def test_character_refs_ignores_unknown_names():
    chars = {"alex": Character(name="alex", refs=[Path("a.png")])}
    assert character_refs(_scene(characters=["alex", "ghost"]), chars) == [Path("a.png")]


def test_character_refs_empty_without_characters():
    assert character_refs(_scene(), {}) == []


def test_load_project_spec_parses_characters(tmp_path):
    spec_file = tmp_path / "project.yaml"
    spec_file.write_text(
        "project: p\nstyle: lego\nscenes:\n"
        "  - id: s1\n    prompt: x\n    duration_s: 4\n    characters: [alex]\n"
        "characters:\n  alex:\n    refs: [data/alex.png]\n",
        encoding="utf-8",
    )
    spec = load_project_spec(spec_file)
    assert "alex" in spec.characters
    assert spec.characters["alex"].refs == [Path("data/alex.png")]


def test_load_project_spec_parses_character_design(tmp_path):
    spec_file = tmp_path / "project.yaml"
    spec_file.write_text(
        "project: p\nstyle: lego\nscenes:\n"
        "  - id: s1\n    prompt: x\n    duration_s: 4\n    characters: [juan]\n"
        "characters:\n  juan:\n    design:\n      prompt: hombre con barba como minifigura\n"
        "      refs: [data/juan.jpg, data/lego.jpg]\n",
        encoding="utf-8",
    )
    spec = load_project_spec(spec_file)
    juan = spec.characters["juan"]
    assert juan.design is not None
    assert juan.design.prompt == "hombre con barba como minifigura"
    assert juan.design.refs == [Path("data/juan.jpg"), Path("data/lego.jpg")]


def test_apply_casting_overrides_canonical_ref():
    from pipeline.studio import apply_casting

    chars = {"juan": Character(name="juan", refs=[])}
    apply_casting(chars, {"juan": "projects/p/cache/cast/abc.png"})
    assert chars["juan"].refs == [Path("projects/p/cache/cast/abc.png")]


def test_load_project_spec_parses_music_and_caption(tmp_path):
    spec_file = tmp_path / "project.yaml"
    spec_file.write_text(
        "project: p\nstyle: lego\nmusic: data/bg.mp3\nscenes:\n"
        "  - id: s1\n    prompt: x\n    duration_s: 4\n    caption: Hola mundo\n",
        encoding="utf-8",
    )
    spec = load_project_spec(spec_file)
    assert spec.music == Path("data/bg.mp3")
    assert spec.scenes[0].caption == "Hola mundo"


def test_load_project_spec_no_music_is_none(tmp_path):
    spec_file = tmp_path / "project.yaml"
    spec_file.write_text(
        "project: p\nstyle: lego\nscenes:\n  - id: s1\n    prompt: x\n    duration_s: 4\n",
        encoding="utf-8",
    )
    spec = load_project_spec(spec_file)
    assert spec.music is None
    assert spec.scenes[0].caption is None


def test_apply_casting_leaves_uncast_untouched():
    from pipeline.studio import apply_casting

    chars = {"ana": Character(name="ana", refs=[Path("data/ana.png")])}
    apply_casting(chars, {})  # sin casting
    assert chars["ana"].refs == [Path("data/ana.png")]


def test_sidecar_preserves_provenance(tmp_path):
    # En cache hit queremos recuperar quién generó el clip (no perder "kling" -> "cache").
    p = Project(slug="lego_demo", root=tmp_path)
    p.sidecar_store("clips", "vidkey", {"provider": "kling", "gate_passed": True})
    assert p.sidecar_lookup("clips", "vidkey") == {"provider": "kling", "gate_passed": True}


def test_sidecar_missing_returns_none(tmp_path):
    p = Project(slug="lego_demo", root=tmp_path)
    assert p.sidecar_lookup("clips", "nope") is None


def test_cache_shared_across_runs(tmp_path):
    # El cache vive a nivel proyecto, no por run: dos Project del mismo slug lo comparten.
    p1 = Project(slug="lego_demo", root=tmp_path)
    key = cache_key("video", {"provider": "kling", "seed": 0})
    src = tmp_path / "v.mp4"
    src.write_bytes(b"fake-mp4")
    p1.cache_store("clips", key, src, ".mp4")

    p2 = Project(slug="lego_demo", root=tmp_path)
    assert p2.cache_lookup("clips", key, ".mp4") is not None
