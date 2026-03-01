"""
VLM prompts for semantic workflow extraction.

CRITICAL: These prompts enforce semantic descriptions only (NO CSS/XPath).
The VLM describes WHAT the user intended, not HOW to implement it.
"""

# System prompt with strict rules against technical selectors
SYSTEM_PROMPT = """You are a web workflow extraction expert. Your job is to analyze video frames showing a user interacting with a website and extract a semantic workflow describing their actions.

CRITICAL RULES - NEVER VIOLATE THESE:

NEVER DO THIS:
- NEVER invent CSS selectors like "#submit-btn", ".form-input", "div.container > button"
- NEVER guess XPath like "//div[@class='container']", "//button[text()='Submit']"
- NEVER use technical DOM paths like "div:nth-child(4)", "input[type='email']"
- NEVER use HTML element names as identifiers like "<button>", "<input>"
- NEVER create selectors based on assumed class names or IDs

ALWAYS DO THIS:
- Describe elements using VISIBLE TEXT that users can see
- Use accessibility semantics (button labels, field labels, placeholder text)
- Reference elements by PURPOSE and MEANING, not technical implementation
- Describe WHAT the user intended to interact with, not HOW to find it technically
- Focus on the semantic intent behind each action

GOOD EXAMPLES (Semantic Descriptions):
✅ "button labeled 'Submit Order'"
✅ "text input with label 'Email Address'"
✅ "dropdown menu labeled 'Select Country'"
✅ "link with text 'View Details'"
✅ "search box with placeholder 'Search products...'"
✅ "checkbox next to 'I agree to terms'"
✅ "blue 'Add to Cart' button below the price"
✅ "password field in the login form"
✅ "navigation menu item 'Products'"

BAD EXAMPLES (Technical - NEVER USE):
❌ "#submit-btn"
❌ ".form-input"
❌ "div.container > button:first-child"
❌ "input[type='email']"
❌ "//button[@class='primary']"
❌ "button:nth-child(2)"
❌ "#email-field"

WORKFLOW OUTPUT FORMAT:
You must return a JSON object with this exact structure compatible with Selenium automation:

{
    "name": "Brief descriptive name for the workflow",
    "description": "What this workflow accomplishes",
    "start_url": "URL where the workflow begins",
    "category": "booking",
    "tags": ["uci", "library", "booking"],
    "parameters": [
        {
            "key": "library",
            "description": "Library location",
            "example": "Gateway Study Center",
            "required": true,
            "input_type": "text"
        },
        {
            "key": "room_keyword",
            "description": "Room identifier",
            "example": "2107",
            "required": true,
            "input_type": "text"
        }
        // ... include all parameters used in steps
    ],
    "steps": [
        {
            "type": "GOTO|CLICK|TYPE|SELECT|WAIT|SCREENSHOT",
            "description": "Human-readable description of what this step does",
            "target_text_hint": "Visible text on element (use {{variable}} for dynamic values)",
            "target_semantic": "Semantic label like 'Location', 'Full Name', 'Email'",
            "value": "{{variable_name}} for dynamic values or static text",
            "url": "URL for GOTO steps",
            "until_text_visible": "Text to wait for (for WAIT steps)",
            "seconds": 1.0
        }
    ]
}

CRITICAL SELENIUM TEMPLATE RULES:
- Use target_text_hint for visible text on buttons/links
- Use target_semantic for form field labels (like "Full Name", "Email", "Location")
- Use {{library}} for location/library names
- Use {{room_keyword}} for room identifiers
- Use {{booking_time}} for time slots
- Use {{full_name}} for person names
- Use {{email}} for email addresses
- Use {{affiliation}} for affiliation selections
- Use {{purpose_for_reservation_covid_19}} for reservation purposes
- Include parameters section with all variables used
- Use until_text_visible for WAIT steps that wait for text to appear
- Use seconds field for WAIT steps that wait a specific duration

EXAMPLE step with placeholders:
{
    "type": "CLICK",
    "description": "Select the study room",
    "target_text_hint": "{{room_keyword}}"
}

ACTION TYPES:
- GOTO: Navigate to a URL
- CLICK: Click on an element
- TYPE: Type text into an input field
- SELECT: Select an option from a dropdown
- WAIT: Wait for a condition to be met
- SCROLL: Scroll to bring an element into view
- HOVER: Hover over an element

SELENIUM FIELD GUIDELINES:
- Use target_text_hint for buttons/links with visible text (use {{variable}} for dynamic values)
- Use target_semantic for form field labels like "Full Name", "Email", "Location"
- Use until_text_visible for WAIT steps that wait for specific text to appear
- Use seconds for WAIT steps that wait a specific duration
- Include all template variables in the parameters section
- Do NOT use nested target objects - use flat field structure

Remember: Your job is to describe the user's INTENT, not to reverse-engineer the DOM structure."""

def create_extraction_prompt(num_frames: int) -> tuple[str, str]:
    """
    Create system and user prompts for workflow extraction.

    Args:
        num_frames: Number of keyframes being analyzed

    Returns:
        Tuple of (system_prompt, user_prompt)
    """
    user_prompt = f"""Analyze these {num_frames} keyframes from a screen recording to extract the semantic workflow.

The frames show a user interacting with a website. Your task is to:

1. Identify the sequence of user actions (clicks, typing, navigation)
2. Describe each action semantically using visible text and element roles
3. Create a complete workflow that could be replayed on the same website

Focus on:
- What buttons/links the user clicked (use visible text)
- What text they typed into which fields (use field labels)
- What dropdowns they selected from (use dropdown labels)
- The order and intent of actions

IMPORTANT:
- Describe elements by what users can SEE and UNDERSTAND
- Never guess technical selectors or DOM structure
- Use semantic descriptions that would make sense to any human user

Return the workflow as a JSON object following the specified format."""

    return SYSTEM_PROMPT, user_prompt


def create_repair_prompt(errors: list[str], previous_output: str) -> tuple[str, str]:
    """
    Create prompts for repairing invalid workflow JSON.

    Args:
        errors: List of validation errors found
        previous_output: The invalid JSON output that needs repair

    Returns:
        Tuple of (system_prompt, user_prompt)
    """
    repair_system = SYSTEM_PROMPT + """

REPAIR MODE: The previous output had validation errors. Fix them while maintaining semantic descriptions.
Do not add technical selectors to fix errors - fix the JSON structure and required fields only."""

    error_list = "\n".join(f"- {error}" for error in errors)

    repair_user = f"""The previous workflow extraction had these validation errors:

{error_list}

Previous output:
```json
{previous_output}
```

Please fix these errors and return a corrected JSON workflow. Maintain all semantic descriptions - only fix the structural issues.

Requirements:
- Fix any JSON syntax errors
- Ensure required fields are present
- Validate action types are correct
- Keep all semantic target descriptions as-is
- Do not add CSS selectors or XPath"""

    return repair_system, repair_user


# Additional prompts for specific scenarios
PROMPTS = {
    "login_workflow": {
        "context": "This appears to be a login workflow. Focus on email/username fields, password fields, and login buttons.",
        "hints": "Look for input fields with labels like 'Email', 'Username', 'Password' and buttons with text like 'Sign In', 'Login', 'Log In'."
    },

    "ecommerce_workflow": {
        "context": "This appears to be an e-commerce workflow. Focus on product selection, cart operations, and checkout.",
        "hints": "Look for 'Add to Cart' buttons, quantity selectors, checkout buttons, and form fields for shipping/payment."
    },

    "form_submission": {
        "context": "This appears to be a form submission workflow. Focus on input fields, dropdowns, and submit buttons.",
        "hints": "Identify form fields by their labels, placeholder text, and required field indicators."
    },

    "navigation_workflow": {
        "context": "This appears to be a navigation-heavy workflow. Focus on menu items, links, and page transitions.",
        "hints": "Look for navigation menus, breadcrumbs, and link text to understand the user's path through the site."
    }
}


def get_contextual_prompt(workflow_type: str | None = None) -> str:
    """
    Get additional context for specific workflow types.

    Args:
        workflow_type: Type of workflow (login_workflow, ecommerce_workflow, etc.)

    Returns:
        Additional context string to append to user prompt
    """
    if workflow_type and workflow_type in PROMPTS:
        prompt_data = PROMPTS[workflow_type]
        return f"\nContext: {prompt_data['context']}\nHints: {prompt_data['hints']}"

    return ""


def validate_semantic_output(output_text: str) -> list[str]:
    """
    Validate that VLM output contains only semantic descriptions.

    Args:
        output_text: Raw VLM output text

    Returns:
        List of validation warnings for technical selectors found
    """
    warnings = []

    # Check for common technical selector patterns
    technical_patterns = [
        r'#[\w-]+',  # CSS IDs like #submit-btn
        r'\.[\w-]+\s*{',  # CSS classes in context like .form-input {
        r'input\[type=',  # CSS attribute selectors
        r'//\w+\[',  # XPath expressions
        r'div\s*>\s*button',  # CSS child selectors
        r'nth-child\(',  # CSS nth-child selectors
        r'\.[\w-]+\s*>',  # CSS class with child selector
    ]

    import re
    for pattern in technical_patterns:
        if re.search(pattern, output_text):
            warnings.append(f"Found potential technical selector pattern: {pattern}")

    # Check for common technical keywords
    technical_keywords = ['css', 'xpath', 'selector', 'nth-child', 'querySelector']
    text_lower = output_text.lower()
    for keyword in technical_keywords:
        if keyword in text_lower:
            warnings.append(f"Found technical keyword: {keyword}")

    return warnings
