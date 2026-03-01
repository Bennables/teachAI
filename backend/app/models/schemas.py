"""Pydantic schemas used by extraction and Selenium execution."""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, Field


# === Selenium workflow template models ===


class ParameterSpec(BaseModel):
    key: str
    description: Optional[str] = None
    example: Optional[str] = None
    required: bool = True
    input_type: Literal["text", "number", "date", "time", "email", "password", "select"] = "text"


class BaseStep(BaseModel):
    type: str
    description: str
    resolved_css_selector: Optional[str] = None


class GotoStep(BaseStep):
    type: Literal["GOTO"]
    url: str


class ClickStep(BaseStep):
    type: Literal["CLICK"]
    target_text_hint: Optional[str] = None
    target_semantic: Optional[str] = None
    css_selector_hint: Optional[str] = None


class TypeStep(BaseStep):
    type: Literal["TYPE"]
    target_text_hint: Optional[str] = None
    target_semantic: Optional[str] = None
    css_selector_hint: Optional[str] = None
    value: str
    clear_first: bool = True


class SelectStep(BaseStep):
    type: Literal["SELECT"]
    target_semantic: Optional[str] = None
    css_selector_hint: Optional[str] = None
    value: str


class WaitStep(BaseStep):
    type: Literal["WAIT"]
    seconds: Optional[float] = None
    until_url_contains: Optional[str] = None
    until_selector: Optional[str] = None
    until_text_visible: Optional[str] = None


class ScrollStep(BaseStep):
    type: Literal["SCROLL"]
    target_selector: Optional[str] = None
    direction: Literal["up", "down"] = "down"
    pixels: int = 300


class ScreenshotStep(BaseStep):
    type: Literal["SCREENSHOT"]
    filename: str


Step = Annotated[
    Union[GotoStep, ClickStep, TypeStep, SelectStep, WaitStep, ScrollStep, ScreenshotStep],
    Field(discriminator="type"),
]


class WorkflowTemplate(BaseModel):
    name: str
    description: Optional[str] = None
    start_url: str
    parameters: list[ParameterSpec] = Field(default_factory=list)
    steps: list[Step]
    category: str = "custom"
    tags: list[str] = Field(default_factory=list)
    estimated_duration_seconds: Optional[int] = None


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
    step_index: Optional[int] = None
    screenshot_path: Optional[str] = None


class DisambiguationCandidate(BaseModel):
    index: int
    label: str
    css: str
    confidence: float
    location: Optional[str] = None


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
    disambiguation: Optional[DisambiguationPayload] = None


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
    text_hint: Optional[str] = None
    role_hint: Optional[str] = None
    label_hint: Optional[str] = None
    placeholder_hint: Optional[str] = None
    relative_hint: Optional[str] = None
    page_context: Optional[str] = None
    visual_description: Optional[str] = None


class WorkflowStep(BaseModel):
    type: ActionType
    description: str
    target: Optional[SemanticTarget] = None
    value: Optional[str] = None
    url: Optional[str] = None
    wait_for: Optional[WaitCondition] = None
    wait_text: Optional[str] = None
    timeout_seconds: float = Field(default=10.0, gt=0)


class SemanticWorkflow(BaseModel):
    name: str
    description: str
    start_url: str
    steps: list[WorkflowStep]
    extracted_at: Optional[str] = None
    source_video: Optional[str] = None


class ResolvedStep(BaseModel):
    original_step: WorkflowStep
    resolved_selector: Optional[str] = None
    selector_type: Optional[Literal["css", "xpath"]] = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    alternatives: list[str] = Field(default_factory=list)
