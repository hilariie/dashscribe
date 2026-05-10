"""Canonical source for the VM-side FastAPI server. The user copies this file
to the VM and restarts after every change. Tests load this module directly
via `importlib.util` (see `server/tests/conftest.py`).

Schema and prompt default live here so the deployment stays single-file.
Per-request `system_prompt` override on `DescribeRequest` allows prompt
iteration without redeploying — useful when re-evaluating the prompt without
a VM round-trip.
"""

import base64
import io
import time
from contextlib import asynccontextmanager

import torch
from fastapi import FastAPI, HTTPException
from PIL import Image
from pydantic import BaseModel
from transformers import AutoProcessor, Qwen2VLForConditionalGeneration

MODEL_ID = "Qwen/Qwen2-VL-7B-Instruct"

DEFAULT_USER_PROMPT = "Describe what is happening and tell the driver what to do."

DEFAULT_SYSTEM_PROMPT = (
    "You are the driver's co-pilot, watching a dashcam in real time. "
    "Each request gives you one or more sequential frames from the same "
    "dashcam (most recent last). Your job: see what is happening and tell "
    "the driver what to do, in one short line.\n\n"
    "Output format (strict):\n"
    "  \"<observation>. Advice: <action>.\"\n"
    "One line, no preamble, under 25 words, no quotes around the line.\n\n"
    "Observation rules:\n"
    "  - Name only what is visible: vehicles, pedestrians, cyclists, "
    "brake lights, hazards, road conditions, lane position, traffic signals.\n"
    "  - When multiple frames are provided, infer motion across them: "
    "closing distance, sudden braking, lane changes, an oncoming collision. "
    "Frames are ordered oldest → newest.\n"
    "  - Do not invent details not present in the frames. If the scene is "
    "uneventful, say so plainly.\n\n"
    "Advice rules:\n"
    "  - One actionable instruction: brake, slow down, hold lane, prepare "
    "to stop, change lane, swerve, or 'maintain speed' when nothing is needed.\n"
    "  - Be decisive. Avoid hedging words like 'maybe', 'might', 'could'.\n\n"
    "No greetings, no qualifiers, no meta-commentary, no 'I see' or 'It "
    "appears'. Output the line and stop."
)

MAX_TEXT_CTX = 8
MAX_IMAGE_CTX = 4

# When more than one image is in a single request, downscale every image so
# the longest side fits this budget. Single-image requests keep native
# resolution. Trade-off: per-image fidelity vs total vision-token budget;
# multi-image at native 1080p+ OOMs on 7B bf16 on a single A100.
MULTI_IMAGE_MAX_SIDE = 640

state: dict = {}


@asynccontextmanager
async def lifespan(_: FastAPI):
    dtype = torch.bfloat16
    model = Qwen2VLForConditionalGeneration.from_pretrained(
        MODEL_ID, torch_dtype=dtype, device_map="cuda"
    ).eval()
    processor = AutoProcessor.from_pretrained(MODEL_ID)
    state["model"] = model
    state["processor"] = processor
    yield
    state.clear()


app = FastAPI(lifespan=lifespan)


class DescribeRequest(BaseModel):
    image_b64: str
    prompt: str | None = None
    system_prompt: str | None = None
    recent_commentary: list[str] = []
    recent_frames_b64: list[str] = []
    max_new_tokens: int = 60
    client_send_ts_ms: float | None = None


class DescribeResponse(BaseModel):
    text: str
    latency_ms: float           # generate() only (kept for back-compat)
    image_decode_ms: float      # base64 + JPEG + RGB convert (current frame + prior frames)
    preprocess_ms: float        # processor() + .to(device)
    output_decode_ms: float     # token slice + batch_decode
    server_total_ms: float      # full handler wall time
    server_recv_ts_ms: float    # time.time()*1000 at handler start
    server_send_ts_ms: float    # time.time()*1000 just before return
    image_width: int
    image_height: int


def build_messages(
    image_present: bool,
    recent_commentary: list[str],
    recent_frames_b64: list[str],
    system_prompt: str | None,
    user_prompt: str,
) -> list[dict]:
    """Assemble Qwen2-VL chat-template messages.

    Layout:
      - system turn: SYSTEM_PROMPT + (optional) "Recent commentary (most
        recent last)" block.
      - one user turn carrying every prior frame as image placeholders, then
        the current frame as the final image, then the user_prompt.

    Image alignment: the handler must pass `images=[*prior_frames, current]`
    in the same order as the image placeholders in the user turn.

    Server-side caps: `recent_commentary[-MAX_TEXT_CTX:]` and
    `recent_frames_b64[-MAX_IMAGE_CTX:]` so a misbehaving client cannot OOM
    the A100.
    """
    sys_text = system_prompt if system_prompt is not None else DEFAULT_SYSTEM_PROMPT

    recent_commentary = recent_commentary[-MAX_TEXT_CTX:]
    recent_frames_b64 = recent_frames_b64[-MAX_IMAGE_CTX:]

    if recent_commentary:
        sys_text += "\n\nRecent commentary (most recent last):\n" + "\n".join(
            f"- {c}" for c in recent_commentary
        )

    messages: list[dict] = [
        {"role": "system", "content": [{"type": "text", "text": sys_text}]}
    ]

    user_content: list[dict] = []
    for _ in recent_frames_b64:
        user_content.append({"type": "image"})
    if image_present:
        user_content.append({"type": "image"})
    user_content.append({"type": "text", "text": user_prompt})
    messages.append({"role": "user", "content": user_content})

    return messages


def _decode_b64_image(b64: str) -> Image.Image:
    raw = base64.b64decode(b64, validate=True)
    return Image.open(io.BytesIO(raw)).convert("RGB")


def _downscale_to_max_side(img: Image.Image, max_side: int) -> Image.Image:
    longest = max(img.width, img.height)
    if longest <= max_side:
        return img
    scale = max_side / longest
    new_w = round(img.width * scale)
    new_h = round(img.height * scale)
    return img.resize((new_w, new_h), Image.LANCZOS)


def maybe_downscale_for_multi_image(
    images: list[Image.Image], max_side: int = MULTI_IMAGE_MAX_SIDE
) -> list[Image.Image]:
    """Downscale every image when the request carries more than one.

    Single-image requests keep native resolution to preserve fine detail
    (small distant cars, brake lights, traffic-light state). Multi-image
    requests trade fidelity for the ability to perceive motion across frames
    without OOM.
    """
    if len(images) <= 1:
        return images
    return [_downscale_to_max_side(img, max_side) for img in images]


@app.get("/health")
def health():
    return {"ok": "model" in state, "cuda": torch.cuda.is_available()}


@app.post("/describe", response_model=DescribeResponse)
def describe(req: DescribeRequest):
    server_recv_ts_ms = time.time() * 1000.0
    t_handler_start = time.perf_counter()

    try:
        t0 = time.perf_counter()
        image = _decode_b64_image(req.image_b64)
        prior_frames_capped = req.recent_frames_b64[-MAX_IMAGE_CTX:]
        prior_images = [_decode_b64_image(b) for b in prior_frames_capped]
        image_decode_ms = (time.perf_counter() - t0) * 1000.0
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"invalid image: {e}")

    processor = state["processor"]
    model = state["model"]
    user_prompt = req.prompt or DEFAULT_USER_PROMPT

    messages = build_messages(
        image_present=True,
        recent_commentary=req.recent_commentary,
        recent_frames_b64=prior_frames_capped,
        system_prompt=req.system_prompt,
        user_prompt=user_prompt,
    )

    t0 = time.perf_counter()
    chat_text = processor.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    images_in_order = maybe_downscale_for_multi_image([*prior_images, image])
    inputs = processor(
        text=[chat_text], images=images_in_order, padding=True, return_tensors="pt"
    ).to(model.device)
    preprocess_ms = (time.perf_counter() - t0) * 1000.0

    torch.cuda.synchronize()
    t0 = time.perf_counter()
    with torch.inference_mode():
        out_ids = model.generate(**inputs, max_new_tokens=req.max_new_tokens, do_sample=False)
    torch.cuda.synchronize()
    latency_ms = (time.perf_counter() - t0) * 1000.0

    t0 = time.perf_counter()
    trimmed = out_ids[:, inputs.input_ids.shape[1]:]
    text = processor.batch_decode(
        trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False
    )[0].strip()
    output_decode_ms = (time.perf_counter() - t0) * 1000.0

    server_total_ms = (time.perf_counter() - t_handler_start) * 1000.0
    server_send_ts_ms = time.time() * 1000.0

    return DescribeResponse(
        text=text,
        latency_ms=round(latency_ms, 2),
        image_decode_ms=round(image_decode_ms, 2),
        preprocess_ms=round(preprocess_ms, 2),
        output_decode_ms=round(output_decode_ms, 2),
        server_total_ms=round(server_total_ms, 2),
        server_recv_ts_ms=round(server_recv_ts_ms, 2),
        server_send_ts_ms=round(server_send_ts_ms, 2),
        image_width=image.width,
        image_height=image.height,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
