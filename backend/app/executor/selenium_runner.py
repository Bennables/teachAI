from __future__ import annotations

import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Optional, Union

from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.select import Select
from selenium.webdriver.support.ui import WebDriverWait

from app.core.config import settings
from app.core.storage import add_log, get_run, save_run, update_run
from app.models.schemas import (
    RunStatus,
    Step,
    WorkflowTemplate,
)

StatusCallback = Callable[[dict[str, Any]], None]

_PLACEHOLDER_PATTERN = re.compile(r"{{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*}}")
_UCI_AUTH_DOMAINS = ("webauth.uci.edu", "login.uci.edu")
_DEFAULT_ARTIFACTS_DIR = "artifacts"


class WorkflowRunner:
    """
    Executes a workflow template with Selenium.

    Designed for UCI demo reliability first:
    - UCI auth-domain pause detection
    - Multi-strategy element finding
    - Screenshot artifact capture after every step
    - Real-time status callback events
    """

    def __init__(
        self,
        run_id: str,
        workflow_id: str,
        status_callback: Optional[StatusCallback] = None,
        artifacts_root: Optional[Union[str, Path]] = None,
    ) -> None:
        self.run_id = run_id
        self.workflow_id = workflow_id
        self.status_callback = status_callback
        self.driver: Optional[webdriver.Chrome] = None
        self._paused_for_auth = False

        root = Path(artifacts_root or _DEFAULT_ARTIFACTS_DIR)
        self.artifacts_dir = root / run_id
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

    def run(self, workflow: WorkflowTemplate, params: dict[str, Any]) -> None:
        """
        Execute the workflow from the current run checkpoint.

        If authentication redirects to known UCI auth domains, execution pauses
        with WAITING_FOR_AUTH so it can be resumed later.
        """
        run_state = get_run(self.run_id)
        if run_state is None:
            run_state = save_run(
                run_id=self.run_id,
                workflow_id=self.workflow_id,
                status=RunStatus.QUEUED,
                current_step=0,
                total_steps=len(workflow.steps),
            )

        start_step = run_state.current_step
        try:
            self._paused_for_auth = False
            if self.driver is None:
                self._setup_driver()
            self._set_status(
                status=RunStatus.RUNNING,
                current_step=start_step,
                message="Workflow run started",
            )

            for step_index in range(start_step, len(workflow.steps)):
                original_step = workflow.steps[step_index]
                self._set_status(
                    status=RunStatus.RUNNING,
                    current_step=step_index,
                    message=f"Starting step {step_index}: {original_step.description}",
                    step_index=step_index,
                )

                resolved_step = self._substitute_step_placeholders(original_step, params)
                self._execute_step(resolved_step)

                screenshot_path = self._take_screenshot(f"step_{step_index}.png")
                self._set_status(
                    status=RunStatus.RUNNING,
                    current_step=step_index + 1,
                    message=f"Completed step {step_index}",
                    step_index=step_index,
                    screenshot_path=screenshot_path,
                )

                if self._is_uci_auth_page():
                    auth_shot = self._take_screenshot(f"step_{step_index}_auth.png")
                    self._paused_for_auth = True
                    self._set_status(
                        status=RunStatus.WAITING_FOR_AUTH,
                        current_step=step_index + 1,
                        message=(
                            "Paused for authentication on UCI login page. "
                            "Complete login and resume."
                        ),
                        step_index=step_index,
                        screenshot_path=auth_shot,
                    )
                    return

            self._set_status(
                status=RunStatus.SUCCEEDED,
                current_step=len(workflow.steps),
                message="Workflow completed successfully",
            )
        except Exception as exc:  # noqa: BLE001
            error_shot = self._safe_error_screenshot()
            self._set_status(
                status=RunStatus.FAILED,
                current_step=get_run(self.run_id).current_step if get_run(self.run_id) else 0,
                message=f"Workflow failed: {exc}",
                level="error",
                screenshot_path=error_shot,
            )
            raise
        finally:
            if self.driver is not None and not self._paused_for_auth:
                self.driver.quit()
                self.driver = None

    def _setup_driver(self) -> None:
        options = webdriver.ChromeOptions()
        if settings.selenium_headless:
            options.add_argument("--headless=new")
        options.add_argument("--start-maximized")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        # Use Selenium's built-in driver management (avoids webdriver_manager path bugs)
        self.driver = webdriver.Chrome(options=options)
        self.driver.implicitly_wait(3)

    def _execute_step(self, step: Step) -> None:
        if self.driver is None:
            raise RuntimeError("WebDriver is not initialized")

        if step.type == "GOTO":
            self.driver.get(step.url)
            self._wait_for_page_ready(timeout=max(5, settings.selenium_timeout))
            return

        if step.type == "CLICK":
            element = self._find_element(step)
            self.driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});", element
            )
            element.click()
            self._wait_for_page_ready(timeout=3)
            return

        if step.type == "TYPE":
            element = self._find_element(step)
            self.driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});", element
            )
            if step.clear_first:
                element.clear()
            element.send_keys(step.value)
            return

        if step.type == "SELECT":
            element = self._find_element(step)
            self.driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});", element
            )
            if element.tag_name.lower() == "select":
                select = Select(element)
                try:
                    select.select_by_visible_text(step.value)
                except NoSuchElementException:
                    select.select_by_value(step.value)
            else:
                element.click()
                element.send_keys(step.value)
                element.send_keys(Keys.ENTER)
            return

        if step.type == "WAIT":
            if step.until_selector:
                WebDriverWait(self.driver, 30).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, step.until_selector))
                )
            elif step.until_url_contains:
                WebDriverWait(self.driver, 30).until(
                    EC.url_contains(step.until_url_contains)
                )
            elif step.until_text_visible:
                WebDriverWait(self.driver, 30).until(
                    EC.text_to_be_present_in_element(
                        (By.TAG_NAME, "body"), step.until_text_visible
                    )
                )
            elif step.seconds is not None:
                time.sleep(step.seconds)
            else:
                time.sleep(0.5)
            return

        if step.type == "SCROLL":
            if step.target_selector:
                target = self.driver.find_element(By.CSS_SELECTOR, step.target_selector)
                self.driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'center'});", target
                )
            else:
                pixels = step.pixels if step.direction == "down" else -step.pixels
                self.driver.execute_script("window.scrollBy(0, arguments[0]);", pixels)
            return

        if step.type == "SCREENSHOT":
            self._take_screenshot(step.filename)
            return

        raise ValueError(f"Unsupported step type: {step.type}")

    def _find_element(self, step: Step):
        if self.driver is None:
            raise RuntimeError("WebDriver is not initialized")

        wait = WebDriverWait(self.driver, max(3, settings.selenium_timeout))

        # Strategy 1: CSS selectors (learned selector first, then hint).
        css_candidates: list[str] = []
        if getattr(step, "resolved_css_selector", None):
            css_candidates.append(step.resolved_css_selector)  # type: ignore[arg-type]
        if hasattr(step, "css_selector_hint") and getattr(step, "css_selector_hint"):
            css_candidates.append(step.css_selector_hint)  # type: ignore[arg-type]
        for css_selector in css_candidates:
            try:
                return wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, css_selector))
                )
            except TimeoutException:
                continue

        # Strategy 2: XPath text matching from target_text_hint.
        text_hint = getattr(step, "target_text_hint", None)
        if text_hint:
            text_literal = self._xpath_literal(text_hint)
            xpaths = [
                f"//*[normalize-space(text())={text_literal}]",
                f"//*[@value={text_literal}]",
                f"//*[contains(normalize-space(text()), {text_literal})]",
            ]
            for xpath in xpaths:
                elements = self.driver.find_elements(By.XPATH, xpath)
                visible = [el for el in elements if el.is_displayed()]
                if visible:
                    return visible[0]

        # Strategy 3: aria-label / semantic attribute matching.
        semantic_hint = getattr(step, "target_semantic", None) or text_hint
        if semantic_hint:
            semantic_literal = self._xpath_literal(semantic_hint)
            aria_xpaths = [
                f"//*[@aria-label={semantic_literal}]",
                f"//*[contains(@aria-label, {semantic_literal})]",
                f"//*[contains(@placeholder, {semantic_literal})]",
                f"//*[contains(@title, {semantic_literal})]",
                f"//*[contains(@name, {semantic_literal})]",
            ]
            for xpath in aria_xpaths:
                elements = self.driver.find_elements(By.XPATH, xpath)
                visible = [el for el in elements if el.is_displayed()]
                if visible:
                    return visible[0]

        raise NoSuchElementException(f"No element found for step: {step.description}")

    def _substitute_step_placeholders(self, step: Step, params: dict[str, Any]) -> Step:
        def substitute(value: Any) -> Any:
            if isinstance(value, str):
                return _PLACEHOLDER_PATTERN.sub(
                    lambda match: self._resolve_param(match.group(1), params), value
                )
            if isinstance(value, dict):
                return {k: substitute(v) for k, v in value.items()}
            if isinstance(value, list):
                return [substitute(v) for v in value]
            return value

        raw_step = step.model_dump()
        substituted = substitute(raw_step)
        return type(step).model_validate(substituted)

    def _resolve_param(self, key: str, params: dict[str, Any]) -> str:
        if key not in params:
            raise KeyError(f"Missing required workflow parameter: {key}")
        return str(params[key])

    def _wait_for_page_ready(self, timeout: int) -> None:
        if self.driver is None:
            return
        try:
            WebDriverWait(self.driver, timeout).until(
                lambda driver: driver.execute_script("return document.readyState")
                == "complete"
            )
        except TimeoutException:
            # UCI pages can render dynamic widgets after initial content load.
            pass

    def _is_uci_auth_page(self) -> bool:
        if self.driver is None:
            return False
        current_url = self.driver.current_url.lower()
        return any(domain in current_url for domain in _UCI_AUTH_DOMAINS)

    def _take_screenshot(self, filename: str) -> str:
        if self.driver is None:
            raise RuntimeError("WebDriver is not initialized")
        path = self.artifacts_dir / filename
        self.driver.save_screenshot(str(path))
        return str(path)

    def _safe_error_screenshot(self) -> Optional[str]:
        if self.driver is None:
            return None
        try:
            return self._take_screenshot("error.png")
        except Exception:  # noqa: BLE001
            return None

    def _set_status(
        self,
        *,
        status: RunStatus,
        current_step: int,
        message: str,
        level: str = "info",
        step_index: Optional[int] = None,
        screenshot_path: Optional[str] = None,
    ) -> None:
        update_run(
            self.run_id,
            status=status,
            current_step=current_step,
        )
        add_log(
            self.run_id,
            level="error" if level == "error" else "info",
            message=message,
            step_index=step_index,
            screenshot_path=screenshot_path,
        )

        if self.status_callback is not None:
            payload = {
                "run_id": self.run_id,
                "workflow_id": self.workflow_id,
                "status": status.value,
                "current_step": current_step,
                "message": message,
                "step_index": step_index,
                "screenshot_path": screenshot_path,
            }
            try:
                self.status_callback(payload)
            except Exception:  # noqa: BLE001
                # Status push failures should not interrupt workflow execution.
                add_log(
                    self.run_id,
                    level="warn",
                    message="Status callback failed; continuing run.",
                    step_index=step_index,
                )

    @staticmethod
    def _xpath_literal(value: str) -> str:
        if "'" not in value:
            return f"'{value}'"
        if '"' not in value:
            return f'"{value}"'
        parts = value.split("'")
        joined = ", \"'\", ".join(f"'{part}'" for part in parts)
        return f"concat({joined})"


# Backward-compatible alias if other modules import SeleniumRunner.
SeleniumRunner = WorkflowRunner
