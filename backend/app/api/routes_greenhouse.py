"""
API for filling Greenhouse job application forms via Selenium.
"""

import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.executor.greenhouse_applier import apply_to_greenhouse

router = APIRouter(prefix="/api", tags=["greenhouse"])


@router.post("/greenhouse/apply")
async def greenhouse_apply(
    application_url: str = Form(..., description="Full URL of the Greenhouse job application page"),
    first_name: str = Form(..., description="Applicant first name"),
    last_name: str = Form(..., description="Applicant last name"),
    email: str = Form(..., description="Email address"),
    phone: str = Form(..., description="Phone number"),
    address: str = Form("", description="Optional address or location"),
    submit: bool = Form(False, description="If true, attempt to click the submit button after filling"),
    resume: UploadFile = File(..., description="Resume file (PDF or DOC)"),
) -> dict:
    """
    Fill a Greenhouse job application form with the given applicant data and resume.
    Uses Selenium to find common fields (name, email, phone, resume upload) and fill them.
    Returns success/failure and which fields were filled or missing.
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

        result = apply_to_greenhouse(
            application_url=application_url,
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone,
            resume_path=tmp_path,
            address=address.strip() or None,
            submit=submit,
        )
        return result
    finally:
        if tmp_path:
            Path(tmp_path).unlink(missing_ok=True)
