"""
DOM Grounding Resolver - translates semantic targets to DOM selectors.

This is the core component that bridges semantic descriptions from the VLM
to actual DOM elements that Selenium can interact with.
"""
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    StaleElementReferenceException
)
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from ..models.schemas import SemanticTarget, ResolvedStep, WorkflowStep

logger = logging.getLogger(__name__)

# Score weights for different matching strategies
WEIGHTS = {
    "exact_text": 1.0,
    "aria_label": 0.95,
    "label_for": 0.9,
    "placeholder": 0.85,
    "role_match": 0.3,
    "partial_text": 0.7,
    "fuzzy_text": 0.5,
    "visual_match": 0.4,
}

# Role-based selector mapping
ROLE_SELECTORS = {
    "button": ["button", "input[type='button']", "input[type='submit']", "[role='button']"],
    "link": ["a", "[role='link']"],
    "input": ["input:not([type='button']):not([type='submit'])", "textarea"],
    "dropdown": ["select", "[role='combobox']", "[role='listbox']"],
    "checkbox": ["input[type='checkbox']", "[role='checkbox']"],
    "radio": ["input[type='radio']", "[role='radio']"],
    "textbox": ["input[type='text']", "input[type='email']", "input[type='password']", "textarea"],
}


@dataclass
class ScoredElement:
    """Element with confidence score and matching information."""
    element: WebElement
    score: float
    selector: str
    selector_type: str  # "css" or "xpath"
    match_reasons: list[str]

    def __str__(self) -> str:
        return f"{self.selector} (score: {self.score:.2f}, reasons: {', '.join(self.match_reasons)})"


class DOMResolver:
    """
    Resolves semantic targets to actual DOM elements at runtime.

    Uses multiple strategies to find elements based on semantic descriptions:
    1. Exact text match
    2. aria-label match
    3. Label association (label-for)
    4. Placeholder match
    5. Role + text combination
    6. Fuzzy/partial text match
    """

    def __init__(self, driver: WebDriver, cache_file: str | None = None):
        self.driver = driver
        self.cache: dict[str, dict] = {}
        self.cache_file = Path(cache_file) if cache_file else None
        self.wait = WebDriverWait(driver, 10)

        if self.cache_file and self.cache_file.exists():
            self.load_cache(self.cache_file)

    def resolve(self, target: SemanticTarget, wait: bool = True) -> tuple[WebElement, ResolvedStep]:
        """
        Resolve semantic target to DOM element.

        Args:
            target: Semantic description of the target element
            wait: Whether to wait for element to be present

        Returns:
            Tuple of (WebElement, ResolvedStep with resolution info)

        Raises:
            NoSuchElementException: If element cannot be found
        """
        logger.info(f"[Resolver] Resolving target: {target}")

        # Check cache first
        cache_key = self._create_cache_key(target)
        if cache_key in self.cache:
            cached = self.cache[cache_key]
            try:
                element = self.driver.find_element(By.CSS_SELECTOR, cached["selector"])
                logger.info(f"[Resolver] Found cached selector: {cached['selector']}")
                return element, ResolvedStep(
                    original_step=WorkflowStep(type="CLICK", description="cached", target=target),
                    resolved_selector=cached["selector"],
                    selector_type=cached["type"],
                    confidence=cached["confidence"],
                    alternatives=cached.get("alternatives", [])
                )
            except NoSuchElementException:
                # Cache miss, remove stale entry
                del self.cache[cache_key]
                logger.info(f"[Resolver] Cached selector stale, removed from cache")

        # Find candidate elements using multiple strategies
        candidates = self._find_candidates(target)

        if not candidates:
            raise NoSuchElementException(f"No elements found matching target: {target}")

        # Sort by confidence score
        candidates.sort(key=lambda x: x.score, reverse=True)
        best_candidate = candidates[0]

        logger.info(f"[Resolver] Best match: {best_candidate}")

        # Cache the result
        self.cache[cache_key] = {
            "selector": best_candidate.selector,
            "type": best_candidate.selector_type,
            "confidence": best_candidate.score,
            "alternatives": [c.selector for c in candidates[1:6]]  # Top 5 alternatives
        }

        if wait:
            # Wait for element to be clickable/interactable
            try:
                self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, best_candidate.selector)))
            except TimeoutException:
                logger.warning(f"[Resolver] Element not clickable within timeout: {best_candidate.selector}")

        resolved_step = ResolvedStep(
            original_step=WorkflowStep(type="CLICK", description="resolved", target=target),
            resolved_selector=best_candidate.selector,
            selector_type=best_candidate.selector_type,
            confidence=best_candidate.score,
            alternatives=[c.selector for c in candidates[1:6]]
        )

        return best_candidate.element, resolved_step

    def _find_candidates(self, target: SemanticTarget) -> list[ScoredElement]:
        """Find all candidate elements matching the semantic target."""
        candidates: list[ScoredElement] = []

        # Strategy 1: Exact text match
        if target.text_hint:
            candidates.extend(self._find_by_text(target.text_hint, exact=True))

        # Strategy 2: aria-label match
        if target.label_hint:
            candidates.extend(self._find_by_aria_label(target.label_hint))

        # Strategy 3: Label association
        if target.label_hint:
            candidates.extend(self._find_by_label_for(target.label_hint))

        # Strategy 4: Placeholder match
        if target.placeholder_hint:
            candidates.extend(self._find_by_placeholder(target.placeholder_hint))

        # Strategy 5: Role-based search
        if target.role_hint:
            candidates.extend(self._find_by_role(target.role_hint, target.text_hint))

        # Strategy 6: Partial text match
        if target.text_hint:
            candidates.extend(self._find_by_text(target.text_hint, exact=False))

        # Remove duplicates (same element found by different strategies)
        unique_candidates = []
        seen_elements = set()

        for candidate in candidates:
            try:
                element_id = candidate.element._id  # Selenium internal ID
                if element_id not in seen_elements:
                    seen_elements.add(element_id)
                    unique_candidates.append(candidate)
            except StaleElementReferenceException:
                continue

        return unique_candidates

    def _find_by_text(self, text: str, exact: bool = True) -> list[ScoredElement]:
        """Find elements by visible text content."""
        candidates = []

        if exact:
            # Find by exact text match
            xpath = f"//*[normalize-space(text())='{text}' or @value='{text}']"
            weight = WEIGHTS["exact_text"]
            reason = f"exact text '{text}'"
        else:
            # Find by partial text match
            xpath = f"//*[contains(normalize-space(text()), '{text}') or contains(@value, '{text}')]"
            weight = WEIGHTS["partial_text"]
            reason = f"partial text '{text}'"

        try:
            elements = self.driver.find_elements(By.XPATH, xpath)
            for element in elements:
                selector = self._generate_selector(element)
                if selector:
                    candidates.append(ScoredElement(
                        element=element,
                        score=weight,
                        selector=selector,
                        selector_type="css",
                        match_reasons=[reason]
                    ))
        except Exception as e:
            logger.debug(f"[Resolver] Text search failed: {e}")

        return candidates

    def _find_by_aria_label(self, label: str) -> list[ScoredElement]:
        """Find elements by aria-label attribute."""
        candidates = []

        try:
            # Exact aria-label match
            elements = self.driver.find_elements(By.XPATH, f"//*[@aria-label='{label}']")
            for element in elements:
                selector = self._generate_selector(element)
                if selector:
                    candidates.append(ScoredElement(
                        element=element,
                        score=WEIGHTS["aria_label"],
                        selector=selector,
                        selector_type="css",
                        match_reasons=[f"aria-label '{label}'"]
                    ))

            # Partial aria-label match
            elements = self.driver.find_elements(By.XPATH, f"//*[contains(@aria-label, '{label}')]")
            for element in elements:
                selector = self._generate_selector(element)
                if selector:
                    candidates.append(ScoredElement(
                        element=element,
                        score=WEIGHTS["aria_label"] * 0.8,
                        selector=selector,
                        selector_type="css",
                        match_reasons=[f"partial aria-label '{label}'"]
                    ))

        except Exception as e:
            logger.debug(f"[Resolver] Aria-label search failed: {e}")

        return candidates

    def _find_by_label_for(self, label_text: str) -> list[ScoredElement]:
        """Find input elements associated with labels."""
        candidates = []

        try:
            # Find labels with matching text
            label_xpath = f"//label[normalize-space(text())='{label_text}' or contains(normalize-space(text()), '{label_text}')]"
            labels = self.driver.find_elements(By.XPATH, label_xpath)

            for label in labels:
                # Check if label has 'for' attribute
                for_attr = label.get_attribute("for")
                if for_attr:
                    # Find element with matching ID
                    try:
                        element = self.driver.find_element(By.ID, for_attr)
                        selector = f"#{for_attr}"
                        candidates.append(ScoredElement(
                            element=element,
                            score=WEIGHTS["label_for"],
                            selector=selector,
                            selector_type="css",
                            match_reasons=[f"label for '{label_text}'"]
                        ))
                    except NoSuchElementException:
                        continue

                # Check if input is nested inside label
                try:
                    nested_input = label.find_element(By.TAG_NAME, "input")
                    selector = self._generate_selector(nested_input)
                    if selector:
                        candidates.append(ScoredElement(
                            element=nested_input,
                            score=WEIGHTS["label_for"] * 0.9,
                            selector=selector,
                            selector_type="css",
                            match_reasons=[f"input inside label '{label_text}'"]
                        ))
                except NoSuchElementException:
                    continue

        except Exception as e:
            logger.debug(f"[Resolver] Label search failed: {e}")

        return candidates

    def _find_by_placeholder(self, placeholder: str) -> list[ScoredElement]:
        """Find input elements by placeholder text."""
        candidates = []

        try:
            # Exact placeholder match
            elements = self.driver.find_elements(By.XPATH, f"//*[@placeholder='{placeholder}']")
            for element in elements:
                selector = self._generate_selector(element)
                if selector:
                    candidates.append(ScoredElement(
                        element=element,
                        score=WEIGHTS["placeholder"],
                        selector=selector,
                        selector_type="css",
                        match_reasons=[f"placeholder '{placeholder}'"]
                    ))

            # Partial placeholder match
            elements = self.driver.find_elements(By.XPATH, f"//*[contains(@placeholder, '{placeholder}')]")
            for element in elements:
                selector = self._generate_selector(element)
                if selector:
                    candidates.append(ScoredElement(
                        element=element,
                        score=WEIGHTS["placeholder"] * 0.8,
                        selector=selector,
                        selector_type="css",
                        match_reasons=[f"partial placeholder '{placeholder}'"]
                    ))

        except Exception as e:
            logger.debug(f"[Resolver] Placeholder search failed: {e}")

        return candidates

    def _find_by_role(self, role: str, text_hint: str | None = None) -> list[ScoredElement]:
        """Find elements by semantic role."""
        candidates = []
        role_lower = role.lower()

        if role_lower not in ROLE_SELECTORS:
            return candidates

        try:
            for selector in ROLE_SELECTORS[role_lower]:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)

                for element in elements:
                    score = WEIGHTS["role_match"]
                    reasons = [f"role '{role}'"]

                    # Boost score if text also matches
                    if text_hint:
                        element_text = element.get_attribute("textContent") or ""
                        element_value = element.get_attribute("value") or ""

                        if text_hint.lower() in element_text.lower() or text_hint.lower() in element_value.lower():
                            score += WEIGHTS["partial_text"]
                            reasons.append(f"text contains '{text_hint}'")

                    generated_selector = self._generate_selector(element)
                    if generated_selector:
                        candidates.append(ScoredElement(
                            element=element,
                            score=score,
                            selector=generated_selector,
                            selector_type="css",
                            match_reasons=reasons
                        ))

        except Exception as e:
            logger.debug(f"[Resolver] Role search failed: {e}")

        return candidates

    def _generate_selector(self, element: WebElement) -> str | None:
        """
        Generate a CSS selector for the element.

        Priority order:
        1. ID (most reliable)
        2. Class combination
        3. Data attributes
        4. Text content (for buttons/links)
        5. nth-child (last resort)
        """
        try:
            # Strategy 1: ID selector
            element_id = element.get_attribute("id")
            if element_id and element_id.strip():
                return f"#{element_id}"

            # Strategy 2: Class combination
            class_names = element.get_attribute("class")
            if class_names:
                classes = [c.strip() for c in class_names.split() if c.strip()]
                if classes:
                    class_selector = "." + ".".join(classes)
                    # Verify uniqueness
                    if len(self.driver.find_elements(By.CSS_SELECTOR, class_selector)) == 1:
                        return class_selector

            # Strategy 3: Data attributes
            data_testid = element.get_attribute("data-testid")
            if data_testid:
                return f"[data-testid='{data_testid}']"

            data_cy = element.get_attribute("data-cy")
            if data_cy:
                return f"[data-cy='{data_cy}']"

            # Strategy 4: Text-based selector for buttons/links
            tag_name = element.tag_name.lower()
            if tag_name in ["button", "a"]:
                text_content = element.get_attribute("textContent")
                if text_content and text_content.strip():
                    text = text_content.strip()
                    xpath = f"//{tag_name}[normalize-space(text())='{text}']"
                    # Convert to CSS if unique
                    matching_elements = self.driver.find_elements(By.XPATH, xpath)
                    if len(matching_elements) == 1:
                        return f"{tag_name}:contains('{text}')"  # Note: CSS4 selector

            # Strategy 5: nth-child (last resort)
            parent = element.find_element(By.XPATH, "..")
            siblings = parent.find_elements(By.XPATH, f".//{element.tag_name}")
            for i, sibling in enumerate(siblings, 1):
                if sibling._id == element._id:
                    parent_selector = self._generate_selector(parent) or "body"
                    return f"{parent_selector} > {element.tag_name}:nth-child({i})"

        except Exception as e:
            logger.debug(f"[Resolver] Selector generation failed: {e}")

        return None

    def _create_cache_key(self, target: SemanticTarget) -> str:
        """Create a cache key from semantic target."""
        key_parts = [
            target.text_hint or "",
            target.role_hint or "",
            target.label_hint or "",
            target.placeholder_hint or "",
            target.page_context or "",
        ]
        return "|".join(key_parts).lower()

    def save_cache(self, filepath: str | Path) -> None:
        """Save resolved selectors cache to file."""
        try:
            with open(filepath, 'w') as f:
                json.dump(self.cache, f, indent=2)
            logger.info(f"[Resolver] Saved cache with {len(self.cache)} entries to {filepath}")
        except Exception as e:
            logger.error(f"[Resolver] Failed to save cache: {e}")

    def load_cache(self, filepath: str | Path) -> None:
        """Load resolved selectors cache from file."""
        try:
            with open(filepath, 'r') as f:
                self.cache = json.load(f)
            logger.info(f"[Resolver] Loaded cache with {len(self.cache)} entries from {filepath}")
        except Exception as e:
            logger.warning(f"[Resolver] Failed to load cache: {e}")
            self.cache = {}