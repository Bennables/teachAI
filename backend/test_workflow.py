#!/usr/bin/env python3
"""
Simple test script for VLM-based workflow extraction.
Run with: python test_workflow.py
"""
import asyncio
import json
import logging
import sys
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from app.services.workflow_extraction_service import WorkflowExtractionService, extract_workflow_from_video
from app.core.vlm_client import check_gemini_availability

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')


async def test_vlm_workflow_extraction(video_path: str, output_file: str = "vlm_workflow.json"):
    """Test VLM-based workflow extraction."""

    print("🚀 TESTING VLM WORKFLOW EXTRACTION")
    print("=" * 60)

    # Check if video exists
    if not Path(video_path).exists():
        print(f"❌ Video file not found: {video_path}")
        return False

    # Check VLM availability
    print("🔍 Checking VLM availability...")
    availability = check_gemini_availability()

    print("VLM Status:")
    for requirement, status in availability["requirements_met"].items():
        print(f"  {requirement}: {status}")

    if not availability["available"]:
        print("\n❌ VLM setup required:")
        for issue in availability["issues"]:
            print(f"  - {issue}")
        print(f"\n💡 Setup instructions:")
        print(f"  1. Install: pip install google-generativeai")
        print(f"  2. Set API key: export GOOGLE_API_KEY=your_api_key")
        print(f"  3. Get API key: https://aistudio.google.com/app/apikey")
        return False

    print("✅ VLM is ready!")

    # Progress tracking
    def progress_callback(message: str, percent: float):
        print(f"[{percent:3.0f}%] {message}")

    try:
        print(f"\n🎬 Processing video: {Path(video_path).name}")

        # Method 1: Using service directly
        service = WorkflowExtractionService(
            model_name="gemini-3-flash-preview",  # Use the most capable model
            max_tokens=8000,  # Increase significantly for complete workflows
            temperature=0.3
        )

        workflow = await service.extract_workflow(
            video_path=video_path,
            progress_callback=progress_callback
        )

        print(f"\n✅ Extraction completed successfully!")
        print(f"📋 Workflow: {workflow.name}")
        print(f"📝 Description: {workflow.description}")
        print(f"🌐 Start URL: {workflow.start_url}")
        print(f"📊 Steps: {len(workflow.steps)}")

        # Save workflow
        workflow_dict = workflow.model_dump()
        with open(output_file, 'w') as f:
            json.dump(workflow_dict, f, indent=2)

        print(f"💾 Workflow saved to: {output_file}")

        # Preview first few steps
        print(f"\n📋 Workflow preview:")
        for i, step in enumerate(workflow.steps[:5]):
            target_hint = ""
            if step.target and step.target.text_hint:
                target_hint = f" ('{step.target.text_hint}')"

            print(f"  {i+1}. {step.type}: {step.description}{target_hint}")

        if len(workflow.steps) > 5:
            print(f"  ... and {len(workflow.steps) - 5} more steps")

        return True

    except Exception as e:
        print(f"❌ Extraction failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_convenience_function(video_path: str):
    """Test the convenience function."""
    print(f"\n🧪 Testing convenience function...")

    try:
        workflow = await extract_workflow_from_video(
            video_path=video_path,
            output_path="convenience_workflow.json"
        )

        print(f"✅ Convenience function test passed!")
        print(f"📋 Generated: {workflow.name} ({len(workflow.steps)} steps)")

    except Exception as e:
        print(f"❌ Convenience function test failed: {e}")


async def compare_with_manual_workflow():
    """Compare VLM output with manually created workflow."""
    print(f"\n📊 Comparing with manual workflow...")

    # Load manual workflow if exists
    manual_path = "workflow_uci_library_booking.json"
    if Path(manual_path).exists():
        with open(manual_path, 'r') as f:
            manual_workflow = json.load(f)

        vlm_path = "vlm_workflow.json"
        if Path(vlm_path).exists():
            with open(vlm_path, 'r') as f:
                vlm_workflow = json.load(f)

            print(f"Manual workflow steps: {len(manual_workflow.get('steps', []))}")
            print(f"VLM workflow steps: {len(vlm_workflow.get('steps', []))}")

            # Compare step types
            manual_types = [step.get('type') for step in manual_workflow.get('steps', [])]
            vlm_types = [step.get('type') for step in vlm_workflow.get('steps', [])]

            print(f"Manual step types: {manual_types}")
            print(f"VLM step types: {vlm_types}")

            if len(vlm_workflow.get('steps', [])) >= len(manual_workflow.get('steps', [])):
                print("✅ VLM generated more complete workflow!")
            else:
                print("⚠️ VLM generated fewer steps than manual")

        else:
            print("No VLM workflow found for comparison")
    else:
        print("No manual workflow found for comparison")


async def main():
    """Main test function."""
    # Default test video
    test_video = "/Users/jisharajala/teachAI/teachAI/test_vid3.mov"

    # Allow command line argument
    if len(sys.argv) > 1:
        test_video = sys.argv[1]

    # Check if video exists
    if not Path(test_video).exists():
        print(f"❌ Video not found: {test_video}")
        print("\n💡 Usage: python test_workflow.py [video_path]")
        print("   Example: python test_workflow.py ../test_vid3.mov")
        return

    # Run tests
    success = await test_vlm_workflow_extraction(test_video)

    if success:
        #await test_convenience_function(test_video)
        #await compare_with_manual_workflow()

        print(f"\n🎉 All tests completed!")
        print(f"📁 Check the generated workflows:")
        print(f"   - vlm_workflow.json")
        print(f"   - convenience_workflow.json")
    else:
        print(f"\n❌ Testing failed - check setup and try again")


if __name__ == "__main__":
    asyncio.run(main())