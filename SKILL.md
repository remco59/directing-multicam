---
name: directing-multicam
description: Use when the user has two or more recordings of the same event and wants an AI-directed multicamera edit that considers visual relevance, framing, reactions, action, pacing, and audio context instead of switching only on microphone energy. Builds on polysync sidecars and rendering; produces an editable, validated EDL before rendering.
---

# directing-multicam

Create a semantic multicamera rough cut on top of `polysync`.

`polysync` remains the source of truth for synchronization. This skill does **not** reimplement waveform matching, drift estimation, or media rendering. It adds the missing director layer: inspect aligned visual samples, reason about what each camera shows, choose the best angle over time, explain every cut, validate the result, and then hand the EDL back to `polysync`.

## Requirements

```bash
python -m pip install -e .
directing-multicam doctor
```

System requirements: `ffmpeg`, `ffprobe`, and `polysync`.

## Workflow

### 1. Sync the originals

Pick the longest / most continuous camera as reference.

```bash
directing-multicam sync CAM_A.MOV CAM_B.MOV CAM_C.MOV
```

This delegates to `polysync sync` and `polysync verify`. Original files are untouched. Keep every `.sync.json` next to its source.

If a source only covers part of the event:

```bash
directing-multicam sync CAM_A.MOV PHONE_CLIP.mp4 --partial
```

### 2. Prepare aligned visual evidence

```bash
directing-multicam prepare CAM_A.MOV CAM_B.MOV CAM_C.MOV \
  --output .directing-multicam \
  --interval 5
```

This writes:

```text
.directing-multicam/
  manifest.json
  frames/
    cam_00/
    cam_01/
    cam_02/
```

Frames are sampled on the **reference timeline**. The manifest records sync deltas and coverage, so a missing frame means that camera did not cover that moment.

For a long event, work in windows first:

```bash
directing-multicam prepare CAM_A.MOV CAM_B.MOV CAM_C.MOV \
  --start 600 --end 900 --interval 2
```

### 3. Direct the edit

Read `manifest.json`, then inspect the sampled frames across cameras at the same reference times.

Create `decisions.json`:

```json
{
  "audio_source": 0,
  "decisions": [
    {
      "cam": 0,
      "start": 0.0,
      "end": 6.2,
      "reason": "Stable establishing wide while the scene is introduced",
      "confidence": 0.91
    },
    {
      "cam": 1,
      "start": 6.2,
      "end": 9.4,
      "reason": "Closer subject framing and visible interaction",
      "confidence": 0.88
    }
  ]
}
```

Every decision must be contiguous. Times are reference-timeline seconds. Never schedule a camera outside its `coverage`.

### Director priorities

Use these in order:

1. **Usability** — reject black, obscured, wildly shaky, badly out-of-focus, or repositioning shots.
2. **Subject relevance** — show the person/action that currently matters.
3. **Composition** — prefer intentional framing over accidental framing.
4. **Reaction value** — reactions can be more informative than the primary action immediately after a beat, joke, reveal, drop, or applause.
5. **Continuity** — avoid visually jarring switches between near-identical framings or cuts that interrupt an important motion.
6. **Pacing** — vary shot length with event energy. Do not switch merely because another camera is available.
7. **Variety** — use wides to establish/reset geography; mediums for interaction; close shots for detail/emotion.

Do **not** optimize for maximum cut count.

### Style presets

#### `dj-set`

- Hold longer during mixes/builds.
- Prefer DJ detail when the performer is actively mixing or interacting.
- Use crowd/reaction angles around recognizable energy peaks and drops.
- Use wide shots to re-establish the room after runs of close shots.
- Avoid cutting away in the middle of a clear gesture unless the receiving shot completes the action.

#### `aftermovie`

- Faster pacing is acceptable.
- Prioritize peaks, reactions, movement, lighting changes and visually distinctive shots.
- Still reject camera repositioning and accidental footage.
- Use rhythmic patterns, but do not make every cut mechanically beat-aligned.

#### `podcast` / `interview`

- Prefer the active speaker.
- Insert listener reactions when visually meaningful.
- Use the wide as an intentional reset/cutaway, not because its mic is loud.
- Avoid ping-pong cutting on every short interjection.

#### `event`

- Start with spatial context.
- Track whichever subject/action is currently narratively important.
- Use reaction/cutaway shots to bridge transitions.
- Prefer continuity over frantic switching.

Natural-language instructions from the user override these presets.

### 4. Validate

```bash
directing-multicam validate .directing-multicam/manifest.json decisions.json \
  --min-shot 0.75
```

Validation rejects:
- gaps or overlaps;
- invalid camera indices;
- shots outside camera coverage;
- accidental ultra-short shots;
- timelines that do not reach the event duration.

If working on only a sub-window, first create decisions for that selected window and then expand/merge them into a full-event decision list before final validation.

### 5. Build polysync EDL

```bash
directing-multicam build .directing-multicam/manifest.json decisions.json \
  --output edl.json
```

The resulting file preserves `reason` and `confidence` as extra fields while retaining the fields `polysync render-cuts` needs.

### 6. Render preview

```bash
directing-multicam render edl.json --output preview.mp4
```

Extra renderer flags can be passed after `--`, for example:

```bash
directing-multicam render edl.json --output preview.mp4 -- \
  --width 1080 --height 1920 --fill --log slog3
```

## Iteration loop

Treat the EDL as the editable source of truth.

When the user says something like:

- "too many crowd shots between 12:00 and 15:00";
- "stay on the DJ longer before drops";
- "camera 2 is shaky in the second half";
- "make this section calmer";

change only the affected decisions, validate again, and rebuild the EDL. Do not resync or re-render unrelated sections.

## Why this differs from `wjs-editing-multicam`

`wjs-editing-multicam` / `polysync edit` is intentionally audio-energy driven. This skill uses those tools as the media infrastructure but moves camera selection into a semantic director pass that can understand framing, action, reactions, visual quality and style instructions.

## Safety / data handling

- Never overwrite source footage.
- Never modify `.sync.json` manually unless repairing a known sync issue.
- Keep analysis proxies/frames disposable.
- Prefer an editable EDL before a final render.
