from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Camera:
    index: int
    input: str
    delta_seconds: float
    coverage: tuple[float, float]


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def dump_json(path: str | Path, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def sidecar_path(media: Path) -> Path:
    return media.with_name(media.name + ".sync.json")


def read_camera(index: int, media: Path) -> Camera:
    sidecar = sidecar_path(media)
    if sidecar.exists():
        data = load_json(sidecar)
        delta = float(data.get("delta_seconds", 0.0))
        cov = data.get("overlap_in_reference")
        if cov and len(cov) == 2:
            coverage = (float(cov[0]), float(cov[1]))
        else:
            coverage = (0.0, float("inf"))
    else:
        delta = 0.0
        coverage = (0.0, float("inf"))
    return Camera(index=index, input=str(media), delta_seconds=delta, coverage=coverage)


def normalize_decisions(
    decisions: list[dict[str, Any]],
    *,
    duration: float,
    cameras: list[Camera],
    min_shot: float = 0.75,
    tolerance: float = 1e-3,
) -> list[dict[str, Any]]:
    if not decisions:
        raise ValueError("No director decisions were supplied.")

    ordered = sorted(decisions, key=lambda row: float(row["start"]))
    out: list[dict[str, Any]] = []
    cursor = 0.0

    for i, row in enumerate(ordered):
        start = float(row["start"])
        end = float(row["end"])
        cam = int(row["cam"])

        if cam < 0 or cam >= len(cameras):
            raise ValueError(f"Decision {i}: camera index {cam} is out of range.")
        if end <= start:
            raise ValueError(f"Decision {i}: end must be greater than start.")
        if start < -tolerance:
            raise ValueError(f"Decision {i}: start cannot be negative.")
        if abs(start - cursor) > tolerance:
            raise ValueError(
                f"Decision {i}: timeline gap/overlap at {cursor:.3f}s -> {start:.3f}s."
            )
        if (end - start) < min_shot and end < duration - tolerance:
            raise ValueError(
                f"Decision {i}: shot is {(end-start):.3f}s, below min_shot {min_shot:.3f}s."
            )

        coverage_start, coverage_end = cameras[cam].coverage
        if start < coverage_start - tolerance or end > coverage_end + tolerance:
            raise ValueError(
                f"Decision {i}: cam {cam} is not available for {start:.3f}-{end:.3f}s "
                f"(coverage {coverage_start:.3f}-{coverage_end:.3f}s)."
            )

        out.append(
            {
                "cam": cam,
                "start": round(start, 3),
                "end": round(min(end, duration), 3),
                "reason": row.get("reason", ""),
                "confidence": row.get("confidence"),
            }
        )
        cursor = min(end, duration)
        if cursor >= duration - tolerance:
            break

    if abs(cursor - duration) > tolerance:
        raise ValueError(
            f"Director decisions stop at {cursor:.3f}s; expected {duration:.3f}s."
        )
    return out


def build_polysync_edl(
    manifest: dict[str, Any],
    decisions_payload: dict[str, Any],
    *,
    min_shot: float = 0.75,
    audio_source: int | None = None,
) -> dict[str, Any]:
    cameras = [
        Camera(
            index=int(c["index"]),
            input=str(c["input"]),
            delta_seconds=float(c["delta_seconds"]),
            coverage=(float(c["coverage"][0]), float(c["coverage"][1])),
        )
        for c in manifest["cameras"]
    ]
    duration = float(manifest["duration_sec"])
    decisions = normalize_decisions(
        list(decisions_payload["decisions"]),
        duration=duration,
        cameras=cameras,
        min_shot=min_shot,
    )

    if audio_source is None:
        audio_source = int(decisions_payload.get("audio_source", 0))
    if audio_source < 0 or audio_source >= len(cameras):
        raise ValueError("audio_source is out of range.")

    return {
        "_about": (
            "EDL produced by directing-multicam. Times are on the polysync "
            "reference timeline; reasons/confidence are preserved as extra fields."
        ),
        "inputs": [c.input for c in cameras],
        "deltas": [c.delta_seconds for c in cameras],
        "duration_sec": duration,
        "audio_source": audio_source,
        "coverage": [list(c.coverage) for c in cameras],
        "edl": decisions,
    }
