"""
Vision-Language Model client for workflow extraction.
Uses Google Gemini for reliable image analysis.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import os
from pathlib import Path
from typing import Callable, Optional
import dotenv 

dotenv.load_dotenv()

try:
    import google.genai as genai
    from google.generativeai.types import HarmCategory, HarmBlockThreshold
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

logger = logging.getLogger(__name__)


class VLMClient:
    """
    Vision-Language Model client for analyzing images and generating workflows.
    Uses Google Gemini for reliable vision-language analysis.
    """

    def __init__(self,
                 model_name: str = "gemini-3-flash-preview",
                 api_key: Optional[str] = None,
                 max_tokens: int = 8000,
                 temperature: float = 0.3):

        if not GEMINI_AVAILABLE:
            raise RuntimeError(
                "Google GenerativeAI library not available. Install with: pip install google-generativeai"
            )

        self.model_name = model_name
        self.max_tokens = max_tokens
        self.temperature = temperature

        # Configure API key
        api_key = api_key or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError(
                "Google API key required. Set GOOGLE_API_KEY environment variable or pass api_key parameter"
            )

        genai.configure(api_key=api_key)
        self.model = None
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize Gemini model."""
        if self._initialized:
            return

        logger.info(f"[Gemini] Initializing {self.model_name}")

        try:
            # Configure safety settings to be less restrictive for workflow analysis
            safety_settings = {
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            }

            # Configure generation settings
            generation_config = genai.GenerationConfig(
                max_output_tokens=self.max_tokens,
                temperature=self.temperature,
                top_p=0.95,
                top_k=64,
            )

            self.model = genai.GenerativeModel(
                model_name=self.model_name,
                generation_config=generation_config,
                safety_settings=safety_settings
            )

            self._initialized = True
            logger.info(f"[Gemini] Model initialized successfully")

        except Exception as e:
            logger.error(f"[Gemini] Failed to initialize model: {e}")
            raise RuntimeError(f"Gemini initialization failed: {e}") from e

    async def analyze_frames(self,
                           frames: list[Path | str],
                           system_prompt: str,
                           user_prompt: str,
                           on_token: Optional[Callable[[str], None]] = None) -> str:
        """
        Analyze keyframes and extract workflow JSON.

        Args:
            frames: List of image file paths
            system_prompt: System instruction for the model
            user_prompt: User prompt for analysis
            on_token: Optional token callback (not used with Gemini)

        Returns:
            Generated workflow JSON string
        """
        if not self._initialized:
            await self.initialize()

        logger.info(f"[Gemini] Analyzing {len(frames)} keyframes")

        # Prepare images for Gemini
        images = []
        for frame_path in frames:
            try:
                # Load and prepare image for Gemini
                image_data = self._load_image_for_gemini(frame_path)
                images.append(image_data)
            except Exception as e:
                logger.warning(f"[Gemini] Failed to load image {frame_path}: {e}")

        if not images:
            raise ValueError("No valid images could be loaded from frames")

        # Create combined prompt (Gemini doesn't have separate system/user prompts)
        combined_prompt = f"{system_prompt}\n\n{user_prompt}"

        # Generate response
        return await self._generate_response(combined_prompt, images)

    def _load_image_for_gemini(self, image_path: Path | str) -> dict:
        """Load image in format expected by Gemini."""
        image_path = Path(image_path)

        with open(image_path, 'rb') as f:
            image_data = f.read()

        return {
            'mime_type': 'image/jpeg',
            'data': image_data
        }

    async def _generate_response(self, prompt: str, images: list[dict]) -> str:
        """Generate response from Gemini."""
        try:
            # Prepare content for Gemini
            content = [prompt]  # Start with text prompt

            # Add images
            for image in images:
                content.append(image)

            # Generate response in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                self._generate_sync,
                content
            )

            # Extract text from response
            response_text = response.text if hasattr(response, 'text') else str(response)

            logger.info(f"[Gemini] Generated response ({len(response_text)} chars)")
            return response_text

        except Exception as e:
            logger.error(f"[Gemini] Generation failed: {e}")
            raise RuntimeError(f"Gemini generation failed: {e}") from e

    def _generate_sync(self, content: list) -> str:
        """Generate response synchronously."""
        response = self.model.generate_content(content)

        # Handle potential safety issues
        if response.prompt_feedback:
            blocked_reason = response.prompt_feedback.block_reason
            if blocked_reason:
                raise RuntimeError(f"Content blocked by safety filters: {blocked_reason}")

        return response

    async def close(self) -> None:
        """Clean up resources (no cleanup needed for Gemini)."""
        self.model = None
        self._initialized = False
        logger.info("[Gemini] Client closed")

    async def get_model_info(self) -> dict:
        """Get information about the model."""
        return {
            "model_name": self.model_name,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "status": "initialized" if self._initialized else "not_initialized",
            "provider": "Google Gemini"
        }


# Compatibility alias for easy replacement
class ReliableVLMClient(VLMClient):
    """Alias for easy drop-in replacement of MLX-VLM client."""
    pass


def check_gemini_availability() -> dict:
    """Check if Gemini is available and configured."""
    result = {
        "available": False,
        "issues": [],
        "requirements_met": {}
    }

    # Check library availability
    if GEMINI_AVAILABLE:
        result["requirements_met"]["library"] = "OK google-generativeai installed"
    else:
        result["issues"].append("google-generativeai library not installed")
        result["requirements_met"]["library"] = "FAIL google-generativeai missing"

    # Check API key
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if api_key:
        result["requirements_met"]["api_key"] = "OK API key configured"
    else:
        result["issues"].append("Google API key not configured")
        result["requirements_met"]["api_key"] = "FAIL API key missing"

    # Check model access (if library available)
    if GEMINI_AVAILABLE and api_key:
        try:
            genai.configure(api_key=api_key)
            # Try to list models to verify access
            models = list(genai.list_models())
            result["requirements_met"]["model_access"] = f"OK {len(models)} models available"
        except Exception as e:
            result["issues"].append(f"Cannot access Gemini models: {e}")
            result["requirements_met"]["model_access"] = f"FAIL {e}"

    result["available"] = len(result["issues"]) == 0
    return result


# Example usage
async def example_gemini_usage():
    """Example of how to use Gemini VLM client."""

    # Initialize client
    client = VLMClient(
        model_name="gemini-3-flash-preview",  # or "gemini-1.5-flash" for faster responses
        api_key="your-api-key-here",  # or set GOOGLE_API_KEY environment variable
        max_tokens=2000,
        temperature=0.3
    )

    await client.initialize()

    # Analyze images
    frame_paths = ["frame1.jpg", "frame2.jpg", "frame3.jpg"]

    system_prompt = "You are a workflow analysis expert."
    user_prompt = "Analyze these screenshots and create a workflow JSON."

    try:
        response = await client.analyze_frames(
            frames=frame_paths,
            system_prompt=system_prompt,
            user_prompt=user_prompt
        )

        print(f"Generated workflow: {response}")

    finally:
        await client.close()


if __name__ == "__main__":
    # Check availability
    availability = check_gemini_availability()
    print("Gemini Availability Check:")
    for requirement, status in availability["requirements_met"].items():
        print(f"  {requirement}: {status}")

    if availability["available"]:
        print("✅ Gemini is ready to use!")
    else:
        print("❌ Setup required:")
        for issue in availability["issues"]:
            print(f"  - {issue}")
