"""Pydantic schemas used by extraction and Selenium execution."""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, Field


# === Selenium workflow template models ===


class ParameterSpec(BaseModel):
    key: str
    description: str | None = None
    example: str | None = None
    required: bool = True
    input_type: Literal["text", "number", "date", "time", "email", "password", "select"] = "text"


class BaseStep(BaseModel):
    type: str
    description: str
    resolved_css_selector: str | None = None


class GotoStep(BaseStep):
    type: Literal["GOTO"]
    url: str


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
    value: str
    clear_first: bool = True


class SelectStep(BaseStep):
    type: Literal["SELECT"]
    target_semantic: str | None = None
    css_selector_hint: str | None = None
    value: str


class WaitStep(BaseStep):
    type: Literal["WAIT"]
    seconds: float | None = None
    until_url_contains: str | None = None
    until_selector: str | None = None
    until_text_visible: str | None = None


class ScrollStep(BaseStep):
    type: Literal["SCROLL"]
    target_selector: str | None = None
    direction: Literal["up", "down"] = "down"
    pixels: int = 300


class ScreenshotStep(BaseStep):
    type: Literal["SCREENSHOT"]
    filename: str


Step = Annotated[
    GotoStep | ClickStep | TypeStep | SelectStep | WaitStep | ScrollStep | ScreenshotStep,
    Field(discriminator="type"),
]


class WorkflowTemplate(BaseModel):
    name: str
    description: str | None = None
    start_url: str
    parameters: list[ParameterSpec] = Field(default_factory=list)
    steps: list[Step]
    category: str = "custom"
    tags: list[str] = Field(default_factory=list)
    estimated_duration_seconds: int | None = None


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


# === Semantic workflow models ===


class ActionType(str, Enum):
    GOTO = "GOTO"
    CLICK = "CLICK"
    TYPE = "TYPE"
    SELECT = "SELECT"
    WAIT = "WAIT"
    SCROLL = "SCROLL"
    HOVER = "HOVER"


class WaitCondition(str, Enum):
    URL_CHANGE = "URL_CHANGE"
    ELEMENT_VISIBLE = "ELEMENT_VISIBLE"
    ELEMENT_CLICKABLE = "ELEMENT_CLICKABLE"
    ELEMENT_PRESENT = "ELEMENT_PRESENT"
    TEXT_PRESENT = "TEXT_PRESENT"
    PAGE_LOAD = "PAGE_LOAD"


class SemanticTarget(BaseModel):
    text_hint: str | None = None
    role_hint: str | None = None
    label_hint: str | None = None
    placeholder_hint: str | None = None
    relative_hint: str | None = None
    page_context: str | None = None
    visual_description: str | None = None


class WorkflowStep(BaseModel):
    type: ActionType
    description: str
    target: SemanticTarget | None = None
    value: str | None = None
    url: str | None = None
    wait_for: WaitCondition | None = None
    wait_text: str | None = None
    timeout_seconds: float = Field(default=10.0, gt=0)


class SemanticWorkflow(BaseModel):
    name: str
    description: str
    start_url: str
    steps: list[WorkflowStep]
    extracted_at: str | None = None
    source_video: str | None = None


class ResolvedStep(BaseModel):
    original_step: WorkflowStep
    resolved_selector: str | None = None
    selector_type: Literal["css", "xpath"] | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    alternatives: list[str] = Field(default_factory=list)
