"""
API for filling Greenhouse job application forms via Selenium.
Parses the uploaded resume with Grok to extract applicant details automatically.
"""

import json
import profile
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from openai import OpenAI

from app.core.config import settings
from app.executor.greenhouse_applier import apply_to_greenhouse

router = APIRouter(prefix="/api", tags=["greenhouse"])


# ---------------------------------------------------------------------------
# Resume text extraction
# ---------------------------------------------------------------------------

def _extract_text_from_pdf(path: str) -> str:
    from pdfminer.high_level import extract_text
    return extract_text(path) or ""


def _extract_text_from_docx(path: str) -> str:
    from docx import Document
    doc = Document(path)
    return "\n".join(p.text for p in doc.paragraphs)


def _extract_resume_text(path: str) -> str:
    ext = Path(path).suffix.lower()
    if ext == ".pdf":
        return _extract_text_from_pdf(path)
    if ext in (".doc", ".docx"):
        return _extract_text_from_docx(path)
    return ""


# ---------------------------------------------------------------------------
# Grok resume parsing
# ---------------------------------------------------------------------------

def _parse_resume_with_grok(resume_text: str) -> dict:
    """
    Ask Grok to extract structured applicant info and a highlight profile blurb.
    Returns a dict with first_name, last_name, email, phone, address, and profile.
    """
    client = OpenAI(
        api_key=settings.grok_api_key,
        base_url="https://api.x.ai/v1",
    )

    prompt = (
        "You are a professional resume parser. Read the resume below and return ONLY a JSON object "
        "with these exact keys:\n"
        "  first_name    – candidate's first name\n"
        "  last_name     – candidate's last name\n"
        "  email         – email address\n"
        "  phone         – phone number\n"
        "  address       – city/state or full address if present\n"
        "  profile       – a 2-3 sentence first-person blurb written as the candidate, "
        "highlighting their most impressive skills, experiences, and achievements in a way "
        "that would excite a hiring manager. Be specific — mention company names, technologies, "
        "or measurable results where available.\n\n"
        "Use empty string \"\" for any field you cannot find.\n\n"
        f"Resume:\n{resume_text[:8000]}"
    )

    response = client.chat.completions.create(
        model="grok-3-fast",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )

    raw = response.choices[0].message.content or ""
    stripped = raw.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("```")[1]
        if stripped.startswith("json"):
            stripped = stripped[4:]
        stripped = stripped.strip()

    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        data = {}

    return {
        "first_name": str(data.get("first_name", "")),
        "last_name": str(data.get("last_name", "")),
        "email": str(data.get("email", "")),
        "phone": str(data.get("phone", "")),
        "address": str(data.get("address", "")),
        "profile": str(data.get("profile", "")),
    }


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post("/greenhouse/apply")
async def greenhouse_apply(
    application_url: str = Form(..., description="Full URL of the Greenhouse job application page"),
    resume: UploadFile = File(..., description="Resume file (PDF or DOC)"),
) -> dict:
    """
    Parse the resume with Grok to extract applicant details, then fill the
    Greenhouse job application form via Selenium.
    """
    if not resume.filename:
        raise HTTPException(status_code=400, detail="Resume file is required")

    suffix = Path(resume.filename).suffix or ".pdf"
    tmp_path: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            content = await resume.read()
            tmp.write(content)
            tmp_path = tmp.name

        resume_text = _extract_resume_text(tmp_path)
        if not resume_text.strip():
            raise HTTPException(status_code=422, detail="Could not extract text from resume file.")

        applicant = _parse_resume_with_grok(resume_text)

        print("[greenhouse] Parsed applicant:")
        for key, value in applicant.items():
            print(f"  {key}: {value!r}")

        result = apply_to_greenhouse(
            application_url=application_url,
            first_name=applicant["first_name"],
            last_name=applicant["last_name"],
            email=applicant["email"],
            phone=applicant["phone"],
            resume_path=tmp_path,
            address=applicant["address"] or None,
            profile=applicant["profile"] or None,
        )

        result["parsed_applicant"] = applicant
        return result

    finally:
        if tmp_path:
            Path(tmp_path).unlink(missing_ok=True)
