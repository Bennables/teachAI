"""
Main pipeline orchestrator for semantic workflow extraction.

Coordinates all components: frame extraction, VLM analysis, JSON parsing, and validation.
"""
from __future__ import annotations

import asyncio
import json
import logging
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Callable

from .vlm_client import VLMClient
from .json_utils import parse_json_safe, validate_workflow_json, fix_common_json_errors
from .vlm_prompts import create_extraction_prompt, create_repair_prompt
from ..models.schemas import SemanticWorkflow

logger = logging.getLogger(__name__)


class WorkflowExtractionPipeline:
    """
    Main pipeline for extracting semantic workflows from video recordings.

    Orchestrates the complete flow:
    1. Extract keyframes from video
    2. Analyze frames with Gemini VLM
    3. Parse and validate JSON output
    4. Repair if needed
    5. Return semantic workflow
    """

    def __init__(
        self,
        vlm_client: VLMClient | None = None,
        temp_dir: str = "/tmp/workflow_extraction",
        max_repair_attempts: int = 2
    ):
        self.vlm_client = vlm_client
        self.temp_dir = temp_dir
        self.max_repair_attempts = max_repair_attempts
        self._cleanup_dirs: list[Path] = []

    async def extract(
        self,
        video_path: str | Path,
        on_progress: Callable[[str, float], None] | None = None
    ) -> SemanticWorkflow:
        """
        Extract semantic workflow from video recording.

        Args:
            video_path: Path to video file
            on_progress: Optional progress callback (message, percent)

        Returns:
            Extracted semantic workflow

        Raises:
            ValueError: If extraction fails
            FileNotFoundError: If video file doesn't exist
        """
        video_path = Path(video_path)
        if not video_path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")

        def progress(message: str, percent: float):
            logger.info(f"[Distill] {message} ({percent:.0f}%)")
            if on_progress:
                on_progress(message, percent)

        try:
            progress("Starting workflow extraction", 0)

            # Step 1: Extract keyframes (0-20%)
            progress("Extracting keyframes from video", 10)
            keyframe_dir = await self._extract_keyframes(video_path)
            keyframes = list(keyframe_dir.glob("*.jpg"))

            if not keyframes:
                raise ValueError("No keyframes extracted from video")

            logger.info(f"[Distill] Extracted {len(keyframes)} keyframes")
            progress(f"Extracted {len(keyframes)} keyframes", 20)

            # Step 2: Initialize VLM (20-30%)
            progress("Initializing Gemini VLM", 25)
            if not self.vlm_client:
                self.vlm_client = VLMClient()

            await self.vlm_client.initialize()
            progress("VLM initialized", 30)

            # Step 3: Analyze frames with VLM (30-70%)
            progress("Analyzing frames with VLM", 40)

            system_prompt, user_prompt = create_extraction_prompt(len(keyframes))

            def token_callback(token: str):
                # Called for each streaming token - could update progress
                pass

            vlm_response = await self.vlm_client.analyze_frames(
                frames=keyframes,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                on_token=token_callback
            )

            progress("VLM analysis complete", 70)

            # Step 4: Parse and validate JSON (70-90%)
            progress("Parsing workflow JSON", 80)
            workflow_data = await self._parse_and_validate(vlm_response, keyframes)

            # Step 5: Create workflow object (90-100%)
            progress("Creating workflow object", 90)
            workflow = SemanticWorkflow(
                **workflow_data,
                extracted_at=datetime.now().isoformat(),
                source_video=str(video_path)
            )

            progress("Workflow extraction complete", 100)
            logger.info(f"[Distill] Successfully extracted workflow: {workflow.name}")

            return workflow

        finally:
            # Cleanup temporary directories
            await self._cleanup()

    async def _extract_keyframes(self, video_path: Path) -> Path:
        """Extract keyframes to temporary directory."""
        try:
            from .frame_extractor import extract_keyframes
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                "Frame extraction dependencies are not available. "
                "Check OpenCV/NumPy installation for this Python version."
            ) from exc

        # Ensure temp directory exists
        if self.temp_dir:
            Path(self.temp_dir).mkdir(parents=True, exist_ok=True)

        temp_dir = Path(tempfile.mkdtemp(prefix="keyframes_", dir=self.temp_dir))
        self._cleanup_dirs.append(temp_dir)

        # Run extraction in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        keyframes = await loop.run_in_executor(
            None,
            extract_keyframes,
            video_path,
            temp_dir
        )

        return temp_dir

    async def _parse_and_validate(
        self,
        vlm_response: str,
        keyframes: list[Path],
        attempt: int = 0
    ) -> dict:
        """
        Parse and validate VLM response, with repair attempts if needed.

        Args:
            vlm_response: Raw VLM response text
            keyframes: Keyframe paths for repair attempts
            attempt: Current repair attempt number

        Returns:
            Valid workflow dictionary

        Raises:
            ValueError: If parsing/validation fails after all attempts
        """
        logger.debug(f"[Distill] Parsing VLM response (attempt {attempt + 1})")

        # Parse JSON
        workflow_data = parse_json_safe(vlm_response)
        if workflow_data is None:
            if attempt < self.max_repair_attempts:
                logger.warning("[Distill] JSON parsing failed, attempting repair")
                return await self._repair_workflow(vlm_response, ["Invalid JSON format"], keyframes, attempt + 1)
            else:
                raise ValueError("Failed to parse JSON after all repair attempts")

        # Validate structure
        is_valid, errors = validate_workflow_json(workflow_data)
        if not is_valid:
            if attempt < self.max_repair_attempts:
                logger.warning(f"[Distill] Validation failed: {errors}")
                return await self._repair_workflow(vlm_response, errors, keyframes, attempt + 1)
            else:
                raise ValueError(f"Validation failed after all repair attempts: {errors}")

        logger.info("[Distill] Workflow JSON validated successfully")
        return workflow_data

    async def _repair_workflow(
        self,
        original_response: str,
        errors: list[str],
        keyframes: list[Path],
        attempt: int
    ) -> dict:
        """
        Attempt to repair invalid workflow using VLM.

        Args:
            original_response: Original VLM response that failed
            errors: List of validation errors
            keyframes: Keyframe paths
            attempt: Current attempt number

        Returns:
            Repaired workflow dictionary
        """
        logger.info(f"[Distill] Attempting repair (attempt {attempt})")

        # Create repair prompts
        system_prompt, user_prompt = create_repair_prompt(errors, original_response)

        # Use fewer frames for repair to reduce complexity
        repair_frames = keyframes[::2] if len(keyframes) > 10 else keyframes

        # Get repaired response
        repaired_response = await self.vlm_client.analyze_frames(
            frames=repair_frames,
            system_prompt=system_prompt,
            user_prompt=user_prompt
        )

        # Recursively parse and validate
        return await self._parse_and_validate(repaired_response, keyframes, attempt)

    async def _cleanup(self):
        """Clean up temporary directories."""
        for temp_dir in self._cleanup_dirs:
            try:
                if temp_dir.exists():
                    shutil.rmtree(temp_dir)
                    logger.debug(f"[Distill] Cleaned up temp dir: {temp_dir}")
            except Exception as e:
                logger.warning(f"[Distill] Failed to cleanup {temp_dir}: {e}")

        self._cleanup_dirs.clear()


# Convenience functions
async def extract_workflow(
    video_path: str,
    output_path: str | None = None,
    vlm_client: VLMClient | None = None,
    on_progress: Callable[[str, float], None] | None = None
) -> SemanticWorkflow:
    """
    Extract semantic workflow from video file.

    Args:
        video_path: Path to video file
        output_path: Optional path to save workflow JSON
        vlm_client: Optional VLM client instance
        on_progress: Optional progress callback

    Returns:
        Extracted semantic workflow
    """
    pipeline = WorkflowExtractionPipeline(vlm_client=vlm_client)
    workflow = await pipeline.extract(video_path, on_progress)

    # Save to file if requested
    if output_path:
        workflow_dict = workflow.model_dump()
        with open(output_path, 'w') as f:
            json.dump(workflow_dict, f, indent=2)
        logger.info(f"[Distill] Saved workflow to {output_path}")

    return workflow


async def extract_workflow_with_progress(
    video_path: str,
    progress_callback: Callable[[str, float], None]
) -> SemanticWorkflow:
    """
    Extract workflow with progress updates.

    Args:
        video_path: Path to video file
        progress_callback: Function called with (message, percent) updates

    Returns:
        Extracted semantic workflow
    """
    return await extract_workflow(video_path, on_progress=progress_callback)


def extract_workflow_sync(
    video_path: str,
    output_path: str | None = None,
    vlm_client: VLMClient | None = None
) -> SemanticWorkflow:
    """
    Synchronous wrapper for workflow extraction.

    Args:
        video_path: Path to video file
        output_path: Optional path to save workflow JSON
        vlm_client: Optional VLM client instance

    Returns:
        Extracted semantic workflow
    """
    return asyncio.run(extract_workflow(video_path, output_path, vlm_client))


class BatchWorkflowExtractor:
    """Extract workflows from multiple videos in batch."""

    def __init__(self, vlm_client: VLMClient | None = None):
        self.vlm_client = vlm_client

    async def extract_batch(
        self,
        video_paths: list[str | Path],
        output_dir: str | Path,
        on_video_complete: Callable[[str, SemanticWorkflow], None] | None = None
    ) -> dict[str, SemanticWorkflow]:
        """
        Extract workflows from multiple videos.

        Args:
            video_paths: List of video file paths
            output_dir: Directory to save workflow JSON files
            on_video_complete: Optional callback when each video completes

        Returns:
            Dictionary mapping video path to extracted workflow
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        results = {}
        pipeline = WorkflowExtractionPipeline(vlm_client=self.vlm_client)

        for i, video_path in enumerate(video_paths):
            video_path = Path(video_path)
            logger.info(f"[Distill] Processing {i+1}/{len(video_paths)}: {video_path.name}")

            try:
                # Extract workflow
                workflow = await pipeline.extract(video_path)

                # Save to output directory
                output_file = output_dir / f"{video_path.stem}_workflow.json"
                workflow_dict = workflow.model_dump()
                with open(output_file, 'w') as f:
                    json.dump(workflow_dict, f, indent=2)

                results[str(video_path)] = workflow

                if on_video_complete:
                    on_video_complete(str(video_path), workflow)

                logger.info(f"[Distill] Completed {video_path.name}")

            except Exception as e:
                logger.error(f"[Distill] Failed to process {video_path.name}: {e}")

        return results
