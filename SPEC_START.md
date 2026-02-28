# TeachOnce: Teach an Agent with One Video

> **Build Context**: You are an elite full-stack engineer building this for a 24-hour hackathon. Priorities: (1) stable live demo, (2) minimal moving parts, (3) clean extensible code.

---

## Vision

**Core Idea**: A user records themselves performing *any* web task once. The system watches, learns the workflow, and can replay it autonomously—forever.

**The Promise**:
- Record booking a library room → automate all future bookings
- Record filing an expense report → automate monthly submissions
- Record checking inventory across tabs → automate daily checks
- Record any repetitive web task → never do it manually again

**How It Works**:
1. User uploads a screen recording of any web workflow
2. A Vision-Language Model (VLM) analyzes the video frame-by-frame
3. System extracts a **parameterized workflow template** (what to click, what to type, in what order)
4. User reviews, adjusts parameters, and saves the workflow
5. Selenium replays the workflow with user-provided parameters
6. Human-in-the-loop handles authentication and ambiguous elements
7. System **learns** from each run—resolved selectors improve future reliability

**Why This Approach**:
- **Site-agnostic**: No browser extensions, no injected scripts—works on any website
- **Layout-resilient**: DOM/semantic matching survives UI redesigns
- **Zero training**: VLM inference only, no fine-tuning required
- **Graceful degradation**: When uncertain, ask once, then remember

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         TEACHONCE                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   ┌──────────┐    ┌──────────────┐    ┌───────────────────┐    │
│   │  Video   │───▶│  VLM Engine  │───▶│ Workflow Template │    │
│   │  Upload  │    │ (frame→JSON) │    │    (stored DB)    │    │
│   └──────────┘    └──────────────┘    └─────────┬─────────┘    │
│                                                  │               │
│                                                  ▼               │
│   ┌──────────┐    ┌──────────────┐    ┌───────────────────┐    │
│   │   Run    │◀───│   Selenium   │◀───│  Parameter Form   │    │
│   │  Logs    │    │   Executor   │    │  (user fills in)  │    │
│   └──────────┘    └──────┬───────┘    └───────────────────┘    │
│                          │                                       │
│                          ▼                                       │
│              ┌───────────────────────┐                          │
│              │  Human-in-the-Loop    │                          │
│              │  • Auth (Duo/SSO)     │                          │
│              │  • Disambiguation     │                          │
│              │  • Error Recovery     │                          │
│              └───────────────────────┘                          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Extensibility Model

### Workflow as Data

Every workflow is a **self-contained JSON document** that can be:
- Created from video (VLM extraction)
- Manually edited by users
- Shared/exported as JSON files
- Imported into other TeachOnce instances
- Versioned (future enhancement)

### Site-Agnostic Design Principles

| Principle | Implementation |
|-----------|----------------|
| **No hardcoded selectors** | All selectors come from VLM or user disambiguation |
| **No hardcoded URLs** | `start_url` is extracted from video |
| **No hardcoded auth domains** | Auth detection uses configurable patterns |
| **Generic parameter system** | Any `{{key}}` placeholder works |
| **Pluggable VLM prompts** | System prompt can be customized per workflow type |

### Adding a New Workflow Type

To support a new type of task (e.g., expense reporting, appointment booking):

1. **Record**: User records the task as usual
2. **Extract**: VLM analyzes and produces workflow JSON
3. **Review**: User adjusts parameters and step descriptions
4. **Save**: Workflow stored with metadata (name, category, tags)
5. **Run**: Same executor handles all workflow types

**No code changes required**—the system is data-driven.

### Workflow Categories (Future UI Enhancement)

```typescript
interface WorkflowMetadata {
  id: string;
  name: string;
  category: "booking" | "forms" | "data-entry" | "monitoring" | "custom";
  tags: string[];
  site_domain: string;  // e.g., "library.uci.edu"
  created_at: string;
  last_run_at: string | null;
  run_count: number;
  success_rate: number;
}
```

---

## Demo Target vs. Production Scope

### Hackathon Demo (MVP)

- **Site**: UCI Library room booking
- **Scope**: Single browser, single account
- **Goal**: End-to-end flow works reliably with human-in-the-loop

### Production Vision (Post-Hackathon)

- **Multi-workflow dashboard**: List, search, categorize saved workflows
- **Scheduling**: Run workflows on a cron schedule
- **Batch runs**: Execute same workflow with different parameter sets
- **Workflow sharing**: Export/import JSON, share with team
- **Error recovery**: Auto-retry with exponential backoff
- **Notifications**: Email/Slack on success/failure

### Non-Goals (Never Build)

- ❌ Chrome extensions or JS injection
- ❌ Mock sites or sandboxed testing
- ❌ Model training or fine-tuning
- ❌ Coordinate-based clicking (breaks on resize/zoom)
- ❌ Captcha solving (use human-in-the-loop)

### Explicitly Allowed

- ✅ One-time user confirmation for ambiguous elements
- ✅ Human-in-the-loop for any authentication
- ✅ Storing resolved selectors to improve future runs
- ✅ Manual workflow editing by users

---

## Tech Stack

| Layer | Technologies |
|-------|-------------|
| **Backend** | Python 3.11+, FastAPI, Selenium + webdriver-manager, Pydantic v2, SQLite, OpenAI SDK or Google GenAI SDK, opencv-python |
| **Frontend** | Next.js 14 (App Router), Tailwind CSS, TypeScript |

---

## Repository Structure

```
teachonce/
├── README.md
├── backend/
│   ├── requirements.txt
│   ├── .env.example
│   └── app/
│       ├── main.py
│       ├── api/
│       │   ├── routes_workflows.py      # CRUD + distill
│       │   └── routes_runs.py           # Execute + monitor
│       ├── core/
│       │   ├── config.py                # Environment + settings
│       │   ├── vlm_client.py            # Frame extraction + VLM calls
│       │   ├── vlm_prompts.py           # Customizable prompts
│       │   └── storage.py               # SQLite operations
│       ├── models/
│       │   ├── schemas.py               # Pydantic models
│       │   └── db.py                    # Database init + migrations
│       └── executor/
│           ├── selenium_runner.py       # Main execution loop
│           ├── action_strategies.py     # Element finding logic
│           ├── auth_detector.py         # Configurable auth detection
│           └── artifacts.py             # Screenshot management
└── frontend/
    ├── package.json
    ├── tailwind.config.js
    ├── tsconfig.json
    └── src/
        ├── app/
        │   ├── page.tsx                 # Home: workflow list
        │   ├── layout.tsx
        │   ├── upload/page.tsx          # New workflow from video
        │   ├── workflow/[id]/page.tsx   # View/edit workflow
        │   ├── workflow/[id]/run/page.tsx  # Start new run
        │   └── run/[id]/page.tsx        # Monitor active run
        ├── components/
        │   ├── VideoUploader.tsx
        │   ├── WorkflowCard.tsx
        │   ├── WorkflowEditor.tsx
        │   ├── WorkflowViewer.tsx
        │   ├── ParamForm.tsx
        │   ├── RunLogs.tsx
        │   └── DisambiguationModal.tsx
        └── lib/
            └── api.ts                   # API client helpers
```

---

## Database Schema

### SQLite Tables

```sql
-- Workflows: The learned task templates
CREATE TABLE workflows (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT DEFAULT 'custom',
    site_domain TEXT,
    start_url TEXT NOT NULL,
    workflow_json TEXT NOT NULL,  -- Full WorkflowTemplate as JSON
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Runs: Execution instances of workflows
CREATE TABLE runs (
    id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL REFERENCES workflows(id),
    params_json TEXT NOT NULL,
    status TEXT NOT NULL,  -- queued, running, waiting_for_auth, needs_user_disambiguation, succeeded, failed
    current_step INTEGER DEFAULT 0,
    total_steps INTEGER NOT NULL,
    disambiguation_json TEXT,  -- Populated when status = needs_user_disambiguation
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Run Logs: Step-by-step execution logs
CREATE TABLE run_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES runs(id),
    step_index INTEGER,
    level TEXT NOT NULL,  -- info, warn, error
    message TEXT NOT NULL,
    screenshot_path TEXT,
    created_at TEXT NOT NULL
);

-- Resolved Selectors: Learning from successful matches
CREATE TABLE resolved_selectors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id TEXT NOT NULL REFERENCES workflows(id),
    step_index INTEGER NOT NULL,
    css_selector TEXT NOT NULL,
    confidence REAL,
    times_used INTEGER DEFAULT 1,
    last_used_at TEXT NOT NULL,
    UNIQUE(workflow_id, step_index)
);
```

---

## Backend API Contract

### Workflow Endpoints

#### 1. List All Workflows

```http
GET /api/workflows
```

**Response:**
```json
{
  "workflows": [
    {
      "id": "wf_abc123",
      "name": "UCI Library Room Booking",
      "category": "booking",
      "site_domain": "spaces.lib.uci.edu",
      "created_at": "2024-01-15T10:00:00Z",
      "run_count": 12,
      "last_run_at": "2024-01-20T14:30:00Z",
      "success_rate": 0.92
    }
  ]
}
```

#### 2. Distill Workflow from Video

```http
POST /api/workflows/distill-video
Content-Type: multipart/form-data

file=<video.mp4 or video.webm>
workflow_hint=<optional: "booking", "form", "monitoring">
```

**Response (200):**
```json
{
  "workflow_id": "wf_abc123",
  "workflow": { /* WorkflowTemplate */ }
}
```

**Response (422):** VLM output failed validation after retry
```json
{
  "error": "Failed to parse workflow after repair attempt",
  "raw_output": "...",
  "validation_errors": ["..."]
}
```

#### 3. Get Workflow

```http
GET /api/workflows/{workflow_id}
```

**Response:**
```json
{
  "workflow_id": "wf_abc123",
  "workflow": { /* WorkflowTemplate */ },
  "metadata": {
    "created_at": "...",
    "run_count": 12,
    "success_rate": 0.92
  }
}
```

#### 4. Update Workflow

```http
PUT /api/workflows/{workflow_id}
Content-Type: application/json

{
  "name": "Updated Name",
  "workflow": { /* WorkflowTemplate */ }
}
```

Allows users to manually edit workflows after extraction.

#### 5. Delete Workflow

```http
DELETE /api/workflows/{workflow_id}
```

#### 6. Export Workflow

```http
GET /api/workflows/{workflow_id}/export
```

**Response:** Downloads workflow as `.json` file

#### 7. Import Workflow

```http
POST /api/workflows/import
Content-Type: application/json

{
  "workflow": { /* WorkflowTemplate */ }
}
```

---

### Run Endpoints

#### 1. Create Run

```http
POST /api/runs
Content-Type: application/json

{
  "workflow_id": "wf_abc123",
  "params": {
    "room": "Study Room 3A",
    "date": "2024-01-15",
    "time": "2:00 PM"
  }
}
```

**Response:**
```json
{
  "run_id": "run_xyz789"
}
```

#### 2. Read Run (Polling Endpoint)

```http
GET /api/runs/{run_id}
```

**Response:**
```json
{
  "run_id": "run_xyz789",
  "workflow_id": "wf_abc123",
  "status": "running",
  "current_step": 2,
  "total_steps": 7,
  "logs": [
    {
      "ts": "2024-01-15T10:30:00Z",
      "level": "info",
      "message": "Starting step 0: Navigate to library booking page",
      "step_index": 0
    },
    {
      "ts": "2024-01-15T10:30:02Z",
      "level": "info", 
      "message": "Step 0 completed successfully",
      "step_index": 0,
      "screenshot_path": "/artifacts/run_xyz789/step_0.png"
    }
  ],
  "disambiguation": null
}
```

**Status Values:**

| Status | Meaning | User Action |
|--------|---------|-------------|
| `queued` | Waiting for executor thread | Wait |
| `running` | Selenium actively executing | Watch logs |
| `waiting_for_auth` | Paused at login page | Complete auth, click Continue |
| `needs_user_disambiguation` | Multiple elements matched | Choose correct element |
| `succeeded` | All steps completed | 🎉 |
| `failed` | Unrecoverable error | Review logs, retry |

**Disambiguation Payload** (when `status === "needs_user_disambiguation"`):

```json
{
  "disambiguation": {
    "step_index": 3,
    "step_description": "Click the 'Next' button to proceed",
    "reason": "Multiple elements matched text='Next'",
    "screenshot_path": "/artifacts/run_xyz789/step_3_ambiguous.png",
    "candidates": [
      {
        "index": 0,
        "label": "button: 'Next' (primary action)",
        "css": "button.btn.primary",
        "confidence": 0.82,
        "location": "bottom-right of form"
      },
      {
        "index": 1,
        "label": "a: 'Next' (pagination link)", 
        "css": "a.pagination-next",
        "confidence": 0.61,
        "location": "top pagination bar"
      }
    ]
  }
}
```

#### 3. List Runs

```http
GET /api/runs?workflow_id={workflow_id}&limit=20
```

**Response:**
```json
{
  "runs": [
    {
      "run_id": "run_xyz789",
      "workflow_id": "wf_abc123",
      "status": "succeeded",
      "created_at": "2024-01-15T10:30:00Z",
      "duration_seconds": 45
    }
  ]
}
```

#### 4. Continue After Auth

```http
POST /api/runs/{run_id}/continue
```

**Response:**
```json
{ "ok": true }
```

#### 5. Choose Candidate for Disambiguation

```http
POST /api/runs/{run_id}/choose
Content-Type: application/json

{
  "step_index": 3,
  "chosen_index": 0
}
```

**Response:**
```json
{ "ok": true }
```

**Side Effects:**
- Stores chosen CSS selector in `resolved_selectors` table
- Updates workflow step with `resolved_css_selector`
- Resumes execution

#### 6. Cancel Run

```http
POST /api/runs/{run_id}/cancel
```

Stops execution gracefully.

---

### ⚠️ Critical: Non-Blocking Execution

Selenium execution **MUST NOT** block the HTTP request thread.

```python
# In routes_runs.py
import asyncio
from concurrent.futures import ThreadPoolExecutor

executor_pool = ThreadPoolExecutor(max_workers=2)

@router.post("/api/runs")
async def create_run(request: CreateRunRequest):
    run_id = generate_run_id()
    workflow = get_workflow(request.workflow_id)
    
    # Initialize run in DB
    save_run(run_id, 
             workflow_id=request.workflow_id,
             status="queued", 
             current_step=0,
             total_steps=len(workflow.steps))
    
    # Fire and forget - runs in background thread
    asyncio.get_event_loop().run_in_executor(
        executor_pool,
        lambda: selenium_runner.run(workflow, request.params, run_id)
    )
    
    return {"run_id": run_id}
```

---

## Pydantic Schemas

**File:** `backend/app/models/schemas.py`

```python
from pydantic import BaseModel, Field
from typing import Literal, Annotated
from enum import Enum

# === Parameters (Generic - works for any workflow) ===

class ParameterSpec(BaseModel):
    """
    Defines a user-fillable parameter in the workflow.
    
    Examples:
    - {"key": "room", "description": "Room to book", "example": "Study Room 3A"}
    - {"key": "amount", "description": "Expense amount in USD", "example": "125.50"}
    - {"key": "date", "description": "Appointment date", "example": "2024-01-15"}
    """
    key: str = Field(..., pattern=r"^[a-z][a-z0-9_]*$", 
                     description="Parameter name (lowercase, underscores)")
    description: str = Field(..., description="Human-readable description")
    example: str = Field(..., description="Example value")
    required: bool = Field(default=True)
    input_type: Literal["text", "date", "time", "number", "select"] = "text"
    options: list[str] | None = None  # For select type

# === Steps (Discriminated Union) ===

class BaseStep(BaseModel):
    """Common fields for all step types."""
    description: str
    resolved_css_selector: str | None = None  # Learned from successful runs

class GotoStep(BaseStep):
    type: Literal["GOTO"]
    url: str  # May contain {{param}} placeholders

class ClickStep(BaseStep):
    type: Literal["CLICK"]
    target_text_hint: str | None = None
    target_semantic: str | None = None
    css_selector_hint: str | None = None

class TypeStep(BaseStep):
    type: Literal["TYPE"]
    target_text_hint: str | None = None
    target_semantic: str | None = None
    css_selector_hint: str | None = None
    value: str  # May contain {{param}} placeholders
    clear_first: bool = True  # Clear existing text before typing

class SelectStep(BaseStep):
    """For dropdown/select elements."""
    type: Literal["SELECT"]
    target_semantic: str | None = None
    css_selector_hint: str | None = None
    value: str  # Option value or text, may contain {{param}}

class WaitStep(BaseStep):
    type: Literal["WAIT"]
    seconds: float | None = None
    until_url_contains: str | None = None
    until_selector: str | None = None
    until_text_visible: str | None = None

class ScrollStep(BaseStep):
    """Scroll to element or position."""
    type: Literal["SCROLL"]
    target_selector: str | None = None
    direction: Literal["up", "down"] = "down"
    pixels: int = 300

class ScreenshotStep(BaseStep):
    """Capture screenshot (useful for verification)."""
    type: Literal["SCREENSHOT"]
    filename: str

Step = Annotated[
    GotoStep | ClickStep | TypeStep | SelectStep | WaitStep | ScrollStep | ScreenshotStep,
    Field(discriminator="type")
]

# === Workflow Template ===

class WorkflowTemplate(BaseModel):
    """
    Complete workflow definition.
    This is site-agnostic - same schema works for any web task.
    """
    name: str
    description: str | None = None
    start_url: str
    parameters: list[ParameterSpec]
    steps: list[Step]
    
    # Metadata (not used in execution)
    category: str = "custom"
    tags: list[str] = []
    estimated_duration_seconds: int | None = None
    
    class Config:
        extra = "forbid"  # Reject unexpected fields

# === Run State ===

class RunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_FOR_AUTH = "waiting_for_auth"
    NEEDS_USER_DISAMBIGUATION = "needs_user_disambiguation"
    SUCCEEDED = "succeeded"
    FAILED = "failed"

class LogEntry(BaseModel):
    ts: str
    level: Literal["info", "warn", "error"]
    message: str
    step_index: int | None = None
    screenshot_path: str | None = None

class DisambiguationCandidate(BaseModel):
    index: int
    label: str
    css: str
    confidence: float
    location: str | None = None

class DisambiguationPayload(BaseModel):
    step_index: int
    step_description: str
    reason: str
    screenshot_path: str
    candidates: list[DisambiguationCandidate]

class RunState(BaseModel):
    run_id: str
    workflow_id: str
    status: RunStatus
    current_step: int
    total_steps: int
    logs: list[LogEntry]
    disambiguation: DisambiguationPayload | None = None
```

---

## VLM Distillation Logic

**File:** `backend/app/core/vlm_client.py`

### Frame Extraction

```python
import cv2
import base64
from pathlib import Path

def extract_frames(video_path: str, max_frames: int = 60, fps_sample: int = 1) -> list[str]:
    """
    Extract frames from video at specified FPS, resize, return as base64.
    Works with any video format supported by OpenCV.
    """
    cap = cv2.VideoCapture(video_path)
    video_fps = cap.get(cv2.CAP_PROP_FPS)
    frame_interval = max(1, int(video_fps / fps_sample))
    
    frames = []
    frame_count = 0
    
    while len(frames) < max_frames:
        ret, frame = cap.read()
        if not ret:
            break
        
        if frame_count % frame_interval == 0:
            # Resize longest side to 1024px for efficient API calls
            h, w = frame.shape[:2]
            scale = 1024 / max(h, w)
            if scale < 1:
                frame = cv2.resize(frame, (int(w * scale), int(h * scale)))
            
            # Encode as base64 JPEG
            _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            frames.append(base64.b64encode(buffer).decode('utf-8'))
        
        frame_count += 1
    
    cap.release()
    return frames
```

### VLM Prompts (Customizable)

**File:** `backend/app/core/vlm_prompts.py`

```python
# Base prompt - works for any web workflow
BASE_SYSTEM_PROMPT = """You are an expert at analyzing screen recordings of web workflows and converting them into executable automation scripts.

Your task: Watch the provided video frames (in chronological order) and extract the exact sequence of user actions.

ANALYSIS RULES:
1. Identify EVERY user action: clicks, text input, selections, scrolls, navigation
2. For variable data (names, dates, amounts, IDs), use parameter placeholders: {{parameter_name}}
3. Use semantic descriptions for elements (e.g., "the blue Submit button", "email input field")
4. Include CSS selector hints when identifiable from the UI
5. Add WAIT steps after actions that trigger page loads, modals, or AJAX
6. Preserve the exact order of actions
7. Group related actions logically

PARAMETER NAMING:
- Use lowercase with underscores: {{first_name}}, {{appointment_date}}
- Be descriptive: {{room_number}} not {{r}}
- Extract ALL variable values as parameters

OUTPUT: Return ONLY valid JSON matching the schema below. No markdown fences, no explanation."""

# Workflow-type-specific hints (optional enhancement)
WORKFLOW_HINTS = {
    "booking": """
Additional context: This appears to be a booking/reservation workflow.
Common parameters to look for: date, time, room/resource name, duration, attendee info.
Watch for: calendar pickers, time slot selectors, confirmation buttons.""",

    "form": """
Additional context: This appears to be a form submission workflow.
Common parameters: name fields, email, phone, address components, dropdown selections.
Watch for: validation messages, required field indicators, multi-step forms.""",

    "monitoring": """
Additional context: This appears to be a data monitoring/checking workflow.
Focus on: navigation between pages/tabs, data extraction points, refresh patterns.
May not need many parameters - focus on the navigation sequence.""",
}

def get_vlm_prompt(workflow_hint: str | None = None) -> str:
    """Assemble the full prompt with optional workflow-specific hints."""
    prompt = BASE_SYSTEM_PROMPT
    
    if workflow_hint and workflow_hint in WORKFLOW_HINTS:
        prompt += f"\n\n{WORKFLOW_HINTS[workflow_hint]}"
    
    prompt += f"""

REQUIRED OUTPUT SCHEMA:
{{
  "name": "descriptive workflow name",
  "description": "what this workflow accomplishes",
  "start_url": "the URL where the workflow begins",
  "category": "booking|form|monitoring|custom",
  "parameters": [
    {{"key": "param_name", "description": "what this parameter is for", "example": "example value"}}
  ],
  "steps": [
    {{"type": "GOTO", "description": "...", "url": "https://..."}},
    {{"type": "CLICK", "description": "...", "target_text_hint": "...", "css_selector_hint": "..."}},
    {{"type": "TYPE", "description": "...", "target_semantic": "...", "value": "{{{{param}}}}"}},
    {{"type": "WAIT", "description": "...", "until_selector": "...", "seconds": 2}},
    {{"type": "SELECT", "description": "...", "css_selector_hint": "...", "value": "{{{{param}}}}"}}
  ]
}}"""
    
    return prompt
```

### Two-Pass Repair Loop

```python
from pydantic import ValidationError
from .vlm_prompts import get_vlm_prompt
from ..models.schemas import WorkflowTemplate

class WorkflowParsingError(Exception):
    def __init__(self, raw_output: str, repaired_output: str | None, errors: list):
        self.raw_output = raw_output
        self.repaired_output = repaired_output
        self.errors = errors
        super().__init__("Failed to parse workflow after repair attempt")

async def distill_video_to_workflow(
    video_path: str, 
    workflow_hint: str | None = None
) -> WorkflowTemplate:
    """
    Extract workflow from video with automatic repair on failure.
    """
    frames = extract_frames(video_path)
    system_prompt = get_vlm_prompt(workflow_hint)
    
    # First attempt
    raw_output = await call_vlm(frames, system_prompt)
    
    # Try to parse
    try:
        # Clean potential markdown fences
        cleaned = raw_output.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```")[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
        
        workflow = WorkflowTemplate.model_validate_json(cleaned)
        return workflow
        
    except ValidationError as e:
        # Repair attempt with error context
        repair_prompt = f"""The previous output had validation errors. Fix them and return valid JSON.

ERRORS:
{e.errors()}

ORIGINAL OUTPUT:
{raw_output}

Return ONLY the corrected JSON, no explanation."""
        
        repaired_output = await call_vlm(frames, repair_prompt)
        
        try:
            cleaned = repaired_output.strip().strip("`")
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
            workflow = WorkflowTemplate.model_validate_json(cleaned)
            return workflow
            
        except ValidationError as e2:
            raise WorkflowParsingError(
                raw_output=raw_output,
                repaired_output=repaired_output,
                errors=e2.errors()
            )

async def call_vlm(frames: list[str], prompt: str) -> str:
    """Call VLM provider (OpenAI or Gemini) with frames."""
    from .config import settings
    
    if settings.VLM_PROVIDER == "openai":
        return await _call_openai(frames, prompt)
    elif settings.VLM_PROVIDER == "gemini":
        return await _call_gemini(frames, prompt)
    else:
        raise ValueError(f"Unknown VLM provider: {settings.VLM_PROVIDER}")

async def _call_openai(frames: list[str], prompt: str) -> str:
    from openai import AsyncOpenAI
    from .config import settings
    
    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    
    # Build message with frames as images
    content = [{"type": "text", "text": prompt}]
    for i, frame in enumerate(frames):
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{frame}",
                "detail": "low"  # Use low detail for efficiency
            }
        })
    
    response = await client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=[{"role": "user", "content": content}],
        max_tokens=4096,
        temperature=0.1  # Low temperature for consistent output
    )
    
    return response.choices[0].message.content

async def _call_gemini(frames: list[str], prompt: str) -> str:
    import google.generativeai as genai
    from .config import settings
    
    genai.configure(api_key=settings.GEMINI_API_KEY)
    model = genai.GenerativeModel(settings.GEMINI_MODEL)
    
    # Build parts with frames
    parts = [prompt]
    for frame in frames:
        parts.append({
            "mime_type": "image/jpeg",
            "data": frame
        })
    
    response = await model.generate_content_async(parts)
    return response.text
```

### Configuration

**File:** `backend/app/core/config.py`

```python
from pydantic_settings import BaseSettings
from typing import Literal

class Settings(BaseSettings):
    # VLM Configuration
    VLM_PROVIDER: Literal["openai", "gemini"] = "openai"
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o"
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-1.5-pro"
    
    # Database
    DATABASE_URL: str = "sqlite:///./teachonce.db"
    
    # Artifacts
    ARTIFACTS_DIR: str = "./artifacts"
    
    # Selenium
    SELENIUM_HEADLESS: bool = False  # False for demo visibility
    SELENIUM_TIMEOUT: int = 15
    
    # Auth Detection (extensible)
    AUTH_URL_PATTERNS: list[str] = [
        "webauth.uci.edu",
        "login.uci.edu",
        "shib.uci.edu",
        "sso.",
        "auth.",
        "login.",
        "signin.",
        "accounts.google.com",
        "login.microsoftonline.com"
    ]
    
    AUTH_TITLE_KEYWORDS: list[str] = [
        "login",
        "sign in",
        "log in",
        "authenticate",
        "duo",
        "sso",
        "verification"
    ]
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
```

---

## Selenium Execution

**File:** `backend/app/executor/selenium_runner.py`

### Core Runner (Site-Agnostic)

```python
import re
import time
from pathlib import Path
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

from ..core.config import settings
from ..core.storage import update_run, add_log, save_resolved_selector
from ..models.schemas import WorkflowTemplate, RunStatus, Step
from .action_strategies import find_element, execute_action
from .auth_detector import is_auth_page

class DisambiguationNeeded(Exception):
    def __init__(self, step_index: int, step: Step, candidates: list):
        self.step_index = step_index
        self.step = step
        self.candidates = candidates

class SeleniumRunner:
    def __init__(self, run_id: str, workflow_id: str):
        self.run_id = run_id
        self.workflow_id = workflow_id
        self.driver = None
        self.artifacts_dir = Path(settings.ARTIFACTS_DIR) / run_id
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
    
    def run(self, workflow: WorkflowTemplate, params: dict):
        """
        Main execution loop with checkpointing.
        Site-agnostic: works for any workflow.
        """
        try:
            self._setup_driver()
            self._update_status(RunStatus.RUNNING)
            
            # Resume from checkpoint if needed
            start_step = self._get_checkpoint()
            
            for i in range(start_step, len(workflow.steps)):
                step = workflow.steps[i]
                self._log(f"Step {i}: {step.description}", step_index=i)
                
                # Substitute parameters in step
                step = self._substitute_params(step, params)
                
                # Execute the step
                self._execute_step(i, step)
                
                # Check for auth redirect after any navigation
                if self._check_auth_pause(i):
                    return  # Will resume via /continue
                
                # Checkpoint after success
                self._save_checkpoint(i + 1)
                self._take_screenshot(f"step_{i}.png")
                self._log(f"Step {i} completed", step_index=i, level="info")
            
            self._update_status(RunStatus.SUCCEEDED)
            self._log("Workflow completed successfully!")
            
        except DisambiguationNeeded as e:
            self._handle_disambiguation(e)
        except Exception as e:
            self._log(f"Error: {str(e)}", level="error")
            self._take_screenshot("error.png")
            self._update_status(RunStatus.FAILED, error=str(e))
        finally:
            if self.driver:
                self.driver.quit()
    
    def _substitute_params(self, step: Step, params: dict) -> Step:
        """
        Replace {{key}} placeholders with actual values.
        Works on all string fields in the step.
        """
        step_dict = step.model_dump()
        
        def replace_placeholders(value):
            if isinstance(value, str):
                for key, val in params.items():
                    value = value.replace(f"{{{{{key}}}}}", str(val))
                return value
            elif isinstance(value, dict):
                return {k: replace_placeholders(v) for k, v in value.items()}
            elif isinstance(value, list):
                return [replace_placeholders(v) for v in value]
            return value
        
        replaced = replace_placeholders(step_dict)
        return type(step).model_validate(replaced)
    
    def _execute_step(self, index: int, step: Step):
        """Execute a single step based on its type."""
        execute_action(self.driver, step, self.artifacts_dir)
    
    def _check_auth_pause(self, step_index: int) -> bool:
        """Check if we hit an auth page and need to pause."""
        if is_auth_page(self.driver):
            self._log("Authentication required - pausing for user", step_index=step_index)
            self._take_screenshot(f"step_{step_index}_auth.png")
            self._update_status(RunStatus.WAITING_FOR_AUTH)
            self._save_checkpoint(step_index)  # Resume from this step after auth
            return True
        return False
    
    def _handle_disambiguation(self, e: DisambiguationNeeded):
        """Pause and request user choice."""
        screenshot_path = self._take_screenshot(f"step_{e.step_index}_ambiguous.png")
        
        disambiguation = {
            "step_index": e.step_index,
            "step_description": e.step.description,
            "reason": f"Multiple elements matched for: {e.step.description}",
            "screenshot_path": f"/artifacts/{self.run_id}/step_{e.step_index}_ambiguous.png",
            "candidates": e.candidates
        }
        
        self._update_status(
            RunStatus.NEEDS_USER_DISAMBIGUATION, 
            disambiguation=disambiguation
        )
        self._save_checkpoint(e.step_index)
    
    def _setup_driver(self):
        """Initialize Chrome (headed for demo, configurable for production)."""
        options = webdriver.ChromeOptions()
        
        if settings.SELENIUM_HEADLESS:
            options.add_argument("--headless=new")
        
        options.add_argument("--start-maximized")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=options)
        self.driver.implicitly_wait(5)
    
    def _take_screenshot(self, filename: str) -> str:
        """Capture screenshot and return path."""
        path = self.artifacts_dir / filename
        self.driver.save_screenshot(str(path))
        return str(path)
    
    def _log(self, message: str, step_index: int = None, level: str = "info"):
        """Write log entry to database."""
        add_log(self.run_id, level, message, step_index)
    
    def _update_status(self, status: RunStatus, error: str = None, disambiguation: dict = None):
        """Update run status in database."""
        update_run(self.run_id, status=status, error=error, disambiguation=disambiguation)
    
    def _save_checkpoint(self, next_step: int):
        """Persist progress for resume."""
        update_run(self.run_id, current_step=next_step)
    
    def _get_checkpoint(self) -> int:
        """Get step to resume from."""
        from ..core.storage import get_run
        run = get_run(self.run_id)
        return run.current_step if run else 0
```

### Auth Detection (Configurable)

**File:** `backend/app/executor/auth_detector.py`

```python
from ..core.config import settings

def is_auth_page(driver) -> bool:
    """
    Detect if we're on an authentication page.
    Uses configurable patterns from settings.
    """
    current_url = driver.current_url.lower()
    page_title = driver.title.lower()
    
    # Check URL patterns
    for pattern in settings.AUTH_URL_PATTERNS:
        if pattern.lower() in current_url:
            return True
    
    # Check title keywords
    for keyword in settings.AUTH_TITLE_KEYWORDS:
        if keyword.lower() in page_title:
            return True
    
    return False
```

### Element Strategies (Site-Agnostic)

**File:** `backend/app/executor/action_strategies.py`

```python
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from ..core.config import settings
from ..models.schemas import Step, GotoStep, ClickStep, TypeStep, SelectStep, WaitStep, ScrollStep

class ElementNotFound(Exception):
    pass

class DisambiguationNeeded(Exception):
    def __init__(self, candidates: list):
        self.candidates = candidates

def execute_action(driver, step: Step, artifacts_dir):
    """Execute any step type."""
    if step.type == "GOTO":
        driver.get(step.url)
        _wait_for_page_load(driver)
        
    elif step.type == "CLICK":
        element = find_element(driver, step)
        _scroll_into_view(driver, element)
        element.click()
        _wait_for_page_stability(driver)
        
    elif step.type == "TYPE":
        element = find_element(driver, step)
        _scroll_into_view(driver, element)
        if step.clear_first:
            element.clear()
        element.send_keys(step.value)
        
    elif step.type == "SELECT":
        element = find_element(driver, step)
        select = Select(element)
        try:
            select.select_by_visible_text(step.value)
        except NoSuchElementException:
            select.select_by_value(step.value)
            
    elif step.type == "WAIT":
        _execute_wait(driver, step)
        
    elif step.type == "SCROLL":
        if step.target_selector:
            element = driver.find_element(By.CSS_SELECTOR, step.target_selector)
            _scroll_into_view(driver, element)
        else:
            scroll_amount = step.pixels if step.direction == "down" else -step.pixels
            driver.execute_script(f"window.scrollBy(0, {scroll_amount})")
            
    elif step.type == "SCREENSHOT":
        path = artifacts_dir / step.filename
        driver.save_screenshot(str(path))

def find_element(driver, step):
    """
    Find element using priority-based strategies.
    Searches main document and all iframes.
    """
    timeout = settings.SELENIUM_TIMEOUT
    
    # Priority 1: Use resolved selector if available (learned from previous runs)
    if step.resolved_css_selector:
        try:
            return WebDriverWait(driver, timeout).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, step.resolved_css_selector))
            )
        except TimeoutException:
            pass  # Fall through to other strategies
    
    # Priority 2: CSS selector hint from VLM
    if step.css_selector_hint:
        try:
            return WebDriverWait(driver, timeout).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, step.css_selector_hint))
            )
        except TimeoutException:
            pass
    
    # Priority 3: Search all frames for matching elements
    candidates = _search_all_frames(driver, step)
    
    if len(candidates) == 0:
        raise ElementNotFound(f"No element found for: {step.description}")
    
    if len(candidates) == 1:
        # Switch back to the frame containing the element
        _switch_to_frame(driver, candidates[0]["frame_path"])
        return candidates[0]["element"]
    
    # Multiple candidates - need disambiguation
    raise DisambiguationNeeded([
        {
            "index": i,
            "label": _describe_element(c["element"]),
            "css": _generate_unique_selector(c["element"]),
            "confidence": c["confidence"],
            "location": _describe_location(driver, c["element"])
        }
        for i, c in enumerate(candidates[:5])  # Limit to top 5
    ])

def _search_all_frames(driver, step) -> list:
    """Search main document and all iframes."""
    all_candidates = []
    
    # Search main document
    driver.switch_to.default_content()
    candidates = _find_in_current_frame(driver, step)
    for c in candidates:
        c["frame_path"] = []
    all_candidates.extend(candidates)
    
    # Search iframes recursively
    _search_iframes_recursive(driver, step, [], all_candidates)
    
    # Return to main document
    driver.switch_to.default_content()
    
    # Sort by confidence
    all_candidates.sort(key=lambda x: x["confidence"], reverse=True)
    return all_candidates

def _search_iframes_recursive(driver, step, frame_path: list, all_candidates: list, depth: int = 0):
    """Recursively search iframes up to depth 3."""
    if depth > 3:
        return
    
    try:
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        for i, iframe in enumerate(iframes):
            try:
                driver.switch_to.frame(iframe)
                new_path = frame_path + [i]
                
                # Search this frame
                candidates = _find_in_current_frame(driver, step)
                for c in candidates:
                    c["frame_path"] = new_path
                all_candidates.extend(candidates)
                
                # Recurse into nested iframes
                _search_iframes_recursive(driver, step, new_path, all_candidates, depth + 1)
                
                # Go back to parent
                driver.switch_to.parent_frame()
            except Exception:
                driver.switch_to.parent_frame()
    except Exception:
        pass

def _find_in_current_frame(driver, step) -> list:
    """Find matching elements in current frame context."""
    candidates = []
    
    # Strategy A: Exact text match
    if hasattr(step, 'target_text_hint') and step.target_text_hint:
        xpath = f"//*[normalize-space(text())='{step.target_text_hint}']"
        for el in driver.find_elements(By.XPATH, xpath):
            if el.is_displayed():
                candidates.append({"element": el, "confidence": 0.95, "match": "exact_text"})
    
    # Strategy B: Partial text
    if hasattr(step, 'target_text_hint') and step.target_text_hint and not candidates:
        xpath = f"//*[contains(normalize-space(text()), '{step.target_text_hint}')]"
        for el in driver.find_elements(By.XPATH, xpath):
            if el.is_displayed():
                candidates.append({"element": el, "confidence": 0.75, "match": "partial_text"})
    
    # Strategy C: aria-label
    if hasattr(step, 'target_semantic') and step.target_semantic:
        for attr in ['aria-label', 'title', 'placeholder', 'name']:
            xpath = f"//*[contains(@{attr}, '{step.target_semantic}')]"
            for el in driver.find_elements(By.XPATH, xpath):
                if el.is_displayed():
                    candidates.append({"element": el, "confidence": 0.70, "match": f"{attr}_match"})
    
    # Strategy D: Role heuristics
    if step.type == "CLICK":
        for el in driver.find_elements(By.CSS_SELECTOR, "button, a, [role='button'], input[type='submit'], input[type='button']"):
            if el.is_displayed():
                text_hint = getattr(step, 'target_text_hint', '') or ''
                if text_hint.lower() in (el.text or '').lower():
                    candidates.append({"element": el, "confidence": 0.60, "match": "role_heuristic"})
    
    elif step.type == "TYPE":
        for el in driver.find_elements(By.CSS_SELECTOR, "input[type='text'], input[type='email'], input[type='search'], input:not([type]), textarea"):
            if el.is_displayed():
                candidates.append({"element": el, "confidence": 0.50, "match": "input_heuristic"})
    
    return candidates

def _switch_to_frame(driver, frame_path: list):
    """Switch to the frame at the given path."""
    driver.switch_to.default_content()
    for frame_index in frame_path:
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        driver.switch_to.frame(iframes[frame_index])

def _execute_wait(driver, step: WaitStep):
    """Execute WAIT with preference for explicit conditions."""
    timeout = 30
    
    if step.until_selector:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, step.until_selector))
        )
    elif step.until_url_contains:
        WebDriverWait(driver, timeout).until(
            EC.url_contains(step.until_url_contains)
        )
    elif step.until_text_visible:
        WebDriverWait(driver, timeout).until(
            EC.text_to_be_present_in_element((By.TAG_NAME, "body"), step.until_text_visible)
        )
    elif step.seconds:
        time.sleep(step.seconds)
    else:
        time.sleep(0.5)  # Brief default pause

def _wait_for_page_load(driver):
    """Wait for page to fully load."""
    WebDriverWait(driver, 30).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )

def _wait_for_page_stability(driver):
    """Brief wait after click to allow for page updates."""
    time.sleep(0.3)
    try:
        WebDriverWait(driver, 5).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
    except TimeoutException:
        pass

def _scroll_into_view(driver, element):
    """Scroll element into view before interaction."""
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
    time.sleep(0.2)

def _describe_element(element) -> str:
    """Generate human-readable description of element."""
    tag = element.tag_name
    text = (element.text or "")[:50]
    element_type = element.get_attribute("type") or ""
    
    if text:
        return f"{tag}: '{text}'"
    elif element_type:
        return f"{tag}[type={element_type}]"
    else:
        return tag

def _generate_unique_selector(element) -> str:
    """Generate a CSS selector for the element."""
    # Try ID first
    el_id = element.get_attribute("id")
    if el_id:
        return f"#{el_id}"
    
    # Try unique class combination
    classes = element.get_attribute("class")
    if classes:
        class_selector = "." + ".".join(classes.split())
        return f"{element.tag_name}{class_selector}"
    
    # Fallback to tag + attributes
    name = element.get_attribute("name")
    if name:
        return f"{element.tag_name}[name='{name}']"
    
    return element.tag_name

def _describe_location(driver, element) -> str:
    """Describe where element is on the page."""
    try:
        rect = element.rect
        viewport = driver.execute_script("return {width: window.innerWidth, height: window.innerHeight}")
        
        x_pos = "left" if rect["x"] < viewport["width"] / 3 else "right" if rect["x"] > 2 * viewport["width"] / 3 else "center"
        y_pos = "top" if rect["y"] < viewport["height"] / 3 else "bottom" if rect["y"] > 2 * viewport["height"] / 3 else "middle"
        
        return f"{y_pos}-{x_pos}"
    except Exception:
        return "unknown"
```

---

## Frontend Implementation

### Home Page - Workflow Library

```tsx
// src/app/page.tsx
"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { WorkflowCard } from "@/components/WorkflowCard";

interface WorkflowSummary {
  id: string;
  name: string;
  category: string;
  site_domain: string;
  run_count: number;
  success_rate: number;
  last_run_at: string | null;
}

export default function HomePage() {
  const [workflows, setWorkflows] = useState<WorkflowSummary[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("http://localhost:8000/api/workflows")
      .then(res => res.json())
      .then(data => {
        setWorkflows(data.workflows);
        setLoading(false);
      });
  }, []);

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b">
        <div className="max-w-6xl mx-auto px-6 py-4 flex justify-between items-center">
          <h1 className="text-2xl font-bold">TeachOnce</h1>
          <Link 
            href="/upload"
            className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700"
          >
            + New Workflow
          </Link>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-6 py-8">
        <h2 className="text-xl font-semibold mb-6">Your Workflows</h2>
        
        {loading ? (
          <div>Loading...</div>
        ) : workflows.length === 0 ? (
          <div className="text-center py-12 bg-white rounded-lg border-2 border-dashed">
            <p className="text-gray-500 mb-4">No workflows yet</p>
            <Link 
              href="/upload"
              className="text-blue-600 hover:underline"
            >
              Upload your first video →
            </Link>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {workflows.map(workflow => (
              <WorkflowCard key={workflow.id} workflow={workflow} />
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
```

### Workflow Card Component

```tsx
// src/components/WorkflowCard.tsx
import Link from "next/link";

interface Props {
  workflow: {
    id: string;
    name: string;
    category: string;
    site_domain: string;
    run_count: number;
    success_rate: number;
    last_run_at: string | null;
  };
}

export function WorkflowCard({ workflow }: Props) {
  return (
    <Link href={`/workflow/${workflow.id}`}>
      <div className="bg-white p-4 rounded-lg border hover:shadow-md transition-shadow">
        <div className="flex justify-between items-start mb-2">
          <h3 className="font-semibold">{workflow.name}</h3>
          <span className="text-xs bg-gray-100 px-2 py-1 rounded">
            {workflow.category}
          </span>
        </div>
        
        <p className="text-sm text-gray-500 mb-3">{workflow.site_domain}</p>
        
        <div className="flex justify-between text-sm">
          <span>{workflow.run_count} runs</span>
          <span className={workflow.success_rate > 0.8 ? "text-green-600" : "text-yellow-600"}>
            {Math.round(workflow.success_rate * 100)}% success
          </span>
        </div>
      </div>
    </Link>
  );
}
```

### Workflow Editor (For Manual Adjustments)

```tsx
// src/components/WorkflowEditor.tsx
"use client";
import { useState } from "react";

interface Props {
  workflow: any;
  onSave: (updated: any) => void;
}

export function WorkflowEditor({ workflow, onSave }: Props) {
  const [editing, setEditing] = useState(false);
  const [json, setJson] = useState(JSON.stringify(workflow, null, 2));
  const [error, setError] = useState<string | null>(null);

  const handleSave = () => {
    try {
      const parsed = JSON.parse(json);
      onSave(parsed);
      setEditing(false);
      setError(null);
    } catch (e) {
      setError("Invalid JSON");
    }
  };

  if (!editing) {
    return (
      <div>
        <div className="flex justify-between items-center mb-2">
          <h3 className="font-semibold">Workflow Definition</h3>
          <button 
            onClick={() => setEditing(true)}
            className="text-sm text-blue-600 hover:underline"
          >
            Edit
          </button>
        </div>
        <pre className="bg-gray-900 text-gray-100 p-4 rounded-lg overflow-auto text-sm max-h-96">
          {JSON.stringify(workflow, null, 2)}
        </pre>
      </div>
    );
  }

  return (
    <div>
      <div className="flex justify-between items-center mb-2">
        <h3 className="font-semibold">Edit Workflow</h3>
        <div className="space-x-2">
          <button onClick={() => setEditing(false)} className="text-sm text-gray-600">
            Cancel
          </button>
          <button onClick={handleSave} className="text-sm text-blue-600 font-medium">
            Save
          </button>
        </div>
      </div>
      
      {error && <p className="text-red-600 text-sm mb-2">{error}</p>}
      
      <textarea
        value={json}
        onChange={e => setJson(e.target.value)}
        className="w-full h-96 font-mono text-sm p-4 border rounded-lg"
      />
    </div>
  );
}
```

---

## Build Order

### Phase 1: Backend Foundation (Hours 1-3)

1. Initialize FastAPI project structure
2. Define all Pydantic schemas (`schemas.py`)
3. Set up SQLite with all tables (`db.py`)
4. Implement storage layer (`storage.py`)
5. Create config with env vars (`config.py`)

### Phase 2: VLM Integration (Hours 3-6)

6. Implement frame extraction with OpenCV
7. Create VLM prompts system (`vlm_prompts.py`)
8. Build VLM client with two-pass repair
9. Wire up `POST /api/workflows/distill-video`
10. Test with a sample video

### Phase 3: Selenium Execution (Hours 6-10)

11. Implement auth detector (configurable patterns)
12. Build action strategies with iframe search
13. Create selenium runner with checkpointing
14. Implement disambiguation flow
15. Wire up all `/api/runs/*` endpoints

### Phase 4: Frontend (Hours 10-16)

16. Create Next.js project with Tailwind
17. Build home page (workflow library)
18. Build upload page with video uploader
19. Build workflow view/edit page
20. Build run page with polling
21. Add disambiguation modal
22. Add auth continue flow

### Phase 5: Polish (Hours 16-20)

23. Error handling throughout
24. Loading states and feedback
25. Workflow export/import
26. Run history view
27. README with exact commands

### Phase 6: Demo Prep (Hours 20-24)

28. End-to-end test with UCI booking
29. Record backup demo video
30. Prepare talking points
31. Edge case testing

---

## Success Criteria

### Demo Checklist

- [ ] User uploads UCI booking video → workflow extracted correctly
- [ ] Workflow shows all steps with parameter placeholders
- [ ] User can edit workflow JSON if needed
- [ ] User fills in room/date/time parameters
- [ ] Selenium opens visible Chrome window
- [ ] System pauses at Duo login → user authenticates → clicks Continue
- [ ] If multiple elements match → disambiguation modal appears → user picks
- [ ] System remembers choice for future runs
- [ ] Booking completes or reaches confirmation
- [ ] Logs and screenshots visible throughout
- [ ] No crashes, hangs, or silent failures

### Extensibility Checklist

- [ ] Workflow JSON is self-contained and portable
- [ ] Auth detection works for common SSO providers
- [ ] Element strategies work across different site structures
- [ ] Parameters work for any placeholder pattern
- [ ] VLM prompt can be customized per workflow type
- [ ] Resolved selectors are saved and reused

---

## README Template

```markdown
# TeachOnce

**Teach an agent with one video. Record yourself once, automate forever.**

## What It Does

1. Upload a screen recording of any web task
2. AI extracts the workflow into a reusable template
3. Fill in parameters (dates, names, etc.)
4. Watch Selenium replay your actions automatically

## Quick Start

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your API key

# Initialize database
python -c "from app.models.db import init_db; init_db()"

# Run
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000

## Environment Variables

```env
# Required: Choose one VLM provider
VLM_PROVIDER=openai
OPENAI_API_KEY=sk-...

# OR
VLM_PROVIDER=gemini
GEMINI_API_KEY=...

# Optional
SELENIUM_HEADLESS=false
SELENIUM_TIMEOUT=15
```

## Demo: UCI Library Room Booking

1. Go to http://localhost:3000/upload
2. Upload a recording of yourself booking a room at UCI Library
3. Review the extracted workflow
4. Click "Start Run" and fill in your preferred room/date/time
5. Complete Duo authentication when the browser pauses
6. Click "Continue" in the web app
7. Watch the automation complete your booking

## Adding New Workflows

TeachOnce is designed to learn **any** web task:

1. **Record**: Screen record yourself doing the task
2. **Upload**: Drop the video in the upload page
3. **Review**: Check the extracted steps and parameters
4. **Adjust**: Edit the workflow JSON if needed
5. **Run**: Execute with different parameters each time

## Architecture

- **VLM (GPT-4o/Gemini)**: Extracts workflow from video frames
- **Selenium**: Replays workflow in real Chrome browser
- **Human-in-the-Loop**: Handles auth and ambiguous elements
- **Learning**: Stores resolved selectors for smoother future runs

## Troubleshooting

**"No element found" error**: The site's HTML may have changed. Try re-recording or manually updating the workflow's CSS selectors.

**Auth loop**: Make sure to complete ALL auth steps (including Duo) before clicking Continue.

**Wrong element clicked**: When disambiguation appears, look at the screenshot carefully to pick the right element.
```

---

## Requirements Files

### `backend/requirements.txt`

```
fastapi==0.109.0
uvicorn[standard]==0.27.0
python-multipart==0.0.6
pydantic==2.5.3
pydantic-settings==2.1.0
opencv-python-headless==4.9.0.80
selenium==4.17.2
webdriver-manager==4.0.1
openai==1.10.0
google-generativeai==0.3.2
aiosqlite==0.19.0
python-dotenv==1.0.0
```

### `frontend/package.json`

```json
{
  "name": "teachonce-frontend",
  "version": "0.1.0",
  "scripts": {
    "dev": "next dev --port 3000",
    "build": "next build",
    "start": "next start"
  },
  "dependencies": {
    "next": "14.1.0",
    "react": "18.2.0",
    "react-dom": "18.2.0"
  },
  "devDependencies": {
    "@types/node": "20.11.0",
    "@types/react": "18.2.48",
    "autoprefixer": "10.4.17",
    "postcss": "8.4.33",
    "tailwindcss": "3.4.1",
    "typescript": "5.3.3"
  }
}
```