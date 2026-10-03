import pytest

from directing_multicam.core import build_polysync_edl


def manifest():
    return {
        "duration_sec": 10.0,
        "cameras": [
            {"index": 0, "input": "a.mov", "delta_seconds": 0.0, "coverage": [0.0, 10.0]},
            {"index": 1, "input": "b.mov", "delta_seconds": 1.0, "coverage": [1.0, 10.0]},
        ],
    }


def test_build_valid_edl():
    decisions = {
        "audio_source": 0,
        "decisions": [
            {"cam": 0, "start": 0.0, "end": 2.0, "reason": "establish"},
            {"cam": 1, "start": 2.0, "end": 10.0, "reason": "closer"},
        ],
    }
    result = build_polysync_edl(manifest(), decisions)
    assert result["deltas"] == [0.0, 1.0]
    assert result["edl"][1]["reason"] == "closer"


def test_rejects_gap():
    decisions = {
        "decisions": [
            {"cam": 0, "start": 0.0, "end": 2.0},
            {"cam": 1, "start": 3.0, "end": 10.0},
        ]
    }
    with pytest.raises(ValueError, match="gap/overlap"):
        build_polysync_edl(manifest(), decisions)


def test_rejects_out_of_coverage():
    decisions = {
        "decisions": [
            {"cam": 1, "start": 0.0, "end": 10.0},
        ]
    }
    with pytest.raises(ValueError, match="not available"):
        build_polysync_edl(manifest(), decisions)


def test_rejects_short_interior_shot():
    decisions = {
        "decisions": [
            {"cam": 0, "start": 0.0, "end": 0.2},
            {"cam": 0, "start": 0.2, "end": 10.0},
        ]
    }
    with pytest.raises(ValueError, match="below min_shot"):
        build_polysync_edl(manifest(), decisions)
