# VLM-narrated dashcam

A vision-language model watches dashcam footage and narrates what it sees, frame by frame, as a calm co-pilot — `<observation>. Advice: <action>.` Captions render as timestamp-aligned subtitles; an urgent-only TTS track speaks the moments that actually matter.

Inspired by Wayve's [LINGO-1](https://wayve.ai/thinking/lingo-natural-language-autonomous-driving/). This is a hobbyist-scope reproduction of the idea, not a research artefact.

<video src="docs/demo.mp4" controls playsinline width="100%"></video>

## What it does

A pre-recorded driving clip is sampled once per second; each frame is sent to a Qwen2-VL-7B server on a remote A100, which returns one short caption ending in an action. A React viewer plays the original video back with those captions as subtitles, on a calmer "display track" that holds for ≥2.5 s and only swaps when the advice meaningfully changes — but hard-preempts when the model escalates to `brake`, `stop`, `swerve`, or flags `collision`/`debris`. A separate offline pass synthesises an MP3 of just those urgent lines via [kokoro-onnx](https://github.com/thewh1teagle/kokoro-onnx) and ffmpeg-muxes it onto the video so the audio narration only fires on real events, not on every frame.

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

The server runs on a remote GCP A100; its canonical source in this repo is [server-mirror.py](server-mirror.py) at the root, which I copy to the VM after every change. The client and viewer run locally on an M1 MacBook Air and do no GPU work — capture, HTTP, TTS rendering, and playback only.

## Repository layout

- [server-mirror.py](server-mirror.py) — canonical FastAPI server (`POST /describe`). Lives at the repo root; the VM copy is updated by hand.
- [server/](server/) — the server's `uv` project. `bench_latency.py` is the benchmarking script; `tests/` covers prompt assembly and the multi-image downscale via `importlib.util` against `server-mirror.py`.
- [client/](client/) — the client's `uv` project. `capture.py` is the OpenCV-driven recorder that produces session JSONL; `render_tts.py` and `mux_tts.py` are the Text-to-Speech (TTS) pipeline. `lib/` holds the display-track and urgency code shared between recorder, TTS renderer, and viewer.
- [viewer/](viewer/) — React + Vite + TypeScript player. `npm run dev` to launch; pick a video and a session JSONL on the splash page.
- `data/` — videos, session JSONLs, kokoro weights. Gitignored.

## Caveats and known limitations

- **Demo footage is biased toward a collision compilation.** Single-frame VLMs cannot see motion directly but can read brake lights, hazard lights, post-impact debris, and lane intrusions — which compilations emphasise. The bias is intentional.
- **The model hallucinates.** Output is grammatical and confident even when wrong. The prompt is tuned to constrain rather than eliminate this.
