#!/usr/bin/env python3
"""
MCP Server for TeachAI Backend Integration

This MCP server provides tools for:
1. Applying to Greenhouse job postings
2. Booking UCI library rooms
3. Processing videos with VLM workflow extraction

Usage:
    python mcp_server.py

Claude Desktop Configuration:
Add this to your Claude Desktop MCP settings:
{
  "mcpServers": {
    "teachai": {
      "command": "python",
      "args": ["/Users/jisharajala/teachAI/teachAI/backend/mcp_server.py"],
      "env": {}
    }
  }
}
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict

import httpx
from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.types import (
    CallToolResult,
    ListToolsResult,
    Tool,
    TextContent,
)

# Configuration
API_BASE_URL = "http://localhost:8000"
TIMEOUT = 300.0  # 5 minutes for long-running operations

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("teachai-mcp")

# Create MCP server
server = Server("teachai")


@server.list_tools()
async def list_tools() -> ListToolsResult:
    """List available tools for Claude Desktop."""
    return ListToolsResult(
        tools=[
            Tool(
                name="apply_to_greenhouse_job",
                description="Apply to a Greenhouse job posting by automatically filling out the application form",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "application_url": {
                            "type": "string",
                            "description": "Full URL of the Greenhouse job application page"
                        },
                        "first_name": {"type": "string", "description": "First name"},
                        "last_name": {"type": "string", "description": "Last name"},
                        "email": {"type": "string", "description": "Email address"},
                        "phone": {"type": "string", "description": "Phone number"},
                        "address": {"type": "string", "description": "Optional address"},
                        "submit": {
                            "type": "boolean",
                            "default": False,
                            "description": "Whether to actually submit (false for testing)"
                        },
                        "resume_file_path": {
                            "type": "string",
                            "description": "Path to resume file (PDF/DOC)"
                        }
                    },
                    "required": ["application_url", "first_name", "last_name", "email", "phone", "resume_file_path"]
                }
            ),
            Tool(
                name="book_uci_library_room",
                description="Book a study room at UCI Libraries",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "library": {"type": "string", "description": "Library location"},
                        "booking_date": {"type": "string", "description": "Date in MM/DD/YYYY format"},
                        "room_keyword": {"type": "string", "description": "Room identifier"},
                        "booking_time": {"type": "string", "description": "Start time (e.g., '2:00pm')"},
                        "duration_minutes": {
                            "type": "integer",
                            "enum": [30, 60, 90, 120],
                            "description": "Duration in minutes"
                        },
                        "full_name": {"type": "string", "description": "Full name"},
                        "email": {"type": "string", "description": "UCI email"},
                        "affiliation": {
                            "type": "string",
                            "enum": ["Undergraduate", "Graduate", "Faculty", "Staff"]
                        },
                        "purpose_for_reservation_covid_19": {"type": "string", "description": "Purpose"},
                        "headless": {"type": "boolean", "default": False}
                    },
                    "required": [
                        "library", "booking_date", "room_keyword", "booking_time",
                        "duration_minutes", "full_name", "email", "affiliation",
                        "purpose_for_reservation_covid_19"
                    ]
                }
            ),
            Tool(
                name="extract_workflow_from_video",
                description="Process video with VLM to extract workflow steps",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "video_file_path": {"type": "string", "description": "Path to video file"},
                        "workflow_type": {
                            "type": "string",
                            "enum": ["greenhouse", "langson_library"],
                            "description": "Workflow type to extract"
                        }
                    },
                    "required": ["video_file_path", "workflow_type"]
                }
            )
        ]
    )


@server.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> CallToolResult:
    """Handle tool calls from Claude Desktop."""
    try:
        if name == "apply_to_greenhouse_job":
            return await _apply_to_greenhouse(arguments)
        elif name == "book_uci_library_room":
            return await _book_uci_room(arguments)
        elif name == "extract_workflow_from_video":
            return await _extract_workflow_from_video(arguments)
        else:
            return CallToolResult(
                content=[TextContent(type="text", text=f"Unknown tool: {name}")],
                isError=True
            )
    except Exception as e:
        logger.error(f"Tool call failed: {e}")
        return CallToolResult(
            content=[TextContent(type="text", text=f"Error: {str(e)}")],
            isError=True
        )


async def _apply_to_greenhouse(args: Dict[str, Any]) -> CallToolResult:
    """Apply to a Greenhouse job posting."""
    resume_path = Path(args["resume_file_path"])

    # Validate resume file exists
    if not resume_path.exists():
        return CallToolResult(
            content=[TextContent(type="text", text=f"Resume file not found: {resume_path}")],
            isError=True
        )

    # Prepare form data
    form_data = {
        "application_url": args["application_url"],
        "first_name": args["first_name"],
        "last_name": args["last_name"],
        "email": args["email"],
        "phone": args["phone"],
        "address": args.get("address", ""),
        "submit": args.get("submit", False)
    }

    # Prepare file upload
    files = {"resume": (resume_path.name, resume_path.read_bytes(), "application/pdf")}

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(
                f"{API_BASE_URL}/api/greenhouse/apply",
                data=form_data,
                files=files
            )

        if response.status_code == 200:
            result = response.json()
            success = result.get("success", False)
            message = result.get("message", "No message")

            status = "✅ SUCCESS" if success else "❌ FAILED"
            return CallToolResult(
                content=[
                    TextContent(
                        type="text",
                        text=f"Greenhouse Application {status}\n\n"
                           f"URL: {args['application_url']}\n"
                           f"Applicant: {args['first_name']} {args['last_name']}\n"
                           f"Result: {message}\n"
                           f"Submit: {'YES' if args.get('submit', False) else 'NO (test mode)'}"
                    )
                ]
            )
        else:
            return CallToolResult(
                content=[TextContent(type="text", text=f"API Error: {response.status_code} - {response.text}")],
                isError=True
            )

    except Exception as e:
        return CallToolResult(
            content=[TextContent(type="text", text=f"Request failed: {str(e)}")],
            isError=True
        )


async def _book_uci_room(args: Dict[str, Any]) -> CallToolResult:
    """Book a UCI library room."""
    # Prepare request payload
    payload = {
        "params": {
            "library": args["library"],
            "booking_date": args["booking_date"],
            "room_keyword": args["room_keyword"],
            "booking_time": args["booking_time"],
            "duration_minutes": args["duration_minutes"],
            "full_name": args["full_name"],
            "email": args["email"],
            "affiliation": args["affiliation"],
            "purpose_for_reservation_covid_19": args["purpose_for_reservation_covid_19"]
        },
        "max_auth_resumes": args.get("max_auth_resumes", 2),
        "headless": args.get("headless", False)
    }

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(
                f"{API_BASE_URL}/api/v1/execute-booking",
                json=payload
            )

        if response.status_code == 200:
            result = response.json()
            status = result.get("status", "unknown")
            run_id = result.get("run_id", "N/A")
            execution_log = result.get("execution_log", [])
            error = result.get("error")
            execution_time = result.get("execution_time_ms", 0)

            # Format result
            log_text = "\n".join(execution_log[-10:])  # Last 10 log entries

            status_emoji = "✅" if status == "success" else "❌" if status == "error" else "⏳"

            return CallToolResult(
                content=[
                    TextContent(
                        type="text",
                        text=f"UCI Room Booking {status_emoji} {status.upper()}\n\n"
                           f"Run ID: {run_id}\n"
                           f"Library: {args['library']}\n"
                           f"Date: {args['booking_date']}\n"
                           f"Time: {args['booking_time']} ({args['duration_minutes']} min)\n"
                           f"Room: {args['room_keyword']}\n"
                           f"Execution Time: {execution_time}ms\n\n"
                           f"Execution Log:\n{log_text}" +
                           (f"\n\nError: {error}" if error else "")
                    )
                ]
            )
        else:
            return CallToolResult(
                content=[TextContent(type="text", text=f"API Error: {response.status_code} - {response.text}")],
                isError=True
            )

    except Exception as e:
        return CallToolResult(
            content=[TextContent(type="text", text=f"Booking request failed: {str(e)}")],
            isError=True
        )


async def _extract_workflow_from_video(args: Dict[str, Any]) -> CallToolResult:
    """Extract workflow from video using VLM."""
    video_path = Path(args["video_file_path"])

    # Validate video file exists
    if not video_path.exists():
        return CallToolResult(
            content=[TextContent(type="text", text=f"Video file not found: {video_path}")],
            isError=True
        )

    try:
        # Prepare file upload
        files = {"video": (video_path.name, video_path.read_bytes(), "video/mp4")}
        params = {"workflow_type": args["workflow_type"]}

        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(
                f"{API_BASE_URL}/api/v1/extract-workflow",
                files=files,
                params=params
            )

        if response.status_code == 200:
            result = response.json()
            status = result.get("status", "unknown")
            workflow_type = result.get("workflow_type", "")
            workflow = result.get("workflow")
            execution_time = result.get("execution_time_ms", 0)
            source_video = result.get("source_video", "")
            error = result.get("error")

            if status == "success" and workflow:
                workflow_name = workflow.get("name", "Unknown")
                steps_count = len(workflow.get("steps", []))

                return CallToolResult(
                    content=[
                        TextContent(
                            type="text",
                            text=f"VLM Workflow Extraction ✅ SUCCESS\n\n"
                               f"Video: {source_video}\n"
                               f"Type: {workflow_type}\n"
                               f"Workflow: {workflow_name}\n"
                               f"Steps Extracted: {steps_count}\n"
                               f"Processing Time: {execution_time}ms\n\n"
                               f"Workflow JSON:\n```json\n{json.dumps(workflow, indent=2)}\n```"
                        )
                    ]
                )
            else:
                return CallToolResult(
                    content=[TextContent(type="text", text=f"VLM Extraction Failed: {error or 'Unknown error'}")],
                    isError=True
                )
        else:
            return CallToolResult(
                content=[TextContent(type="text", text=f"API Error: {response.status_code} - {response.text}")],
                isError=True
            )

    except Exception as e:
        return CallToolResult(
            content=[TextContent(type="text", text=f"Video processing failed: {str(e)}")],
            isError=True
        )


async def main():
    """Run the MCP server using stdio transport."""
    import mcp.server.stdio

    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="teachai",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            )
        )


if __name__ == "__main__":
    asyncio.run(main())