from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any, Optional, Union

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


def extract_frames(video_path: str, fps_sample: int = 1, max_frames: int = 30) -> list[str]:
    """
    Extract frames from a video at 1 FPS (default), capped at max_frames.
    Returns base64-encoded JPEG frames.
    """
    import cv2

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Unable to open video: {video_path}")

    frames: list[str] = []
    try:
        video_fps = cap.get(cv2.CAP_PROP_FPS)
        if not video_fps or video_fps <= 0:
            video_fps = 1.0

        frame_interval = max(1, int(round(video_fps / fps_sample)))
        frame_idx = 0

        while len(frames) < max_frames:
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
                frames.append(base64.b64encode(buf).decode("utf-8"))

            frame_idx += 1
    finally:
        cap.release()

    if not frames:
        raise ValueError("No frames extracted from video")
    return frames


def analyze_frame(
    frame_b64: str,
    frame_index: int,
    total_frames: int,
    on_output: Optional[Any] = None,
) -> dict[str, Any]:
    """
    Analyze a single frame via Cactus LFM2-VL using a UI analysis prompt.
    Calls on_output(text) with the raw model response if provided.
    """
    prompt = (
        f"{_UI_ANALYSIS_PROMPT}\n\n"
        f"Frame index: {frame_index}\n"
        f"Total frames: {total_frames}\n"
        "Focus on actionable UI changes in this frame."
    )
    raw = _call_cactus(prompt=prompt, image_b64=frame_b64)
    if on_output:
        try:
            on_output(raw)
        except Exception:
            pass
    return _extract_json_from_text(raw)


def extract_workflow(
    video_path: Union[str, Path],
    on_progress: Optional[Any] = None,
    on_output: Optional[Any] = None,
) -> WorkflowTemplate:
    """
    End-to-end workflow extraction:
    1) Extract video frames (1 FPS, max 30)
    2) Analyze each frame with Cactus LFM2-VL
    3) Synthesize WorkflowTemplate JSON

    on_progress(step, pct) is called at key milestones.
    on_output(text) is called with the raw model response after each parse.
    On any failure, returns the hardcoded UCI fallback workflow.
    """
    def progress(step: str, pct: float) -> None:
        if on_progress:
            try:
                on_progress(step, pct)
            except Exception:
                pass

    def emit(text: str) -> None:
        if on_output:
            try:
                on_output(text)
            except Exception:
                pass

    try:
        progress("Extracting frames from video", 5)
        path = str(video_path)
        frames = extract_frames(path, fps_sample=1, max_frames=30)
        progress(f"Extracted {len(frames)} frames", 20)

        frame_analyses: list[dict[str, Any]] = []
        for idx, frame in enumerate(frames):
            emit(f"\n--- Frame {idx + 1} / {len(frames)} ---\n")
            analysis = analyze_frame(frame, idx, len(frames), on_output=emit)
            frame_analyses.append(analysis)
            pct = 20 + int((idx + 1) / len(frames) * 50)
            progress(f"Analyzed frame {idx + 1} of {len(frames)}", pct)

        progress("Synthesizing workflow", 75)
        emit("\n--- Synthesis ---\n")
        synthesis_prompt = _SYNTHESIS_PROMPT_TEMPLATE.format(
            frame_analyses=json.dumps(frame_analyses, ensure_ascii=True)
        )
        raw_workflow = _call_cactus(prompt=synthesis_prompt)
        emit(raw_workflow)
        progress("Parsing workflow JSON", 90)
        workflow_json = _extract_json_from_text(raw_workflow)
        result = WorkflowTemplate.model_validate(workflow_json)
        progress("Complete", 100)
        return result
    except Exception as exc:
        emit(f"\n[Extraction error: {exc}]\n[Falling back to default workflow]\n")
        progress("Complete", 100)
        return _fallback_workflow()
