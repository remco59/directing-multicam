from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from .core import build_polysync_edl, dump_json, load_json, read_camera


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def ffprobe_duration(path: Path) -> float:
    out = subprocess.check_output(
        [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        text=True,
    ).strip()
    return float(out)


def doctor(_: argparse.Namespace) -> int:
    missing = [name for name in ("ffmpeg", "ffprobe", "polysync") if shutil.which(name) is None]
    if missing:
        print("Missing required commands: " + ", ".join(missing), file=sys.stderr)
        return 1
    print("OK: ffmpeg, ffprobe and polysync are available.")
    return 0


def sync(args: argparse.Namespace) -> int:
    reference = Path(args.reference)
    for source_value in args.sources:
        source = Path(source_value)
        cmd = ["polysync", "sync", str(reference), str(source)]
        if args.partial:
            cmd.append("--partial")
        run(cmd)
        if not args.no_verify:
            sidecar = source.with_name(source.name + ".sync.json")
            run(["polysync", "verify", str(reference), str(source), str(sidecar)])
    return 0


def _extract_frame(source: Path, local_time: float, target: Path, width: int) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-ss", f"{max(0.0, local_time):.3f}",
            "-i", str(source),
            "-frames:v", "1",
            "-vf", f"scale={width}:-2",
            "-q:v", "3",
            str(target),
        ]
    )


def prepare(args: argparse.Namespace) -> int:
    inputs = [Path(value).resolve() for value in args.inputs]
    if len(inputs) < 2:
        raise SystemExit("prepare requires at least two camera inputs.")
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)

    cameras = [read_camera(i, media) for i, media in enumerate(inputs)]
    durations = [ffprobe_duration(media) for media in inputs]

    finite_ends = []
    for cam, source_duration in zip(cameras, durations):
        coverage_end = cam.coverage[1]
        if coverage_end == float("inf"):
            coverage_end = cam.delta_seconds + source_duration
        finite_ends.append(coverage_end)

    start = max(0.0, float(args.start))
    duration = min(finite_ends)
    end = duration if args.end is None else min(duration, float(args.end))
    if end <= start:
        raise SystemExit("Selected analysis window is empty.")

    manifest_cameras: list[dict[str, Any]] = []
    for cam, source_duration in zip(cameras, durations):
        coverage = cam.coverage
        if coverage[1] == float("inf"):
            coverage = (max(0.0, cam.delta_seconds), cam.delta_seconds + source_duration)
        manifest_cameras.append(
            {
                "index": cam.index,
                "input": cam.input,
                "delta_seconds": cam.delta_seconds,
                "coverage": [round(coverage[0], 3), round(coverage[1], 3)],
            }
        )

    samples = []
    sample_index = 0
    t = start
    while t < end - 1e-9:
        row = {"reference_time": round(t, 3), "frames": []}
        for cam in manifest_cameras:
            cov_start, cov_end = cam["coverage"]
            if not (cov_start <= t < cov_end):
                row["frames"].append(None)
                continue
            local_time = t - cam["delta_seconds"]
            target = output / "frames" / f"cam_{cam['index']:02d}" / f"{sample_index:06d}.jpg"
            _extract_frame(Path(cam["input"]), local_time, target, args.width)
            row["frames"].append(str(target))
        samples.append(row)
        sample_index += 1
        t += float(args.interval)

    manifest = {
        "schema_version": 1,
        "reference_timeline": str(inputs[0]),
        "duration_sec": round(duration, 3),
        "analysis_window": [round(start, 3), round(end, 3)],
        "sample_interval_sec": float(args.interval),
        "cameras": manifest_cameras,
        "samples": samples,
        "director_contract": {
            "output": "decisions.json",
            "shape": {
                "audio_source": "integer camera index (optional; default 0)",
                "decisions": [
                    {
                        "cam": "integer camera index",
                        "start": "reference timeline seconds",
                        "end": "reference timeline seconds",
                        "reason": "short editorial reason",
                        "confidence": "0..1 optional",
                    }
                ],
            },
        },
    }
    dump_json(output / "manifest.json", manifest)
    print(output / "manifest.json")
    return 0


def build(args: argparse.Namespace) -> int:
    manifest = load_json(args.manifest)
    decisions = load_json(args.decisions)
    payload = build_polysync_edl(
        manifest,
        decisions,
        min_shot=float(args.min_shot),
        audio_source=args.audio_source,
    )
    dump_json(args.output, payload)
    print(args.output)
    return 0


def validate(args: argparse.Namespace) -> int:
    manifest = load_json(args.manifest)
    decisions = load_json(args.decisions)
    build_polysync_edl(
        manifest,
        decisions,
        min_shot=float(args.min_shot),
        audio_source=args.audio_source,
    )
    print("OK: decisions are continuous, covered and renderable.")
    return 0


def render(args: argparse.Namespace) -> int:
    cmd = ["polysync", "render-cuts", args.edl, "--out", args.output]
    cmd.extend(args.polysync_args)
    run(cmd)
    return 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="directing-multicam",
        description="AI director layer on top of polysync multicam synchronization.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    d = sub.add_parser("doctor", help="Check ffmpeg/ffprobe/polysync.")
    d.set_defaults(func=doctor)

    s = sub.add_parser("sync", help="Sync camera sources using polysync.")
    s.add_argument("reference")
    s.add_argument("sources", nargs="+")
    s.add_argument("--partial", action="store_true")
    s.add_argument("--no-verify", action="store_true")
    s.set_defaults(func=sync)

    pr = sub.add_parser("prepare", help="Sample aligned frames and write manifest.json.")
    pr.add_argument("inputs", nargs="+")
    pr.add_argument("--output", default=".directing-multicam")
    pr.add_argument("--interval", type=float, default=5.0)
    pr.add_argument("--width", type=int, default=480)
    pr.add_argument("--start", type=float, default=0.0)
    pr.add_argument("--end", type=float)
    pr.set_defaults(func=prepare)

    b = sub.add_parser("build", help="Convert AI decisions into a polysync-compatible EDL.")
    b.add_argument("manifest")
    b.add_argument("decisions")
    b.add_argument("--output", default="edl.json")
    b.add_argument("--min-shot", type=float, default=0.75)
    b.add_argument("--audio-source", type=int)
    b.set_defaults(func=build)

    v = sub.add_parser("validate", help="Validate AI decisions without writing an EDL.")
    v.add_argument("manifest")
    v.add_argument("decisions")
    v.add_argument("--min-shot", type=float, default=0.75)
    v.add_argument("--audio-source", type=int)
    v.set_defaults(func=validate)

    r = sub.add_parser("render", help="Render hard cuts with polysync render-cuts.")
    r.add_argument("edl")
    r.add_argument("--output", default="multicam.mp4")
    r.add_argument("polysync_args", nargs=argparse.REMAINDER)
    r.set_defaults(func=render)
    return p


def main() -> int:
    args = parser().parse_args()
    try:
        return int(args.func(args))
    except subprocess.CalledProcessError as exc:
        print(f"Command failed with exit code {exc.returncode}.", file=sys.stderr)
        return exc.returncode
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
