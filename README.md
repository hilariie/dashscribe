# VLM-narrated dashcam

A vision-language model watches dashcam footage and narrates what it sees, frame by frame, as a calm co-pilot — `<observation>. Advice: <action>.` Captions render as timestamp-aligned subtitles; an urgent-only TTS track speaks the moments that actually matter.

Inspired by Wayve's [LINGO-1](https://wayve.ai/thinking/lingo-natural-language-autonomous-driving/). This is a hobbyist-scope reproduction of the idea, not a research artefact.

## What it does

A pre-recorded driving clip is sampled once per second; each frame is sent to a Qwen2-VL-7B server on a remote A100, which returns one short caption ending in an action. A React viewer plays the original video back with those captions as subtitles, on a calmer "display track" that holds for ≥2.5 s and only swaps when the advice meaningfully changes — but hard-preempts when the model escalates to `brake`, `stop`, `swerve`, or flags `collision`/`debris`. A separate offline pass synthesises an MP3 of just those urgent lines via [kokoro-onnx](https://github.com/thewh1teagle/kokoro-onnx) and ffmpeg-muxes it onto the video so the audio narration only fires on real events, not on every frame.

## What's built

Four milestones, in order:

- **M1 — Scaffolding.** Per-side `uv` projects (`server/`, `client/`), stub FastAPI server, OpenCV → `POST /describe` client. Track A latency pre-flight ran in parallel and locked the cadence at 3 s (p95 = 2.77 s end-to-end on the home-Mac ↔ GCP A100 path).
- **M2 — Real VLM + locked prompt.** Stub replaced with Qwen2-VL-7B (bfloat16). System prompt locked to a co-pilot advice format. Sliding-window context (text + image) was implemented, tried, and defaulted off — single-frame outperformed multi-frame on this prompt and model. Scene-cut detection (Bhattacharyya histogram distance) clears context windows when a compilation splices to a new scenario. Per-request `system_prompt` override on the schema makes prompt iteration cheap without redeploying the VM. Motion-blindness accepted as a fundamental single-frame limitation.
- **M3 — Viewer + display track.** React + Vite + TypeScript viewer under [viewer/](viewer/). File-picker entry on `/`; the user drag-drops a video and a session JSONL and the page wires them up. Subtitles align to `capture_t_s` (the captured-frame timestamp, not the response timestamp), so the latency budget is invisible. Urgency-aware display track (calm / cautious / urgent classes) flashes amber on preempt; HUD shows current latency, frames analysed, cadence; right-hand log shows every raw caption with timestamps. Cadence dropped to 1 s for the M3 demo because the captures are pre-recorded — at 3 s a fast collision passes between samples.
- **M4 — TTS audio narration.** [client/render_tts.py](client/render_tts.py) reads a session JSONL, rebuilds the viewer's display track, filters to urgent-only blocks, synthesises each via kokoro-onnx, and writes an MP3 timed against `capture_t_s`. The viewer auto-discovers a sibling `*.tts.mp3` and plays it in sync. [client/mux_tts.py](client/mux_tts.py) is a thin ffmpeg wrapper that combines the source video with the TTS as a second audio track for downloadable MP4s.

## Architecture

```
   ┌───────────┐      POST /describe       ┌──────────────────┐
   │ client/   │  ───────────────────────▶ │ server-mirror.py │
   │ capture.py│  ◀───────────────────────  │ (FastAPI on A100)│
   └───────────┘   caption + ts split       └──────────────────┘
        │ writes
        ▼
   data/session*.jsonl  ──── render_tts.py ───▶  *.tts.mp3 ──┐
        │                                                    │
        │                                  mux_tts.py ◀──────┘
        ▼                                       │
   ┌──────────┐                                 ▼
   │ viewer/  │ ◀── /data/* via Vite ───  data/*.mp4 (narrated)
   │ React    │
   └──────────┘
```

The server runs on a remote GCP A100; its canonical source in this repo is [server-mirror.py](server-mirror.py) at the root, which the user copies to the VM after every change. The client and viewer run locally on an M1 MacBook Air and do no GPU work — capture, HTTP, TTS rendering, and playback only.

## Repository layout

- [server-mirror.py](server-mirror.py) — canonical FastAPI server (`POST /describe`). Lives at the repo root; the VM copy is updated by hand.
- [server/](server/) — the server's `uv` project. `bench_latency.py` is the Track A benchmarking script; `tests/` covers prompt assembly and the multi-image downscale via `importlib.util` against `server-mirror.py`.
- [client/](client/) — the client's `uv` project. `capture.py` is the OpenCV-driven recorder that produces session JSONL; `render_tts.py` and `mux_tts.py` are the M4 TTS pipeline. `lib/` holds the display-track and urgency code shared between recorder, TTS renderer, and viewer.
- [viewer/](viewer/) — React + Vite + TypeScript player. `npm run dev` to launch; pick a video and a session JSONL on the splash page.
- `data/` — videos, session JSONLs, kokoro weights. Gitignored.

## Caveats and known limitations

- **Demo footage is biased toward a collision compilation.** Single-frame VLMs cannot see motion directly but can read brake lights, hazard lights, post-impact debris, and lane intrusions — which compilations emphasise. The bias is intentional.
- **The model hallucinates.** Output is grammatical and confident even when wrong. The prompt is tuned to constrain rather than eliminate this.