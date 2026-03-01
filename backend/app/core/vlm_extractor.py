from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any, Callable, Iterator, Optional, Union

from app.core.storage import UCI_FALLBACK_WORKFLOW
from app.models.schemas import WorkflowTemplate

_UI_ANALYSIS_PROMPT = """You are analyzing a single UI frame from a web task recording.
Return ONLY valid JSON with this exact shape:
{
  "frame_summary": "short summary",
  "visible_url_hint": "url or null",
  "possible_actions": [
    {
      "action_type": "CLICK|TYPE|SELECT|WAIT|SCROLL|GOTO|UNKNOWN",
      "target_hint": "element text/semantic hint or null",
      "value_hint": "typed or selected value or null",
      "confidence": 0.0
    }
  ]
}
Keep arrays short and do not include markdown fences."""

_SYNTHESIS_PROMPT_TEMPLATE = """You are given per-frame UI analyses from a web workflow recording.
Synthesize them into a reusable workflow template.
Return ONLY valid JSON matching this exact schema:
{
  "name": "workflow name",
  "description": "what it does",
  "start_url": "https://...",
  "category": "booking|form|monitoring|custom",
  "tags": ["tag"],
  "parameters": [
    {
      "key": "room",
      "description": "Room to book",
      "example": "Study Room 3A",
      "required": true,
      "input_type": "text"
    }
  ],
  "steps": [
    {"type": "GOTO", "description": "...", "url": "https://..."},
    {"type": "CLICK", "description": "...", "target_text_hint": "..."},
    {"type": "TYPE", "description": "...", "target_semantic": "...", "value": "{{param}}"},
    {"type": "WAIT", "description": "...", "seconds": 1.0}
  ]
}
Rules:
- Use parameter placeholders for variable fields: {{param_name}}
- Prefer clear descriptions and stable element hints
- Keep only meaningful steps in chronological order

Frame analyses JSON:
{frame_analyses}
"""


def _fallback_workflow() -> WorkflowTemplate:
    return UCI_FALLBACK_WORKFLOW.model_copy(deep=True)


def _get_cactus_client():
    from openai import OpenAI

    api_key = os.getenv("CACTUS_API_KEY")
    if not api_key:
        raise RuntimeError("CACTUS_API_KEY is not set")

    # Cactus can be used via an OpenAI-compatible endpoint.
    base_url = os.getenv("CACTUS_BASE_URL", "https://api.cactus.ai/v1")
    return OpenAI(api_key=api_key, base_url=base_url)


def _extract_json_from_text(text: str) -> dict[str, Any]:
    cleaned = text.strip()

    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in model output")

    return json.loads(cleaned[start : end + 1])


def _call_cactus(prompt: str, image_b64: Optional[str] = None) -> str:
    client = _get_cactus_client()
    model = os.getenv("CACTUS_MODEL", "LFM2-VL")

    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    if image_b64 is not None:
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
            }
        )

    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": content}],
        temperature=0.1,
    )

    message = response.choices[0].message.content
    if message is None:
        raise RuntimeError("Cactus returned an empty response")
    return message


def extract_frames_iter(
    video_path: str, fps_sample: int = 1, max_frames: int = 30
) -> Iterator[str]:
    """
    Yield base64-encoded JPEG frames from a video stream.
    Frames are sampled at fps_sample and capped at max_frames.
    """
    import cv2

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Unable to open video: {video_path}")

    emitted = 0
    try:
        video_fps = cap.get(cv2.CAP_PROP_FPS)
        if not video_fps or video_fps <= 0:
            video_fps = 1.0

        frame_interval = max(1, int(round(video_fps / fps_sample)))
        frame_idx = 0

        while emitted < max_frames:
            ok, frame = cap.read()
            if not ok:
                break

            if frame_idx % frame_interval == 0:
                height, width = frame.shape[:2]
                longest_side = max(height, width)
                if longest_side > 1024:
                    scale = 1024 / float(longest_side)
                    frame = cv2.resize(
                        frame,
                        (int(width * scale), int(height * scale)),
                        interpolation=cv2.INTER_AREA,
                    )

                encoded_ok, buf = cv2.imencode(
                    ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85]
                )
                if not encoded_ok:
                    raise RuntimeError("Failed to encode extracted frame")
                emitted += 1
                yield base64.b64encode(buf).decode("utf-8")

            frame_idx += 1
    finally:
        cap.release()

    if emitted == 0:
        raise ValueError("No frames extracted from video")


def _estimate_sampled_frame_count(
    video_path: str, fps_sample: int = 1, max_frames: int = 30
) -> int:
    """
    Estimate how many sampled frames we'll process for progress reporting.
    """
    import cv2

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return max_frames
    try:
        video_fps = cap.get(cv2.CAP_PROP_FPS)
        if not video_fps or video_fps <= 0:
            video_fps = 1.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if total_frames <= 0:
            return max_frames
        frame_interval = max(1, int(round(video_fps / fps_sample)))
        return max(1, min(max_frames, (total_frames + frame_interval - 1) // frame_interval))
    finally:
        cap.release()


def analyze_frame(frame_b64: str, frame_index: int, total_frames: int) -> dict[str, Any]:
    """
    Analyze a single frame via Cactus LFM2-VL using a UI analysis prompt.
    """
    prompt = (
        f"{_UI_ANALYSIS_PROMPT}\n\n"
        f"Frame index: {frame_index}\n"
        f"Total frames: {total_frames}\n"
        "Focus on actionable UI changes in this frame."
    )
    raw = _call_cactus(prompt=prompt, image_b64=frame_b64)
    return _extract_json_from_text(raw)


def extract_workflow(
    video_path: Union[str, Path],
    on_progress: Optional[Callable[[str, float], None]] = None,
) -> WorkflowTemplate:
    """
    End-to-end workflow extraction:
    1) Extract video frames (1 FPS, max 30)
    2) Analyze each frame with Cactus LFM2-VL
    3) Synthesize WorkflowTemplate JSON

    on_progress: optional callback (message, percent) for progress updates (0-100).

    On any failure, returns the hardcoded UCI fallback workflow.
    """
    def progress(message: str, percent: float) -> None:
        if on_progress:
            on_progress(message, percent)

    try:
        path = str(video_path)
        progress("Extracting frames from video", 0)
        estimated_total = _estimate_sampled_frame_count(path, fps_sample=1, max_frames=30)

        progress(f"Analyzing up to {estimated_total} frames", 5)
        frame_analyses = []
        processed = 0
        for idx, frame in enumerate(extract_frames_iter(path, fps_sample=1, max_frames=30)):
            total_for_prompt = max(estimated_total, idx + 1)
            frame_analyses.append(analyze_frame(frame, idx, total_for_prompt))
            processed = idx + 1
            # 5% -> 80% over frames
            pct = 5 + processed / max(1, estimated_total) * 75
            progress(
                f"Analyzed frame {processed} of {max(estimated_total, processed)}",
                min(80, pct),
            )

        if processed == 0:
            raise ValueError("No frames extracted from video")

        progress("Synthesizing workflow", 85)
        synthesis_prompt = _SYNTHESIS_PROMPT_TEMPLATE.format(
            frame_analyses=json.dumps(frame_analyses, ensure_ascii=True)
        )
        raw_workflow = _call_cactus(prompt=synthesis_prompt)
        workflow_json = _extract_json_from_text(raw_workflow)
        progress("Workflow extraction complete", 100)

        return WorkflowTemplate.model_validate(workflow_json)
    except Exception:
        return _fallback_workflow()
