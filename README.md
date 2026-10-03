# directing-multicam

AI-directed multicamera editing built on top of
[`polysync`](https://github.com/jianshuo/polysync).

The existing `polysync` workflow solves synchronization and rendering very well,
but its automatic angle selection is intentionally audio-energy driven.
`directing-multicam` adds a semantic **director pass**: aligned frame sampling,
camera-coverage awareness, natural-language editing styles, explainable angle
choices, validation, and a polysync-compatible EDL.

## Status

**v0.1 MVP / experimental.** The workflow is intentionally split in two:

1. deterministic media tooling handles sync, frame extraction, coverage and EDL validation;
2. Claude (or another vision-capable agent) inspects the aligned samples and authors the camera decisions.

This keeps the originals untouched and makes every edit decision reviewable.

## Install

Requirements:

- Python 3.10+
- FFmpeg / ffprobe
- `polysync`

```bash
git clone https://github.com/remco59/directing-multicam.git
cd directing-multicam
python -m pip install -e ".[dev]"
directing-multicam doctor
```

## Quick start

### 1. Sync

```bash
directing-multicam sync CAM_A.MOV CAM_B.MOV CAM_C.MOV
```

`CAM_A.MOV` is the reference. The command delegates to `polysync sync` and,
unless disabled, `polysync verify`.

### 2. Prepare aligned samples

```bash
directing-multicam prepare CAM_A.MOV CAM_B.MOV CAM_C.MOV \
  --output .directing-multicam \
  --interval 5
```

This produces a `manifest.json` and low-resolution JPEG samples aligned to the
shared reference timeline.

### 3. Let the director skill create `decisions.json`

Example:

```json
{
  "audio_source": 0,
  "decisions": [
    {
      "cam": 0,
      "start": 0.0,
      "end": 7.5,
      "reason": "Establishing wide",
      "confidence": 0.94
    },
    {
      "cam": 2,
      "start": 7.5,
      "end": 12.0,
      "reason": "Best close-up of the current action",
      "confidence": 0.89
    }
  ]
}
```

See [`SKILL.md`](./SKILL.md) for the full director workflow and style guidance.

### 4. Validate and build

```bash
directing-multicam validate .directing-multicam/manifest.json decisions.json
directing-multicam build .directing-multicam/manifest.json decisions.json --output edl.json
```

### 5. Render

```bash
directing-multicam render edl.json --output preview.mp4
```

Renderer options can be forwarded with `--passthrough`:

```bash
directing-multicam render edl.json --output preview.mp4 --passthrough \
  --width 1080 --height 1920 --fill --log slog3
```

## What the MVP understands

The actual semantic interpretation is performed by the vision-capable agent
using synchronized frame samples. The skill instructs it to reason about:

- subject/action relevance;
- close / medium / wide composition;
- reactions;
- camera repositioning or unusable imagery;
- continuity;
- shot variety;
- pacing and user-provided style instructions.

Preset guidance is included for DJ sets, aftermovies, podcasts/interviews and
general event coverage.

## Architecture

```text
camera originals
      |
      v
 polysync sync + verify
      |
      v
 *.sync.json sidecars
      |
      v
 directing-multicam prepare
      |
      +--> aligned JPEG samples
      +--> manifest.json
              |
              v
       Claude / AI director
              |
              v
        decisions.json
              |
              v
 validate + build EDL
              |
              v
 polysync render-cuts
```

## Principles

- Never modify or re-encode originals during synchronization.
- Keep `polysync` as the synchronization source of truth.
- Prefer editable/explainable decisions over an opaque one-shot render.
- Reject gaps, overlaps and angle choices outside source coverage.
- Treat automatic editing as a rough cut that remains easy to revise.

## Upstream

This project intentionally builds on ideas and tooling from:

- [`jianshuo/polysync`](https://github.com/jianshuo/polysync)
- [`wjs-syncing-multicam`](https://github.com/jianshuo/claude-skills/tree/main/wjs-syncing-multicam)
- [`wjs-editing-multicam`](https://github.com/jianshuo/claude-skills/tree/main/wjs-editing-multicam)

See [`THIRD_PARTY_NOTICES.md`](./THIRD_PARTY_NOTICES.md).
