"""
Selenium workflow executor with DOM resolution integration.

Executes semantic workflows by resolving targets to DOM elements at runtime.
"""
import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Generator, Any

from selenium import webdriver
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    ElementClickInterceptedException,
    StaleElementReferenceException
)
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

from .dom_resolver import DOMResolver
from ..models.schemas import (
    SemanticWorkflow, WorkflowStep, ActionType, WaitCondition, ResolvedStep
)

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    """Result of executing a single workflow step."""
    step_index: int
    step: WorkflowStep
    success: bool
    resolved: ResolvedStep | None = None
    error: str | None = None
    screenshot_path: str | None = None
    execution_time_ms: int = 0


class WorkflowExecutor:
    """
    Executes semantic workflows using Selenium with DOM resolution.

    Features:
    - Context manager for driver lifecycle
    - DOM resolver integration
    - Screenshot capture on success/failure
    - Cache loading/saving
    """

    def __init__(
        self,
        headless: bool = False,
        cache_path: str | None = None,
        screenshot_dir: str | Path | None = None,
        timeout: int = 10
    ):
        self.headless = headless
        self.cache_path = cache_path
        self.screenshot_dir = Path(screenshot_dir) if screenshot_dir else None
        self.timeout = timeout
        self.driver: WebDriver | None = None
        self.resolver: DOMResolver | None = None
        self.wait: WebDriverWait | None = None

    def __enter__(self) -> "WorkflowExecutor":
        """Initialize driver and resolver."""
        self._create_driver()
        self.resolver = DOMResolver(self.driver, self.cache_path)
        self.wait = WebDriverWait(self.driver, self.timeout)
        logger.info("[Replay] Workflow executor initialized")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Cleanup driver and save cache."""
        if self.resolver and self.cache_path:
            self.resolver.save_cache(self.cache_path)

        if self.driver:
            self.driver.quit()
            logger.info("[Replay] Driver closed")

    def _create_driver(self) -> None:
        """Create Chrome WebDriver with appropriate options."""
        chrome_options = ChromeOptions()

        if self.headless:
            chrome_options.add_argument("--headless")

        # Standard options for stability
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

        self.driver = webdriver.Chrome(options=chrome_options)
        logger.info(f"[Replay] Chrome driver created (headless: {self.headless})")

    def execute(
        self,
        workflow: SemanticWorkflow,
        screenshot_dir: str | Path | None = None
    ) -> Generator[ExecutionResult, None, None]:
        """
        Execute workflow step by step.

        Args:
            workflow: Semantic workflow to execute
            screenshot_dir: Directory to save screenshots (overrides instance setting)

        Yields:
            ExecutionResult for each step
        """
        if screenshot_dir:
            self.screenshot_dir = Path(screenshot_dir)

        if self.screenshot_dir:
            self.screenshot_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"[Replay] Executing workflow: {workflow.name} ({len(workflow.steps)} steps)")

        for i, step in enumerate(workflow.steps):
            start_time = time.time()
            result = self._execute_step(i, step)
            result.execution_time_ms = int((time.time() - start_time) * 1000)

            # Take screenshot
            if self.screenshot_dir:
                screenshot_name = f"step_{i:03d}_{step.type.value.lower()}"
                if not result.success:
                    screenshot_name += "_FAILED"
                screenshot_path = self.screenshot_dir / f"{screenshot_name}.png"

                try:
                    self.driver.save_screenshot(str(screenshot_path))
                    result.screenshot_path = str(screenshot_path)
                except Exception as e:
                    logger.warning(f"[Replay] Failed to save screenshot: {e}")

            logger.info(
                f"[Replay] Step {i+1}/{len(workflow.steps)}: "
                f"{step.type.value} - {'SUCCESS' if result.success else 'FAILED'} "
                f"({result.execution_time_ms}ms)"
            )

            if result.error:
                logger.error(f"[Replay] Error: {result.error}")

            yield result

            # Stop on failure
            if not result.success:
                logger.error(f"[Replay] Workflow execution stopped at step {i+1}")
                break

        logger.info("[Replay] Workflow execution completed")

    def _execute_step(self, step_index: int, step: WorkflowStep) -> ExecutionResult:
        """Execute a single workflow step."""
        try:
            logger.debug(f"[Replay] Executing step {step_index}: {step}")

            if step.type == ActionType.GOTO:
                self._execute_goto(step)

            elif step.type == ActionType.CLICK:
                resolved = self._resolve_target(step)
                element = resolved.element if hasattr(resolved, 'element') else resolved[0]
                self._click_element(element)

            elif step.type == ActionType.TYPE:
                resolved = self._resolve_target(step)
                element = resolved.element if hasattr(resolved, 'element') else resolved[0]
                self._type_text(element, step.value or "")

            elif step.type == ActionType.SELECT:
                resolved = self._resolve_target(step)
                element = resolved.element if hasattr(resolved, 'element') else resolved[0]
                self._select_option(element, step.value or "")

            elif step.type == ActionType.WAIT:
                self._execute_wait(step)

            elif step.type == ActionType.SCROLL:
                if step.target:
                    resolved = self._resolve_target(step)
                    element = resolved.element if hasattr(resolved, 'element') else resolved[0]
                    self._scroll_to_element(element)
                else:
                    self._scroll_page()

            elif step.type == ActionType.HOVER:
                resolved = self._resolve_target(step)
                element = resolved.element if hasattr(resolved, 'element') else resolved[0]
                self._hover_element(element)

            else:
                raise ValueError(f"Unsupported action type: {step.type}")

            # Handle wait condition if specified
            if step.wait_for:
                self._handle_wait_condition(step.wait_for, step.wait_text, step.timeout_seconds)

            return ExecutionResult(
                step_index=step_index,
                step=step,
                success=True,
                resolved=getattr(resolved, 'resolved_step', None) if 'resolved' in locals() else None
            )

        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            return ExecutionResult(
                step_index=step_index,
                step=step,
                success=False,
                error=error_msg
            )

    def _resolve_target(self, step: WorkflowStep) -> tuple[WebElement, ResolvedStep]:
        """Resolve semantic target to DOM element."""
        if not step.target:
            raise ValueError(f"Step {step.type} requires a target")

        if not self.resolver:
            raise RuntimeError("DOM resolver not initialized")

        return self.resolver.resolve(step.target)

    def _execute_goto(self, step: WorkflowStep) -> None:
        """Execute GOTO action."""
        if not step.url:
            raise ValueError("GOTO step requires URL")

        logger.debug(f"[Replay] Navigating to: {step.url}")
        self.driver.get(step.url)

        # Wait for page load
        self._wait_for_page_load(step.timeout_seconds)

    def _click_element(self, element: WebElement) -> None:
        """Click an element with retry logic."""
        try:
            # Scroll element into view first
            self.driver.execute_script("arguments[0].scrollIntoView(true);", element)
            time.sleep(0.5)  # Allow scroll to complete

            # Try direct click first
            element.click()

        except ElementClickInterceptedException:
            # Try JavaScript click if intercepted
            logger.debug("[Replay] Direct click intercepted, trying JavaScript click")
            self.driver.execute_script("arguments[0].click();", element)

        except Exception as e:
            # Last resort: ActionChains click
            logger.debug(f"[Replay] Standard click failed ({e}), trying ActionChains")
            ActionChains(self.driver).move_to_element(element).click().perform()

    def _type_text(self, element: WebElement, text: str) -> None:
        """Type text into an element."""
        # Clear existing text
        element.clear()

        # Type new text
        element.send_keys(text)

        # Verify text was entered
        actual_value = element.get_attribute("value") or ""
        if actual_value != text:
            logger.warning(f"[Replay] Text verification failed. Expected: '{text}', Actual: '{actual_value}'")

    def _select_option(self, element: WebElement, option_text: str) -> None:
        """Select option from dropdown."""
        select = Select(element)

        # Try to select by visible text first
        try:
            select.select_by_visible_text(option_text)
            return
        except NoSuchElementException:
            pass

        # Try to select by value
        try:
            select.select_by_value(option_text)
            return
        except NoSuchElementException:
            pass

        # Try partial text match
        for option in select.options:
            if option_text.lower() in option.text.lower():
                select.select_by_visible_text(option.text)
                return

        raise NoSuchElementException(f"Could not find option '{option_text}' in dropdown")

    def _scroll_to_element(self, element: WebElement) -> None:
        """Scroll element into view."""
        self.driver.execute_script("arguments[0].scrollIntoView(true);", element)
        time.sleep(0.5)

    def _scroll_page(self, direction: str = "down", pixels: int = 300) -> None:
        """Scroll the page."""
        if direction == "down":
            self.driver.execute_script(f"window.scrollBy(0, {pixels});")
        else:
            self.driver.execute_script(f"window.scrollBy(0, -{pixels});")
        time.sleep(0.5)

    def _hover_element(self, element: WebElement) -> None:
        """Hover over an element."""
        ActionChains(self.driver).move_to_element(element).perform()
        time.sleep(0.5)

    def _execute_wait(self, step: WorkflowStep) -> None:
        """Execute WAIT action."""
        if step.wait_for:
            self._handle_wait_condition(step.wait_for, step.wait_text, step.timeout_seconds)
        else:
            # Simple time-based wait
            time.sleep(step.timeout_seconds)

    def _handle_wait_condition(self, condition: WaitCondition, wait_text: str | None, timeout: float) -> None:
        """Handle different wait conditions."""
        wait = WebDriverWait(self.driver, timeout)

        try:
            if condition == WaitCondition.URL_CHANGE:
                current_url = self.driver.current_url
                wait.until(lambda driver: driver.current_url != current_url)

            elif condition == WaitCondition.ELEMENT_VISIBLE:
                if wait_text:
                    wait.until(EC.visibility_of_element_located((By.XPATH, f"//*[contains(text(), '{wait_text}')]")))

            elif condition == WaitCondition.ELEMENT_CLICKABLE:
                if wait_text:
                    wait.until(EC.element_to_be_clickable((By.XPATH, f"//*[contains(text(), '{wait_text}')]")))

            elif condition == WaitCondition.TEXT_PRESENT:
                if wait_text:
                    wait.until(EC.text_to_be_present_in_element((By.TAG_NAME, "body"), wait_text))

            elif condition == WaitCondition.PAGE_LOAD:
                self._wait_for_page_load(timeout)

        except TimeoutException:
            logger.warning(f"[Replay] Wait condition '{condition}' timed out after {timeout}s")

    def _wait_for_page_load(self, timeout: float) -> None:
        """Wait for page to finish loading."""
        WebDriverWait(self.driver, timeout).until(
            lambda driver: driver.execute_script("return document.readyState") == "complete"
        )


def execute_workflow_file(
    workflow_path: str | Path,
    screenshot_dir: str | Path | None = None,
    headless: bool = False,
    cache_path: str | None = None
) -> list[ExecutionResult]:
    """
    Convenience function to execute a workflow from file.

    Args:
        workflow_path: Path to workflow JSON file
        screenshot_dir: Directory to save screenshots
        headless: Run browser in headless mode
        cache_path: Path to selector cache file

    Returns:
        List of ExecutionResult for each step
    """
    import json
    from ..models.schemas import SemanticWorkflow

    # Load workflow from file
    with open(workflow_path, 'r') as f:
        workflow_data = json.load(f)

    workflow = SemanticWorkflow(**workflow_data)

    # Execute workflow
    results = []
    with WorkflowExecutor(headless=headless, cache_path=cache_path) as executor:
        for result in executor.execute(workflow, screenshot_dir):
            results.append(result)

    return results


@contextmanager
def workflow_executor(
    headless: bool = False,
    cache_path: str | None = None
) -> Generator[WorkflowExecutor, None, None]:
    """Context manager for WorkflowExecutor."""
    with WorkflowExecutor(headless=headless, cache_path=cache_path) as executor:
        yield executor