"""API for filling Greenhouse job application forms via Selenium."""

import json
import logging
import os
import re
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.core.config import settings
from app.executor.greenhouse_applier import apply_to_greenhouse

router = APIRouter(prefix="/api", tags=["greenhouse"])
logger = logging.getLogger(__name__)


def _compact_text(value: str, limit: int = 50000) -> str:
    return re.sub(r"\s+", " ", value or "").strip()[:limit]


def _extract_pdf_text(content: bytes) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(BytesIO(content))
        chunks: list[str] = []
        for page in reader.pages[:12]:
            text = page.extract_text() or ""
            if text.strip():
                chunks.append(text)
        return _compact_text("\n".join(chunks))
    except Exception as exc:
        logger.warning("[GREENHOUSE] PDF extraction failed: %s", exc)
        return ""


def _extract_docx_text(content: bytes) -> str:
    # DOCX is a zip; parse word/document.xml without extra dependencies.
    try:
        import zipfile

        with zipfile.ZipFile(BytesIO(content)) as zf:
            xml = zf.read("word/document.xml").decode("utf-8", errors="ignore")
        # Insert line breaks at paragraph boundaries, then strip tags.
        xml = xml.replace("</w:p>", "\n")
        text = re.sub(r"<[^>]+>", "", xml)
        return _compact_text(text)
    except Exception as exc:
        logger.warning("[GREENHOUSE] DOCX extraction failed: %s", exc)
        return ""


def _extract_resume_text(content: bytes, filename: str) -> str:
    suffix = Path(filename or "").suffix.lower()

    if suffix == ".pdf":
        extracted = _extract_pdf_text(content)
        if extracted:
            return extracted

    if suffix == ".docx":
        extracted = _extract_docx_text(content)
        if extracted:
            return extracted

    # Last resort for plain text-ish resumes or unsupported formats.
    utf = _compact_text(content.decode("utf-8", errors="ignore"))
    if len(utf) >= 100:
        return utf
    return _compact_text(content.decode("latin-1", errors="ignore"))


def _parse_json_object(text: str) -> dict[str, str]:
    cleaned = (text or "").strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end <= start:
        return {}
    try:
        obj = json.loads(cleaned[start : end + 1])
    except Exception:
        return {}
    if not isinstance(obj, dict):
        return {}
    return {str(k): str(v).strip() for k, v in obj.items() if str(v).strip()}


def _guess_name_from_filename(filename: str) -> tuple[str, str]:
    stem = Path(filename or "").stem
    cleaned = re.sub(r"[^A-Za-z]+", " ", stem).strip()
    parts = [p for p in cleaned.split() if len(p) > 1]
    if len(parts) >= 2:
        return parts[0].title(), parts[1].title()
    if len(parts) == 1:
        return parts[0].title(), ""
    return "", ""


def _fallback_profile(resume_text: str, filename: str) -> dict[str, str]:
    profile: dict[str, str] = {}

    email_match = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", resume_text)
    if email_match:
        profile["email"] = email_match.group(0)

    phone_match = re.search(r"(?:\+?1[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}", resume_text)
    if phone_match:
        profile["phone"] = phone_match.group(0)

    lines = [ln.strip() for ln in resume_text.split("\n") if ln.strip()]
    if lines:
        first_line = re.sub(r"[^A-Za-z\s'-]", "", lines[0]).strip()
        if len(first_line.split()) >= 2:
            parts = first_line.split()[:2]
            profile["first_name"] = parts[0].title()
            profile["last_name"] = parts[1].title()

    if "first_name" not in profile:
        first, last = _guess_name_from_filename(filename)
        if first:
            profile["first_name"] = first
        if last:
            profile["last_name"] = last

    return profile


def _grok_profile_from_resume(resume_text: str, filename: str) -> dict[str, str]:
    api_key = settings.grok_api_key or os.getenv("GROK_API_KEY")
    if not api_key or not resume_text:
        return {}

    payload = {
        "model": os.getenv("GROK_MODEL", "grok-beta"),
        "messages": [
            {
                "role": "system",
                "content": (
                    "Extract applicant contact basics from resume text. "
                    "Return JSON only with keys: first_name, last_name, email, phone, address. "
                    "Use empty string for unknown values."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Resume filename: {filename}\n"
                    f"Resume text:\n{resume_text}\n\n"
                    "Return exactly one JSON object."
                ),
            },
        ],
        "temperature": 0.0,
    }

    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.post(
                "https://api.x.ai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        if response.status_code >= 400:
            logger.warning("[GREENHOUSE] Grok profile extraction failed: %s", response.text[:300])
            return {}

        content = response.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        parsed = _parse_json_object(str(content))
        allowed = {"first_name", "last_name", "email", "phone", "address"}
        return {k: v for k, v in parsed.items() if k in allowed and v}
    except Exception as exc:
        logger.warning("[GREENHOUSE] Grok profile extraction error: %s", exc)
        return {}


@router.post("/greenhouse/apply")
async def greenhouse_apply(
    application_url: str = Form(..., description="Full URL of the Greenhouse job application page"),
    first_name: str = Form("", description="Applicant first name override (optional)"),
    last_name: str = Form("", description="Applicant last name override (optional)"),
    email: str = Form("", description="Email override (optional)"),
    phone: str = Form("", description="Phone override (optional)"),
    address: str = Form("", description="Address override (optional)"),
    submit: bool = Form(False, description="If true, attempt to click the submit button after filling"),
    resume: UploadFile = File(..., description="Resume file (PDF/DOC/DOCX)"),
) -> dict:
    """Fill Greenhouse application form from URL + resume, with backend inference via Grok."""
    if not resume.filename:
        raise HTTPException(status_code=400, detail="Resume file is required")

    suffix = Path(resume.filename).suffix or ".pdf"
    tmp_path: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            content = await resume.read()
            tmp.write(content)
            tmp_path = tmp.name

        resume_text = _extract_resume_text(content, resume.filename)
        grok_profile = _grok_profile_from_resume(resume_text, resume.filename)
        fallback_profile = _fallback_profile(resume_text, resume.filename)

        effective_first_name = first_name.strip() or grok_profile.get("first_name") or fallback_profile.get("first_name", "")
        effective_last_name = last_name.strip() or grok_profile.get("last_name") or fallback_profile.get("last_name", "")
        effective_email = email.strip() or grok_profile.get("email") or fallback_profile.get("email", "")
        effective_phone = phone.strip() or grok_profile.get("phone") or fallback_profile.get("phone", "")
        effective_address = address.strip() or grok_profile.get("address") or fallback_profile.get("address", "")

        logger.info(
            "[GREENHOUSE] Resume parse chars=%s inferred_fields=%s",
            len(resume_text or ""),
            {
                "first_name": bool(effective_first_name),
                "last_name": bool(effective_last_name),
                "email": bool(effective_email),
                "phone": bool(effective_phone),
                "address": bool(effective_address),
            },
        )

        result = apply_to_greenhouse(
            application_url=application_url,
            first_name=effective_first_name,
            last_name=effective_last_name,
            email=effective_email,
            phone=effective_phone,
            resume_path=tmp_path,
            address=effective_address or None,
            submit=submit,
        )
        result["inferred_profile"] = {
            "first_name": effective_first_name,
            "last_name": effective_last_name,
            "email": effective_email,
            "phone": effective_phone,
            "address": effective_address,
            "resume_text_chars": len(resume_text or ""),
        }
        return result
    finally:
        if tmp_path:
            Path(tmp_path).unlink(missing_ok=True)
