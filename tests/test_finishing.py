"""Core: la capa de finishing $0 (D-073) + economía de tomas y stills (D-074).

D-073 — lo que un colorista cobra, en ffmpeg: normalizar -> look (curva S +
saturación) -> vignette -> halation -> sharpen -> GRANO (último op visual) ->
loudnorm two-pass a -14 LUFS (spec IG/TikTok). El orden es load-bearing (node
tree de Resolve). Grano temporal uniforme sobre el film concatenado = el
unificador #1 de tomas de generaciones distintas.

D-074 — la economía de los que SÍ la ven buena: curaduría brutal en tomas
(N takes por plano de video, el humano descarta) y planos contemplativos como
STILLS con Ken Burns ($0 de video). El dinero va a menos planos x más tomas.

Lógica pura (builders de filtergraph, sin ffmpeg real) -> core (CLAUDE.md).
"""

from pathlib import Path

from pipeline.assemble import cut_times, ken_burns_filter
from pipeline.config import load_style
from pipeline.contracts import Shot
from pipeline.finish import (
    FinishConfig,
    film_look_filter,
    loudnorm_apply_filter,
    parse_loudnorm_json,
    speed_filters,
)

CONFIG_DIR = Path("config")


# --- D-073: la cadena visual en el ORDEN canónico ------------------------------

def test_film_look_filter_order_is_load_bearing():
    """balance -> look -> vignette -> halation -> sharpen -> grano (último)."""
    fc = FinishConfig()
    f = film_look_filter(fc)
    i_eq = f.index("eq=")
    i_curves = f.index("curves=")
    i_vig = f.index("vignette")
    i_hal = f.index("gblur")          # la halation es el blur + screen blend
    i_sharp = f.index("unsharp")
    i_grain = f.index("noise=")
    assert i_eq < i_curves < i_vig < i_hal < i_sharp < i_grain


def test_film_look_filter_grain_is_temporal():
    """Grano por frame (t+u), no estático: el estático parece sucio, no fílmico."""
    f = film_look_filter(FinishConfig(grain=7))
    assert "allf=t+u" in f and "alls=7" in f


def test_film_look_filter_halation_is_screen_blended_warm():
    f = film_look_filter(FinishConfig())
    assert "blend=all_mode=screen" in f
    assert "all_opacity=" in f          # sutil, no neón


def test_film_look_scales_off():
    """Cada efecto se puede apagar: el filter omite el op (estilo decide)."""
    f = film_look_filter(FinishConfig(grain=0, halation_alpha=0.0, vignette=False))
    assert "noise=" not in f and "gblur" not in f and "vignette" not in f


# --- D-073: velocidad + conformado (el fix de la flotación) ---------------------

def test_speed_filters_conform_video_and_audio():
    vf, af = speed_filters(1.15, fps=24)
    assert "setpts=PTS/1.15" in vf and "fps=24" in vf
    assert "atempo=1.15" in af


def test_speed_filters_identity_at_1x():
    vf, af = speed_filters(1.0, fps=24)
    assert "setpts" not in vf and af == ""   # solo conforma fps
    assert "fps=24" in vf


# --- D-073: loudnorm two-pass (la spec de IG: -14 LUFS / -1 dBTP) ----------------

def test_parse_loudnorm_json_extracts_measured_values():
    stderr = """
[Parsed_loudnorm_0 @ 0x1]
{
\t"input_i" : "-23.06",
\t"input_tp" : "-4.18",
\t"input_lra" : "7.50",
\t"input_thresh" : "-33.60",
\t"target_offset" : "0.30"
}
"""
    m = parse_loudnorm_json(stderr)
    assert m["input_i"] == "-23.06" and m["target_offset"] == "0.30"


def test_loudnorm_apply_filter_is_linear_two_pass():
    m = {"input_i": "-23.1", "input_tp": "-4.2", "input_lra": "7.5",
         "input_thresh": "-33.6", "target_offset": "0.3"}
    f = loudnorm_apply_filter(m, lufs=-14.0, true_peak=-1.0)
    assert "I=-14" in f and "TP=-1" in f
    assert "measured_I=-23.1" in f and "linear=true" in f


# --- D-073: el estilo declara su "film stock" ------------------------------------

def test_style_yaml_declares_finish_block():
    style = load_style(CONFIG_DIR / "styles" / "lego.yaml")
    assert style.finish is not None
    assert style.finish.lufs == -14.0          # spec IG/TikTok
    assert style.finish.grain > 0              # el unificador #1
    assert style.video_negative_prompt         # negative ESPECÍFICO de video (D-072)
    assert "slow motion" in style.video_negative_prompt


# --- D-074: stills con Ken Burns ($0 de video) -----------------------------------

def test_ken_burns_filter_zooms_over_duration():
    f = ken_burns_filter(duration_s=3.0, size=(1080, 1920), fps=24, move="push_in")
    assert "zoompan" in f
    assert "d=72" in f                  # 3s x 24fps frames
    assert "1080x1920" in f             # el formato del spec, no el del still


def test_ken_burns_pull_out_zooms_backwards():
    f_in = ken_burns_filter(3.0, (1080, 1920), 24, move="push_in")
    f_out = ken_burns_filter(3.0, (1080, 1920), 24, move="pull_out")
    assert f_in != f_out


def test_shot_media_still_is_declarable():
    shot = Shot(action="x", duration_s=3, media="still")
    assert shot.media == "still"


# --- D-074: cortes -> timestamps para impactos de audio ---------------------------

def test_cut_times_are_cumulative_excluding_end():
    assert cut_times([2.0, 3.0, 4.0]) == [2.0, 5.0]
    assert cut_times([5.0]) == []


# --- D-074: N tomas por plano + el humano elige ------------------------------------

def test_shot_takes_declarable_and_bounded():
    assert Shot(action="x", duration_s=2, takes=3).takes == 3


def test_rank_takes_prefers_gate_score():
    from pipeline.runner import rank_takes
    takes = [
        {"video_path": "a.mp4", "gate_scores": {"aesthetic": 0.4, "char_consistency": 0.4}},
        {"video_path": "b.mp4", "gate_scores": {"aesthetic": 0.9, "char_consistency": 0.8}},
        {"video_path": "c.mp4", "gate_scores": {}},
    ]
    ranked = rank_takes(takes)
    assert ranked[0]["video_path"] == "b.mp4"


def test_record_take_pick_persists_relative(tmp_path):
    import yaml
    from pipeline.project import Project
    from pipeline.studio import record_take_pick
    proj = Project(slug="t", root=tmp_path)
    (proj.cache_dir / "takes").mkdir(parents=True)
    take = proj.cache_dir / "takes" / "abc123a1.mp4"
    take.write_bytes(b"00")
    record_take_pick(proj, "s2", take)
    picks = yaml.safe_load((proj.dir / "take_picks.yaml").read_text(encoding="utf-8"))
    assert picks["s2"] == "cache/takes/abc123a1.mp4"
