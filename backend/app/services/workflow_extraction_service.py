"""
Workflow extraction service using Google Gemini VLM.
Extracts semantic workflows from video recordings.
"""
import asyncio
import json
import logging
# Temporary files not used - keyframes saved to permanent directory
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional
import dotenv 

dotenv.load_dotenv()

from ..core.frame_extractor import extract_keyframes
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
        """Create optimal prompts that analyze actual frame content."""

        system_prompt = """You are an expert at analyzing web application workflows from screenshots and generating complete Selenium automation JSON.

Your task is to carefully analyze the provided screenshots in sequence to understand what the user actually did, then create a comprehensive workflow that captures every action step-by-step.

CRITICAL REQUIREMENTS:
1. CAREFULLY EXAMINE each screenshot to understand what the user actually clicked, typed, and selected
2. Use ONLY the information visible in the screenshots - do not make assumptions
3. Generate a COMPLETE workflow with ALL steps from start to finish based on what you see
4. Use semantic descriptions only (NO CSS selectors or XPath)
5. Focus on visible text, labels, and UI element roles exactly as they appear"""

        user_prompt = f"""CAREFULLY analyze these {num_frames} screenshots showing a user booking a study room.

STEP 1: First, examine each screenshot and identify:
- What library/location is shown?
- What specific room/space is being booked?
- What time slot is selected?
- What form fields are filled out?
- What buttons are clicked?

STEP 2: Based on your analysis of the actual screenshots, create a COMPLETE Selenium workflow JSON with this structure:

{{
  "name": "[Descriptive name based on what you see]",
  "description": "[Description based on the actual location/room from screenshots]",
  "start_url": "[URL visible in screenshots]",
  "steps": [
    {{
      "type": "GOTO",
      "description": "Navigate to the booking system",
      "url": "[actual URL from screenshots]",
      "wait_for": "PAGE_LOAD",
      "timeout_seconds": 10.0
    }},
    {{
      "type": "CLICK",
      "description": "Select [actual room name from screenshots]",
      "target": {{
        "text_hint": "[exact room name visible in screenshots]",
        "role_hint": "[button/link/etc]",
        "page_context": "room selection"
      }},
      "wait_for": "ELEMENT_VISIBLE",
      "timeout_seconds": 10.0
    }}
    // ... continue with ALL steps you observe in the screenshots
  ]
}}

CRITICAL:
- Use ONLY information visible in the screenshots
- Use exact room names, times, and text you can see
- Do NOT use generic examples or placeholder text
- Generate 8-12 steps covering the complete workflow
- Include form filling with actual values if visible

Return ONLY the JSON object based on your analysis of the actual screenshots."""

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
        """Fix common validation issues in workflow data."""
        # Ensure required fields
        if "name" not in data:
            data["name"] = "UC Irvine Study Room Booking"
        if "description" not in data:
            data["description"] = "Book a study room at UC Irvine Science Library"
        if "start_url" not in data:
            data["start_url"] = "https://uci.libcal.com/"

        # Fix steps if needed
        if "steps" not in data:
            data["steps"] = []

        # Fix individual steps
        for i, step in enumerate(data.get("steps", [])):
            if "type" not in step:
                step["type"] = "CLICK"
            if "description" not in step:
                step["description"] = f"Step {i + 1}"
            if "timeout_seconds" not in step:
                step["timeout_seconds"] = 10.0

            # Fix invalid action types - convert common alternatives
            if "type" in step:
                action_type = step["type"]
                # Convert ASSERT and VERIFY to WAIT with text checking
                if action_type in ["ASSERT", "VERIFY"]:
                    step["type"] = "WAIT"
                    # If there's a text hint, use it for wait condition
                    if step.get("target") and step["target"].get("text_hint"):
                        step["wait_text"] = step["target"]["text_hint"]
                        step["wait_for"] = "TEXT_PRESENT"
                    else:
                        step["wait_for"] = "ELEMENT_PRESENT"

            # Fix invalid wait conditions - map common alternatives
            if "wait_for" in step:
                wait_condition = step["wait_for"]
                # Map common variations to valid conditions
                if wait_condition in ["ELEMENT_LOADED", "ELEMENT_READY"]:
                    step["wait_for"] = "ELEMENT_PRESENT"
                elif wait_condition in ["PAGE_READY", "LOAD_COMPLETE"]:
                    step["wait_for"] = "PAGE_LOAD"
                elif wait_condition in ["ELEMENT_CLICKABLE", "ELEMENT_INTERACTABLE"]:
                    step["wait_for"] = "ELEMENT_CLICKABLE"

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