"""Core: decision de concat robusto a clips heterogeneos (D-054).

La logica que decide si el concat por demuxer (-c copy) es seguro o hay que
conformar el video es pura (firmas de video -> uniforme? resolucion canonica?).
El ffmpeg en si se valida por smoke (CLAUDE.md: ffmpeg no se testea en unidad).
"""

from pipeline.assemble import _canonical_size, _uniform


# --- _uniform ---------------------------------------------------------------

def test_uniform_true_when_all_clips_share_signature():
    sig = ("h264", 1080, 1920)
    assert _uniform([sig, sig, sig]) is True


def test_uniform_false_when_resolution_differs():
    assert _uniform([("h264", 1080, 1920), ("h264", 1920, 1080)]) is False


def test_uniform_false_when_codec_differs():
    assert _uniform([("h264", 1080, 1920), ("vp9", 1080, 1920)]) is False


def test_uniform_conservative_when_signature_unknown():
    # ffprobe ausente (None) -> no podemos afirmar heterogeneidad: asumimos uniforme
    # para no re-encodear de mas (conserva el camino rapido de 1 provider).
    assert _uniform([None, None]) is True
    assert _uniform([("h264", 1080, 1920), None]) is True


# --- _canonical_size --------------------------------------------------------

def test_canonical_size_picks_largest_area():
    sigs = [("h264", 1080, 1920), ("h264", 720, 1280)]
    assert _canonical_size(sigs) == (1080, 1920)


def test_canonical_size_ignores_unknown_signatures():
    assert _canonical_size([None, ("h264", 1280, 720)]) == (1280, 720)


def test_canonical_size_none_when_nothing_probeable():
    assert _canonical_size([None, None]) is None
