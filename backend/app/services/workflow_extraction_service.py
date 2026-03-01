"""
Workflow extraction service using Google Gemini VLM.
Extracts semantic workflows from video recordings.
"""
from __future__ import annotations

import asyncio
import json
import logging
# Temporary files not used - keyframes saved to permanent directory
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional
import dotenv 

dotenv.load_dotenv()

from ..core.vlm_client import VLMClient
from ..core.json_utils import parse_json_safe
from ..models.schemas import SemanticWorkflow

logger = logging.getLogger(__name__)

class WorkflowExtractionService:
    """
    Production workflow extraction service using Google Gemini VLM.

    Coordinates the complete workflow extraction pipeline:
    1. Extract keyframes from video
    2. Analyze frames with Gemini vision model
    3. Parse and validate JSON output
    4. Return semantic workflow
    """

    def __init__(self,
                 api_key: Optional[str] = None,
                 model_name: str = "gemini-3-flash-preview",
                 max_tokens: int = 8000,
                 temperature: float = 0.3):

        self.vlm_client = VLMClient(
            model_name=model_name,
            api_key=api_key,
            max_tokens=max_tokens,
            temperature=temperature
        )
        # Keyframes now saved to permanent directory for debugging

    async def extract_workflow(self,
                             video_path: str | Path,
                             progress_callback: Optional[Callable[[str, float], None]] = None) -> SemanticWorkflow:
        """
        Extract complete workflow from video using Gemini.

        Args:
            video_path: Path to video file
            progress_callback: Optional progress updates

        Returns:
            Extracted semantic workflow

        Raises:
            ValueError: If extraction fails
            FileNotFoundError: If video doesn't exist
        """
        video_path = Path(video_path)
        if not video_path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")

        def progress(message: str, percent: float):
            logger.info(f"[WorkflowService] {message} ({percent:.1f}%)")
            if progress_callback:
                progress_callback(message, percent)

        try:
            progress("Starting Gemini workflow extraction", 0)

            # Step 1: Extract keyframes (0-25%)
            progress("Extracting keyframes from video", 10)
            keyframe_paths = await self._extract_keyframes(video_path)

            if not keyframe_paths:
                raise ValueError("No keyframes extracted from video")

            logger.info(f"[WorkflowService] Extracted {len(keyframe_paths)} keyframes")
            progress(f"Extracted {len(keyframe_paths)} keyframes", 25)

            # Step 2: Initialize Gemini (25-35%)
            progress("Initializing Gemini VLM", 30)
            await self.vlm_client.initialize()
            progress("Gemini initialized", 35)

            # Step 3: Analyze with Gemini (35-80%)
            progress("Analyzing frames with Gemini", 50)
            vlm_response = await self._analyze_frames_vlm(keyframe_paths, video_path.name)
            progress("Gemini analysis complete", 80)

            # Step 4: Parse and validate JSON (80-95%)
            progress("Parsing workflow JSON", 85)
            workflow_data = await self._parse_and_validate_json(vlm_response)

            # Step 5: Create workflow object (95-100%)
            progress("Creating workflow object", 95)
            workflow = SemanticWorkflow(
                **workflow_data,
                extracted_at=datetime.now().isoformat(),
                source_video=str(video_path)
            )

            progress("Workflow extraction complete", 100)
            logger.info(f"[WorkflowService] Successfully extracted: {workflow.name}")

            return workflow

        finally:
            # Cleanup (keyframes are kept in permanent directory for debugging)
            await self.vlm_client.close()

    async def _extract_keyframes(self, video_path: Path) -> list[Path]:
        """Extract keyframes to permanent directory for debugging."""
        try:
            from ..core.frame_extractor import extract_keyframes
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                "Frame extraction dependencies are not available. "
                "Check OpenCV/NumPy installation for this Python version."
            ) from exc

        # Create permanent debug directory next to video file
        debug_dir = video_path.parent / f"keyframes_{video_path.stem}"
        debug_dir.mkdir(exist_ok=True)

        # Clear any existing frames
        for old_frame in debug_dir.glob("*.jpg"):
            old_frame.unlink()

        logger.info(f"[WorkflowService] Saving keyframes to permanent directory: {debug_dir}")

        loop = asyncio.get_event_loop()
        keyframe_paths = await loop.run_in_executor(
            None,
            extract_keyframes,
            video_path,
            debug_dir,
            0.015,  # change_threshold
            8,      # max_frames
            0,      # context_frames
            6,      # min_keyframes
            0.02,   # dedupe_diff_threshold
            15.0    # target_fps - much higher for UI workflows
        )
        logger.info(f"[WorkflowService] Keyframe paths: {keyframe_paths}")
        return keyframe_paths

    async def _analyze_frames_vlm(self, frame_paths: list[Path], video_name: str) -> str:
        """Analyze frames using VLM."""
        logger.info(f"[WorkflowService] Analyzing {len(frame_paths)} frames with VLM")

        # Use the best prompt from testing (v3_example_driven)
        system_prompt, user_prompt = self._create_optimal_prompts(len(frame_paths), video_name)

        try:
            response = await self.vlm_client.analyze_frames(
                frames=frame_paths,
                system_prompt=system_prompt,
                user_prompt=user_prompt
            )

            logger.info(f"[WorkflowService] Gemini generated {len(response)} characters")
            return response

        except Exception as e:
            logger.error(f"[WorkflowService] Gemini analysis failed: {e}")
            raise RuntimeError(f"Gemini analysis failed: {e}")

    def _create_optimal_prompts(self, num_frames: int, video_name: str) -> tuple[str, str]:
        """Create optimal prompts that analyze actual frame content and generate reusable workflow templates."""

        system_prompt = """You are an expert at analyzing web application workflows from screenshots and generating REUSABLE Selenium automation templates.

Your task is to carefully analyze the provided screenshots to understand the user's workflow pattern, then create a TEMPLATE workflow that can be reused for similar bookings with different parameters.

CRITICAL REQUIREMENTS:
1. CAREFULLY EXAMINE each screenshot to understand the workflow PATTERN (not just the specific values)
2. Create a REUSABLE template with placeholder variables instead of hardcoded values
3. Generate a workflow template compatible with Selenium automation that uses parameter substitution
4. Use semantic descriptions only (NO CSS selectors or XPath)
5. Focus on the GENERAL workflow pattern, not specific room numbers or dates

TEMPLATE PLACEHOLDER RULES - ALWAYS USE THESE:
- {{library}} for location/library names
- {{room_keyword}} for room numbers or identifiers
- {{booking_date}} for dates
- {{booking_time}} for start times
- {{booking_end_time}} for end times
- {{full_name}} for person names
- {{email}} for email addresses
- {{affiliation}} for affiliation selections (Undergraduate/Graduate/Faculty/Staff)
- {{purpose_for_reservation_covid_19}} for reservation purposes
- {{duration_minutes}} for booking durations"""

        user_prompt = f"""CAREFULLY analyze these {num_frames} screenshots showing a user booking a study room.

STEP 1: First, examine each screenshot and identify the WORKFLOW PATTERN:
- What types of elements are being interacted with (dropdowns, buttons, form fields)?
- What is the sequence of actions (navigation -> room selection -> time selection -> form filling)?
- What form fields need to be filled out?
- What buttons need to be clicked?

STEP 2: Based on the workflow pattern you observe, create a REUSABLE Selenium workflow template with this exact structure:

{{
  "name": "UCI Library Study Room Booking",
  "description": "Template for booking study rooms at UCI libraries",
  "start_url": "[URL visible in screenshots or use https://spaces.lib.uci.edu/spaces]",
  "category": "booking",
  "tags": ["uci", "library", "booking"],
  "parameters": [
    {{
      "key": "library",
      "description": "Library location",
      "example": "Gateway Study Center",
      "required": true,
      "input_type": "text"
    }},
    {{
      "key": "room_keyword",
      "description": "Room identifier",
      "example": "2107",
      "required": true,
      "input_type": "text"
    }},
    {{
      "key": "booking_date",
      "description": "Booking date in MM/DD/YYYY format",
      "example": "03/02/2026",
      "required": true,
      "input_type": "text"
    }},
    {{
      "key": "booking_time",
      "description": "Time slot to book",
      "example": "6:30pm",
      "required": true,
      "input_type": "text"
    }},
    {{
      "key": "duration_minutes",
      "description": "Duration in minutes",
      "example": "60",
      "required": true,
      "input_type": "select",
      "options": ["30", "60", "90", "120"]
    }},
    {{
      "key": "full_name",
      "description": "Full name for reservation",
      "example": "Alex Anteater",
      "required": true,
      "input_type": "text"
    }},
    {{
      "key": "email",
      "description": "Email for reservation",
      "example": "alex@uci.edu",
      "required": true,
      "input_type": "text"
    }},
    {{
      "key": "affiliation",
      "description": "Affiliation selection",
      "example": "Undergraduate",
      "required": true,
      "input_type": "select",
      "options": ["Undergraduate", "Graduate", "Faculty", "Staff"]
    }},
    {{
      "key": "purpose_for_reservation_covid_19",
      "description": "Purpose for reservation",
      "example": "Need a place to study",
      "required": true,
      "input_type": "text"
    }}
  ],
  "steps": [
    {{
      "type": "GOTO",
      "description": "Open UCI Libraries spaces page",
      "url": "https://spaces.lib.uci.edu/spaces"
    }},
    {{
      "type": "WAIT",
      "description": "Wait for page content to appear",
      "until_text_visible": "Space Availability"
    }},
    {{
      "type": "SELECT",
      "description": "Select library from Location dropdown",
      "target_semantic": "Location",
      "value": "{{{{library}}}}"
    }},
    {{
      "type": "WAIT",
      "description": "Wait for room list to refresh",
      "seconds": 1.0
    }},
    {{
      "type": "CLICK",
      "description": "Select the study room",
      "target_text_hint": "{{{{room_keyword}}}}"
    }},
    {{
      "type": "CLICK",
      "description": "Select time slot",
      "target_text_hint": "{{{{booking_time}}}}"
    }},
    {{
      "type": "CLICK",
      "description": "Submit Times to proceed to booking form",
      "target_text_hint": "Submit Times"
    }},
    {{
      "type": "WAIT",
      "description": "Wait for booking form to load",
      "until_text_visible": "Space Checkout"
    }},
    {{
      "type": "TYPE",
      "description": "Enter full name",
      "target_semantic": "Full Name",
      "value": "{{{{full_name}}}}"
    }},
    {{
      "type": "TYPE",
      "description": "Enter email",
      "target_semantic": "Email",
      "value": "{{{{email}}}}"
    }},
    {{
      "type": "CLICK",
      "description": "Select affiliation",
      "target_text_hint": "{{{{affiliation}}}}"
    }},
    {{
      "type": "CLICK",
      "description": "Select purpose for reservation",
      "target_text_hint": "{{{{purpose_for_reservation_covid_19}}}}"
    }},
    {{
      "type": "CLICK",
      "description": "Submit the booking",
      "target_text_hint": "Submit my booking"
    }},
    {{
      "type": "WAIT",
      "description": "Wait for confirmation",
      "seconds": 2.0
    }}
  ]
}}

CRITICAL SELENIUM TEMPLATE GUIDELINES:
- Use EXACT field names: target_text_hint, target_semantic, until_text_visible, seconds
- Replace ALL specific values with {{{{variable}}}} placeholders (double braces for escaping)
- Include a complete parameters section with all variables used in steps
- Use semantic descriptions for target_semantic (like "Location", "Full Name", "Email")
- Use visible text for target_text_hint (with placeholders for dynamic text)
- Generate 10-15 steps covering the complete workflow
- Do NOT use nested target objects or role_hint fields

Return ONLY the JSON template with this exact structure for Selenium automation."""

        return system_prompt, user_prompt

    async def _parse_and_validate_json(self, vlm_response: str) -> dict:
        """Parse VLM response JSON and apply basic fixes."""
        logger.info(f"[WorkflowService] Parsing VLM response ({len(vlm_response)} chars)")

        # Debug: Save full response to file for inspection
        try:
            with open("debug_vlm_response.txt", "w") as f:
                f.write(vlm_response)
            logger.info("[WorkflowService] Full VLM response saved to debug_vlm_response.txt")
        except Exception as e:
            logger.warning(f"[WorkflowService] Could not save debug file: {e}")

        # Parse JSON from VLM response
        workflow_data = parse_json_safe(vlm_response)
        if workflow_data is None:
            logger.error("[WorkflowService] JSON parsing failed completely")
            logger.error(f"[WorkflowService] Response length: {len(vlm_response)}")
            logger.error(f"[WorkflowService] Response starts with: {vlm_response[:200]}")
            logger.error(f"[WorkflowService] Response ends with: {vlm_response[-200:]}")

            # Try to find any JSON-like content
            json_start = vlm_response.find('{')
            json_end = vlm_response.rfind('}')
            if json_start != -1 and json_end != -1:
                potential_json = vlm_response[json_start:json_end+1]
                logger.error(f"[WorkflowService] Potential JSON found: {potential_json[:300]}...")
            else:
                logger.error("[WorkflowService] No JSON braces found in response")

            raise ValueError(f"Failed to parse JSON from VLM response. Check debug_vlm_response.txt for full output.")

        # Apply common fixes (Pydantic validation will catch any remaining issues)
        workflow_data = self._fix_common_issues(workflow_data)

        logger.info("[WorkflowService] Workflow JSON parsed and fixed")
        return workflow_data

    def _fix_common_issues(self, data: dict) -> dict:
        """Fix common validation issues in workflow data to match selenium runner format."""
        # Ensure required top-level fields
        if "name" not in data:
            data["name"] = "UCI Library Study Room Booking"
        if "description" not in data:
            data["description"] = "Template for booking study rooms at UCI libraries"
        if "start_url" not in data:
            data["start_url"] = "https://spaces.lib.uci.edu/spaces"
        if "category" not in data:
            data["category"] = "booking"
        if "tags" not in data:
            data["tags"] = ["uci", "library", "booking"]

        # Ensure parameters section exists
        if "parameters" not in data:
            data["parameters"] = []

        # Fix steps if needed
        if "steps" not in data:
            data["steps"] = []

        # Fix individual steps to match selenium runner expectations
        for i, step in enumerate(data.get("steps", [])):
            if "type" not in step:
                step["type"] = "CLICK"
            if "description" not in step:
                step["description"] = f"Step {i + 1}"

            # Convert old format target objects to selenium runner format
            if "target" in step:
                target = step.pop("target")
                # Convert target object to selenium runner field format
                if target.get("text_hint"):
                    step["target_text_hint"] = target["text_hint"]
                if target.get("label_hint"):
                    step["target_semantic"] = target["label_hint"]

            # Convert old wait_for format to selenium runner format
            if "wait_for" in step:
                wait_condition = step.pop("wait_for")
                if wait_condition == "TEXT_PRESENT":
                    step["until_text_visible"] = step.get("wait_text", "")
                elif wait_condition in ["PAGE_LOAD", "ELEMENT_VISIBLE"]:
                    if not step.get("until_text_visible") and not step.get("seconds"):
                        step["seconds"] = 1.0

            # Remove old format fields not used by selenium runner
            step.pop("timeout_seconds", None)
            step.pop("wait_text", None)
            step.pop("wait", None)
            step.pop("until_selector", None)
            step.pop("until_url_contains", None)

        return data

    # Cleanup method removed - keyframes saved to permanent directory for debugging


# Convenience functions
async def extract_workflow_from_video(video_path: str | Path,
                                    output_path: Optional[str | Path] = None,
                                    api_key: Optional[str] = None,
                                    progress_callback: Optional[Callable[[str, float], None]] = None) -> SemanticWorkflow:
    """
    Extract workflow from video using VLM.

    Args:
        video_path: Path to video file
        output_path: Optional path to save JSON workflow
        api_key: Google API key (or set GOOGLE_API_KEY env var)
        progress_callback: Optional progress updates

    Returns:
        Extracted semantic workflow
    """
    service = WorkflowExtractionService(api_key=api_key)
    workflow = await service.extract_workflow(video_path, progress_callback)

    # Save to file if requested
    if output_path:
        workflow_dict = workflow.model_dump()
        output_path = Path(output_path)
        with open(output_path, 'w') as f:
            json.dump(workflow_dict, f, indent=2)
        logger.info(f"[WorkflowService] Saved workflow to {output_path}")

    return workflow
