"""
JSON parsing and validation utilities for VLM output.

Handles common issues with LLM-generated JSON like markdown blocks,
trailing commas, comments, and unquoted keys.
"""
import json
import re
import logging
from typing import Any

logger = logging.getLogger(__name__)


def extract_json(text: str) -> str:
    """
    Extract JSON content from text that may contain markdown code blocks.

    Args:
        text: Raw text that may contain JSON

    Returns:
        Extracted JSON string
    """
    # Remove markdown code blocks
    text = re.sub(r'```json\s*', '', text)
    text = re.sub(r'```\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'^```.*$', '', text, flags=re.MULTILINE)

    # Find JSON boundaries
    text = text.strip()

    # Try to find object boundaries
    if '{' in text and '}' in text:
        start = text.find('{')
        # Find the last closing brace
        end = text.rfind('}') + 1
        if start < end:
            return text[start:end]

    # Try to find array boundaries
    if '[' in text and ']' in text:
        start = text.find('[')
        end = text.rfind(']') + 1
        if start < end:
            return text[start:end]

    return text


def parse_json_safe(text: str) -> dict | list | None:
    """
    Safely parse JSON from VLM output with error recovery.

    Args:
        text: Raw text containing JSON

    Returns:
        Parsed JSON object/array or None if parsing fails
    """
    # Try direct parsing first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Extract JSON content
    json_text = extract_json(text)

    # Try parsing extracted content
    try:
        return json.loads(json_text)
    except json.JSONDecodeError:
        pass

    # Try to fix common JSON errors
    try:
        fixed_json = fix_common_json_errors(json_text)
        return json.loads(fixed_json)
    except json.JSONDecodeError as e:
        logger.error(f"[JSON] Failed to parse JSON after all attempts: {e}")
        logger.debug(f"[JSON] Problematic text: {json_text[:500]}...")
        return None


def fix_common_json_errors(json_str: str) -> str:
    """
    Fix common JSON formatting errors from VLM output.

    Args:
        json_str: JSON string with potential errors

    Returns:
        Fixed JSON string
    """
    # Remove comments (// and /* */)
    json_str = re.sub(r'//.*?$', '', json_str, flags=re.MULTILINE)
    json_str = re.sub(r'/\*.*?\*/', '', json_str, flags=re.DOTALL)

    # Fix single quotes to double quotes (be careful with apostrophes)
    json_str = re.sub(r"'([^']*)':", r'"\1":', json_str)  # Keys
    json_str = re.sub(r":\s*'([^']*)'", r': "\1"', json_str)  # Values

    # Fix unquoted keys
    json_str = re.sub(r'(\w+):', r'"\1":', json_str)

    # Remove trailing commas
    json_str = re.sub(r',\s*}', '}', json_str)
    json_str = re.sub(r',\s*]', ']', json_str)

    # Fix multiple spaces
    json_str = re.sub(r'\s+', ' ', json_str)

    # Fix newlines in strings (preserve intended newlines)
    json_str = json_str.replace('\n', '\\n')

    return json_str.strip()




def create_example_workflow() -> dict:
    """Create an example workflow for testing and validation."""
    return {
        "name": "Login Example",
        "description": "Example login workflow for validation testing",
        "start_url": "https://example.com/login",
        "steps": [
            {
                "type": "GOTO",
                "description": "Navigate to login page",
                "url": "https://example.com/login"
            },
            {
                "type": "CLICK",
                "description": "Click email input field",
                "target": {
                    "label_hint": "Email",
                    "role_hint": "input",
                    "placeholder_hint": "Enter your email"
                }
            },
            {
                "type": "TYPE",
                "description": "Enter email address",
                "target": {
                    "label_hint": "Email",
                    "role_hint": "input"
                },
                "value": "user@example.com"
            },
            {
                "type": "CLICK",
                "description": "Click login button",
                "target": {
                    "text_hint": "Log In",
                    "role_hint": "button"
                },
                "wait_for": "URL_CHANGE",
                "timeout_seconds": 10.0
            }
        ]
    }


def sanitize_for_vlm_repair(json_data: dict) -> dict:
    """
    Sanitize workflow data for VLM repair attempts.

    Removes any technical selectors that may have been accidentally included.

    Args:
        json_data: Workflow data that may contain technical selectors

    Returns:
        Sanitized workflow data
    """
    sanitized = json.deepcopy(json_data) if hasattr(json, 'deepcopy') else json.loads(json.dumps(json_data))

    # Remove any technical selector fields that shouldn't be there
    forbidden_fields = [
        "css_selector", "xpath", "selector", "resolved_css_selector",
        "css_selector_hint", "xpath_hint"
    ]

    def remove_forbidden_fields(obj):
        if isinstance(obj, dict):
            for field in forbidden_fields:
                obj.pop(field, None)
            for value in obj.values():
                remove_forbidden_fields(value)
        elif isinstance(obj, list):
            for item in obj:
                remove_forbidden_fields(item)

    remove_forbidden_fields(sanitized)
    return sanitized