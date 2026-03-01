"""
MCP router — uses Grok to pick the right tool and extract args from a
natural-language request, then executes it.
"""

from __future__ import annotations

import json

from openai import OpenAI

from app.core.config import settings
from app.mcp.tools import TOOLS, TOOLS_BY_NAME, Tool


class RoutingError(Exception):
    pass


def _build_prompt(request: str, tools: list[Tool]) -> str:
    tools_desc = json.dumps(
        [
            {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            }
            for t in tools
        ],
        indent=2,
    )
    return (
        f"You are a tool router. Given the user request below, choose the best tool "
        f"from the list and extract the required arguments.\n\n"
        f"Respond ONLY with a JSON object in this exact format:\n"
        f'{{"tool": "<tool_name>", "args": {{<key>: <value>, ...}}}}\n\n'
        f"Available tools:\n{tools_desc}\n\n"
        f"User request: {request}"
    )


def route(request: str, tools: list[Tool] | None = None) -> dict:
    """
    Route a natural-language request to the appropriate tool and return its result.
    """
    if tools is None:
        tools = TOOLS

    client = OpenAI(
        api_key=settings.grok_api_key,
        base_url="https://api.x.ai/v1",
    )

    response = client.chat.completions.create(
        model="grok-beta",
        messages=[{"role": "user", "content": _build_prompt(request, tools)}],
        temperature=0,
    )

    raw = response.choices[0].message.content or ""

    # Strip markdown fences if Grok wraps the JSON
    stripped = raw.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("```")[1]
        if stripped.startswith("json"):
            stripped = stripped[4:]
        stripped = stripped.strip()

    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise RoutingError(f"Grok returned non-JSON: {raw!r}") from exc

    tool_name = payload.get("tool")
    args = payload.get("args", {})

    if not tool_name:
        raise RoutingError(f"Grok response missing 'tool' key: {payload}")

    tool = TOOLS_BY_NAME.get(tool_name)
    if tool is None:
        raise RoutingError(f"Unknown tool '{tool_name}' chosen by Grok")

    return tool.run(args)
