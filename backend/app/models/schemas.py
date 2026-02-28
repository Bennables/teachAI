from enum import Enum
from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


class ParameterSpec(BaseModel):
    """
    Defines a user-fillable parameter in the workflow.

    Examples:
    - {"key": "room", "description": "Room to book", "example": "Study Room 3A"}
    - {"key": "amount", "description": "Expense amount in USD", "example": "125.50"}
    - {"key": "date", "description": "Appointment date", "example": "2024-01-15"}
    """

    key: str = Field(
        ...,
        pattern=r"^[a-z][a-z0-9_]*$",
        description="Parameter name (lowercase, underscores)",
    )
    description: str = Field(..., description="Human-readable description")
    example: str = Field(..., description="Example value")
    required: bool = Field(default=True)
    input_type: Literal["text", "date", "time", "number", "select"] = "text"
    options: Optional[list[str]] = None


class BaseStep(BaseModel):
    """Common fields for all step types."""

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
    """For dropdown/select elements."""

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
    """Scroll to element or position."""

    type: Literal["SCROLL"]
    target_selector: Optional[str] = None
    direction: Literal["up", "down"] = "down"
    pixels: int = 300


class ScreenshotStep(BaseStep):
    """Capture screenshot (useful for verification)."""

    type: Literal["SCREENSHOT"]
    filename: str


Step = Annotated[
    Union[
        GotoStep,
        ClickStep,
        TypeStep,
        SelectStep,
        WaitStep,
        ScrollStep,
        ScreenshotStep,
    ],
    Field(discriminator="type"),
]


class WorkflowTemplate(BaseModel):
    """
    Complete workflow definition.
    This is site-agnostic - same schema works for any web task.
    """

    name: str
    description: Optional[str] = None
    start_url: str
    parameters: list[ParameterSpec]
    steps: list[Step]

    # Metadata (not used in execution)
    category: str = "custom"
    tags: list[str] = Field(default_factory=list)
    estimated_duration_seconds: Optional[int] = None

    model_config = ConfigDict(extra="forbid")


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
