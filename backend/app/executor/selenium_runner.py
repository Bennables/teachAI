from __future__ import annotations

import re
import time
from collections.abc import Callable
from datetime import datetime, date
from pathlib import Path
from typing import Any, Optional, Union
from urllib.parse import urljoin

from selenium import webdriver
from selenium.common.exceptions import (
    ElementNotInteractableException,
    InvalidElementStateException,
    NoSuchElementException,
    TimeoutException,
)
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.select import Select
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

from app.core.config import settings
from app.core.storage import add_log, get_run, save_run, update_run
from app.models.schemas import (
    RunStatus,
    Step,
    WorkflowTemplate,
)

StatusCallback = Callable[[dict[str, Any]], None]

_PLACEHOLDER_PATTERN = re.compile(r"{{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*}}")
_UCI_AUTH_DOMAINS = ("webauth.uci.edu", "login.uci.edu", "duosecurity.com")
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
                action_result = self._execute_step(resolved_step)

                screenshot_path = self._take_screenshot(f"step_{step_index}.png")
                self._set_status(
                    status=RunStatus.RUNNING,
                    current_step=step_index + 1,
                    message=f"Completed step {step_index}: {action_result}",
                    step_index=step_index,
                    screenshot_path=screenshot_path,
                )

                if self._is_uci_auth_page():
                    auth_completed = self._wait_for_auth_completion(
                        step_index=step_index,
                        current_step=step_index + 1,
                    )
                    if not auth_completed:
                        return

            self._set_status(
                status=RunStatus.SUCCEEDED,
                current_step=len(workflow.steps),
                message="Workflow completed successfully",
            )
        except Exception as exc:  # noqa: BLE001
            error_shot = self._safe_error_screenshot()
            context = self._page_debug_context()
            exc_text = str(exc)
            if "Context:" in exc_text:
                message = f"Workflow failed: {exc_text}"
            else:
                message = f"Workflow failed: {exc_text}. Context: {context}"
            self._set_status(
                status=RunStatus.FAILED,
                current_step=get_run(self.run_id).current_step if get_run(self.run_id) else 0,
                message=message,
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

        # Prefer Selenium Manager (bundled with Selenium 4+) to avoid
        # webdriver-manager path selection issues on newer chromedriver zips.
        try:
            self.driver = webdriver.Chrome(options=options)
        except Exception:
            installed_path = ChromeDriverManager().install()
            resolved_path = self._resolve_chromedriver_path(installed_path)
            service = Service(executable_path=resolved_path)
            self.driver = webdriver.Chrome(service=service, options=options)
        self.driver.implicitly_wait(3)

    def _execute_step(self, step: Step) -> str:
        if self.driver is None:
            raise RuntimeError("WebDriver is not initialized")

        if step.type == "GOTO":
            self.driver.get(step.url)
            self._wait_for_page_ready(timeout=max(5, settings.selenium_timeout))
            return f"navigated to {step.url}"

        if step.type == "CLICK":
            if step.target_text_hint:
                selected = self._try_select_choice_input(step.target_text_hint)
                if selected:
                    self._wait_for_page_ready(timeout=2)
                    return "click action succeeded via checked choice input"
            try:
                element = self._find_element(step)
            except NoSuchElementException as exc:
                if self._try_click_associated_input(step):
                    self._wait_for_page_ready(timeout=3)
                    return "click action succeeded via label-associated input"
                raise exc
            self.driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});", element
            )
            before_url = self.driver.current_url
            element.click()
            if step.target_text_hint and self._looks_like_choice_step(step):
                if not self._is_choice_selected(step.target_text_hint):
                    # One more deterministic attempt for checkbox/radio groups.
                    if not self._try_select_choice_input(step.target_text_hint):
                        raise RuntimeError(
                            f"Choice option '{step.target_text_hint}' was not selected."
                        )
            if self._looks_like_submit_booking_step(step):
                invalid_fields = self._collect_invalid_form_fields()
                if invalid_fields:
                    raise RuntimeError(
                        "Submit blocked by invalid required fields: "
                        + ", ".join(invalid_fields)
                    )
                if not self._wait_for_post_submit_transition(before_url, timeout_seconds=8):
                    raise RuntimeError(
                        "Submit click did not trigger a checkout transition/confirmation."
                    )
            self._wait_for_page_ready(timeout=3)
            return "click action succeeded"

        if step.type == "TYPE":
            element = self._find_element(step)
            element = self._coerce_to_editable_element(step, element)
            self.driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});", element
            )
            method_used = self._type_with_verification(step, element)
            return f"typed value via {method_used}"

        if step.type == "SELECT":
            element = self._find_element(step)
            self.driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});", element
            )
            if element.tag_name.lower() == "select":
                select = Select(element)
                if self._looks_like_end_time_step(step):
                    select = self._resolve_end_time_select(select, requested_value=step.value)
                selected = False
                try:
                    select.select_by_visible_text(step.value)
                    selected = True
                except NoSuchElementException:
                    try:
                        select.select_by_value(step.value)
                        selected = True
                    except NoSuchElementException:
                        selected = self._select_option_fuzzy(select, step.value)
                if not selected:
                    message = self._build_select_unavailable_message(step, select, step.value)
                    add_log(
                        self.run_id,
                        level="warn",
                        message=message,
                    )
                    raise RuntimeError(message)
            else:
                element.click()
                element.send_keys(step.value)
                element.send_keys(Keys.ENTER)
            return f"selected option '{step.value}'"

        if step.type == "WAIT":
            if step.seconds is not None and not (
                step.until_selector or step.until_url_contains or step.until_text_visible
            ):
                time.sleep(step.seconds)
                return "wait condition satisfied"

            timeout_seconds = 30
            auth_extended_once = False
            started = time.time()

            while time.time() - started <= timeout_seconds:
                if self._wait_condition_satisfied(step):
                    return "wait condition satisfied"

                if self._is_uci_auth_page() or self._is_spaces_auth_page():
                    if not auth_extended_once:
                        timeout_seconds = max(timeout_seconds, settings.selenium_auth_wait_seconds)
                        auth_extended_once = True
                        add_log(
                            self.run_id,
                            level="info",
                            message=(
                                f"WAIT step encountered auth flow; extending timeout to "
                                f"{timeout_seconds}s."
                            ),
                        )
                time.sleep(0.4)

            if step.until_selector:
                detail = f"selector '{step.until_selector}'"
            elif step.until_url_contains:
                detail = f"url containing '{step.until_url_contains}'"
            elif step.until_text_visible:
                detail = f"text '{step.until_text_visible}'"
            else:
                detail = "generic wait condition"
            context = self._page_debug_context()
            raise RuntimeError(
                f"WAIT step timed out for {detail}: {step.description}. "
                f"Context: {context}"
            )
            return "wait condition satisfied"

        if step.type == "SCROLL":
            if step.target_selector:
                target = self.driver.find_element(By.CSS_SELECTOR, step.target_selector)
                self.driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'center'});", target
                )
            else:
                pixels = step.pixels if step.direction == "down" else -step.pixels
                self.driver.execute_script("window.scrollBy(0, arguments[0]);", pixels)
            return "scroll action completed"

        if step.type == "SCREENSHOT":
            self._take_screenshot(step.filename)
            return f"screenshot saved to {step.filename}"

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
                if step.type == "CLICK" and self._looks_like_slot_selector(css_selector):
                    return self._find_slot_element_with_date_fallback(step, css_selector)
                if step.type in {"TYPE", "SELECT", "CLICK"}:
                    text_hint = (
                        getattr(step, "target_text_hint", None) if step.type == "CLICK" else None
                    )
                    return wait.until(
                        lambda driver: self._first_visible_css_element(
                            css_selector,
                            editable_only=(step.type == "TYPE"),
                            text_hint=text_hint,
                        )
                    )
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
                f"//*[contains(@title, {text_literal})]",
                f"//*[contains(@aria-label, {text_literal})]",
                f"//*[contains(@data-original-title, {text_literal})]",
                f"//*[contains(@data-tooltip, {text_literal})]",
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

    def _first_visible_css_element(
        self,
        css_selector: str,
        editable_only: bool = False,
        text_hint: Optional[str] = None,
    ):
        if self.driver is None:
            return False

        candidates = self.driver.find_elements(By.CSS_SELECTOR, css_selector)
        for candidate in candidates:
            try:
                if not candidate.is_displayed():
                    continue
            except Exception:  # noqa: BLE001
                continue

            if text_hint and not self._element_matches_hint(candidate, text_hint):
                continue

            if not editable_only:
                return candidate

            tag = candidate.tag_name.lower()
            is_editable = tag in {"input", "textarea"} or (
                candidate.get_attribute("contenteditable") == "true"
            )
            if is_editable:
                return candidate

        return False

    @staticmethod
    def _looks_like_slot_selector(css_selector: str) -> bool:
        lowered = (css_selector or "").lower()
        return "s-lc-eq-avail" in lowered or "data-start" in lowered

    def _find_slot_element_with_date_fallback(self, step: Step, css_selector: str):
        if self.driver is None:
            raise RuntimeError("WebDriver is not initialized")

        text_hint = getattr(step, "target_text_hint", None)
        short_wait = WebDriverWait(self.driver, 2)
        try:
            return short_wait.until(
                lambda driver: self._first_visible_css_element(
                    css_selector, editable_only=False, text_hint=text_hint
                )
            )
        except TimeoutException:
            target_date = self._extract_date_from_selector(css_selector)
            if target_date is not None:
                add_log(
                    self.run_id,
                    level="info",
                    message=(
                        "Start slot not visible on current date range. "
                        f"Navigating schedule to {target_date.isoformat()}."
                    ),
                )
                navigated = self._advance_schedule_to_target_date(target_date)
                add_log(
                    self.run_id,
                    level="info" if navigated else "warn",
                    message=(
                        f"Schedule navigation to {target_date.isoformat()} "
                        + ("succeeded." if navigated else "did not find target date.")
                    ),
                )

            retry_wait = WebDriverWait(self.driver, min(6, max(3, settings.selenium_timeout)))
            return retry_wait.until(
                lambda driver: self._first_visible_css_element(
                    css_selector, editable_only=False, text_hint=text_hint
                )
            )

    @staticmethod
    def _extract_date_from_selector(selector: str) -> Optional[date]:
        if not selector:
            return None
        match = re.search(r"(\d{4})-(\d{2})-(\d{2})", selector)
        if not match:
            return None
        try:
            year, month, day = match.groups()
            return date(int(year), int(month), int(day))
        except ValueError:
            return None

    def _element_matches_hint(self, element, hint: str) -> bool:
        normalized_hint = self._normalize_text(hint)
        if not normalized_hint:
            return True

        texts = [
            element.text,
            element.get_attribute("value"),
            element.get_attribute("title"),
            element.get_attribute("aria-label"),
            element.get_attribute("data-original-title"),
            element.get_attribute("data-tooltip"),
        ]
        for value in texts:
            if normalized_hint in self._normalize_text(value or ""):
                return True
        return False

    def _try_click_associated_input(self, step: Step) -> bool:
        if self.driver is None:
            return False

        hint = getattr(step, "target_text_hint", None)
        if not hint:
            return False
        normalized_hint = self._normalize_text(hint)
        if not normalized_hint:
            return False

        labels = self.driver.find_elements(By.CSS_SELECTOR, "label[for], label")
        for label in labels:
            if not label.is_displayed():
                continue
            if not self._element_matches_hint(label, normalized_hint):
                continue

            label_for = (label.get_attribute("for") or "").strip()
            target_input = None
            if label_for:
                try:
                    target_input = self.driver.find_element(By.ID, label_for)
                except Exception:  # noqa: BLE001
                    target_input = None
            if target_input is None:
                nested = label.find_elements(By.CSS_SELECTOR, "input[type='radio'], input[type='checkbox']")
                if nested:
                    target_input = nested[0]

            for target in [target_input, label]:
                if target is None:
                    continue
                try:
                    self.driver.execute_script(
                        "arguments[0].scrollIntoView({block:'center'});", target
                    )
                    target.click()
                    return True
                except Exception:  # noqa: BLE001
                    try:
                        self.driver.execute_script("arguments[0].click();", target)
                        return True
                    except Exception:  # noqa: BLE001
                        continue
        return False

    @staticmethod
    def _looks_like_choice_step(step: Step) -> bool:
        description = (getattr(step, "description", "") or "").lower()
        semantic = (getattr(step, "target_semantic", "") or "").lower()
        return (
            "affiliation" in description
            or "purpose" in description
            or "affiliation" in semantic
            or "purpose" in semantic
        )

    @staticmethod
    def _looks_like_submit_booking_step(step: Step) -> bool:
        description = (getattr(step, "description", "") or "").lower()
        text_hint = (getattr(step, "target_text_hint", "") or "").lower()
        return "submit my booking" in description or "submit my booking" in text_hint

    def _try_select_choice_input(self, hint: str) -> bool:
        if self.driver is None:
            return False

        normalized_hint = self._normalize_text(hint)
        if not normalized_hint:
            return False

        # First pass: labels with matching text.
        labels = self.driver.find_elements(By.CSS_SELECTOR, "label")
        for label in labels:
            try:
                if not label.is_displayed():
                    continue
            except Exception:  # noqa: BLE001
                continue
            if not self._element_matches_hint(label, normalized_hint):
                continue

            target = self._associated_choice_input_from_label(label)
            if target is None:
                continue
            if self._click_and_confirm_selected(target):
                return True

        # Fallback: direct radio/checkbox input attribute matches.
        inputs = self.driver.find_elements(By.CSS_SELECTOR, "input[type='radio'], input[type='checkbox']")
        for field in inputs:
            try:
                if not field.is_displayed():
                    continue
            except Exception:  # noqa: BLE001
                continue

            attrs = " ".join(
                [
                    field.get_attribute("value") or "",
                    field.get_attribute("id") or "",
                    field.get_attribute("name") or "",
                    field.get_attribute("aria-label") or "",
                    field.get_attribute("title") or "",
                ]
            )
            if normalized_hint not in self._normalize_text(attrs):
                continue
            if self._click_and_confirm_selected(field):
                return True

        return False

    def _is_choice_selected(self, hint: str) -> bool:
        if self.driver is None:
            return False
        normalized_hint = self._normalize_text(hint)
        if not normalized_hint:
            return False
        labels = self.driver.find_elements(By.CSS_SELECTOR, "label")
        for label in labels:
            if not self._element_matches_hint(label, normalized_hint):
                continue
            target = self._associated_choice_input_from_label(label)
            if target is None:
                continue
            try:
                if target.is_selected():
                    return True
                if (target.get_attribute("checked") or "").lower() in {"true", "checked"}:
                    return True
            except Exception:  # noqa: BLE001
                continue
        return False

    def _associated_choice_input_from_label(self, label):
        if self.driver is None:
            return None

        label_for = (label.get_attribute("for") or "").strip()
        if label_for:
            try:
                return self.driver.find_element(By.ID, label_for)
            except Exception:  # noqa: BLE001
                pass

        try:
            nested = label.find_elements(By.CSS_SELECTOR, "input[type='radio'], input[type='checkbox']")
            if nested:
                return nested[0]
        except Exception:  # noqa: BLE001
            pass

        try:
            sibling = label.find_element(
                By.XPATH,
                "preceding-sibling::input[@type='radio' or @type='checkbox'][1] | "
                "following-sibling::input[@type='radio' or @type='checkbox'][1]",
            )
            if sibling is not None:
                return sibling
        except Exception:  # noqa: BLE001
            pass
        return None

    def _click_and_confirm_selected(self, element) -> bool:
        if self.driver is None:
            return False
        try:
            self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
        except Exception:  # noqa: BLE001
            pass

        for clicker in (
            lambda: element.click(),
            lambda: self.driver.execute_script("arguments[0].click();", element),
        ):
            try:
                clicker()
            except Exception:  # noqa: BLE001
                continue
            time.sleep(0.1)
            try:
                if element.is_selected():
                    return True
                if (element.get_attribute("checked") or "").lower() in {"true", "checked"}:
                    return True
            except Exception:  # noqa: BLE001
                continue
        return False

    def _collect_invalid_form_fields(self) -> list[str]:
        if self.driver is None:
            return []
        try:
            invalid = self.driver.execute_script(
                """
                const fields = Array.from(document.querySelectorAll('input, select, textarea'));
                return fields
                  .filter(el => !el.disabled && typeof el.checkValidity === 'function' && !el.checkValidity())
                  .map(el => {
                    const labels = Array.from(el.labels || [])
                      .map(l => (l.innerText || '').trim())
                      .filter(Boolean);
                    const label = labels.length ? labels[0] : (el.name || el.id || el.type || el.tagName);
                    const msg = (el.validationMessage || '').trim();
                    return msg ? `${label} (${msg})` : label;
                  });
                """
            )
            if isinstance(invalid, list):
                return [str(item) for item in invalid if str(item).strip()]
        except Exception:  # noqa: BLE001
            return []
        return []

    def _wait_for_post_submit_transition(self, before_url: str, timeout_seconds: int) -> bool:
        if self.driver is None:
            return False
        deadline = time.time() + max(1, timeout_seconds)
        while time.time() < deadline:
            try:
                current_url = self.driver.current_url
            except Exception:  # noqa: BLE001
                current_url = ""
            if current_url and current_url != before_url:
                return True

            try:
                body_text = (self.driver.find_element(By.TAG_NAME, "body").text or "").lower()
            except Exception:  # noqa: BLE001
                body_text = ""

            if any(
                marker in body_text
                for marker in (
                    "booking confirmed",
                    "reservation confirmed",
                    "confirmation",
                    "successfully booked",
                    "thank you",
                )
            ):
                return True

            # If submit button disappears, we likely transitioned in-place.
            submit_buttons = self.driver.find_elements(
                By.XPATH,
                "//button[contains(normalize-space(.), 'Submit my Booking')]"
                " | //input[@type='submit' and contains(@value, 'Submit my Booking')]",
            )
            visible = [btn for btn in submit_buttons if btn.is_displayed()]
            if not visible:
                return True

            time.sleep(0.25)
        return False

    def _coerce_to_editable_element(self, step: Step, element):
        if self.driver is None:
            return element

        tag = element.tag_name.lower()
        if tag in {"input", "textarea"}:
            return element

        # If a label/container was matched, try to find an editable field inside it.
        try:
            nested = element.find_elements(By.CSS_SELECTOR, "input, textarea")
            for candidate in nested:
                if candidate.is_displayed():
                    return candidate
        except Exception:  # noqa: BLE001
            pass

        # If CSS hints were provided, re-query and pick first visible editable element.
        css_hint = getattr(step, "css_selector_hint", None)
        if css_hint:
            for selector in [part.strip() for part in css_hint.split(",") if part.strip()]:
                found = self._first_visible_css_element(selector, editable_only=True)
                if found:
                    return found

        return element

    def _set_input_value_via_js(self, element, value: str) -> None:
        if self.driver is None:
            raise RuntimeError("WebDriver is not initialized")

        self.driver.execute_script(
            """
            const el = arguments[0];
            const val = arguments[1];
            if (!el) return;

            try { el.removeAttribute('readonly'); } catch (_) {}
            try { el.removeAttribute('disabled'); } catch (_) {}

            const proto = Object.getPrototypeOf(el);
            const descriptor = proto ? Object.getOwnPropertyDescriptor(proto, 'value') : null;
            if (descriptor && typeof descriptor.set === 'function') {
              descriptor.set.call(el, val);
            } else {
              el.value = val;
            }

            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
            el.dispatchEvent(new Event('blur', { bubbles: true }));
            """,
            element,
            value,
        )

    def _type_with_verification(self, step: Step, element) -> str:
        if self.driver is None:
            raise RuntimeError("WebDriver is not initialized")

        is_date_field = self._is_likely_date_step(step)
        if step.clear_first:
            try:
                element.clear()
            except (InvalidElementStateException, ElementNotInteractableException):
                pass

        if is_date_field:
            self._open_go_to_date_control_if_present()

        method = "send_keys"
        try:
            element.click()
            element.send_keys(Keys.COMMAND, "a")
            element.send_keys(Keys.BACKSPACE)
            element.send_keys(step.value)
            # Helps date widgets commit typed value.
            element.send_keys(Keys.ENTER)
            element.send_keys(Keys.TAB)
        except (InvalidElementStateException, ElementNotInteractableException):
            method = "javascript"
            self._set_input_value_via_js(element, step.value)

        if is_date_field:
            picked = self._select_date_via_picker_if_open(step.value)
            if picked:
                method = "datepicker_click"
            target_date = self._parse_date(step.value)
            if target_date is not None:
                navigated = self._advance_schedule_to_target_date(target_date.date())
                if navigated:
                    method = "schedule_nav"
            self._set_input_datepicker_value_via_js(element, step.value)
            # Fire events once more to ensure grid refresh.
            self._set_input_value_via_js(element, step.value)

        if not self._verify_typed_value(element, step.value, is_date_field):
            raise RuntimeError(
                f"TYPE verification failed for '{step.description}'. "
                f"Expected value '{step.value}'."
            )
        if is_date_field:
            target_date = self._parse_date(step.value)
            if target_date is not None and not self._page_contains_date(target_date.date()):
                raise RuntimeError(
                    f"Date step did not update visible schedule to {step.value}."
                )
        return method

    @staticmethod
    def _normalize_text(value: str) -> str:
        return re.sub(r"\s+", " ", (value or "")).strip().lower()

    def _select_option_fuzzy(self, select: Select, target_value: str) -> bool:
        normalized_target = self._normalize_text(target_value)
        for option in select.options:
            option_text = self._normalize_text(option.text)
            option_value = self._normalize_text(option.get_attribute("value") or "")
            if normalized_target in option_text or normalized_target in option_value:
                option.click()
                return True
        return False

    @staticmethod
    def _looks_like_end_time_step(step: Step) -> bool:
        description = (getattr(step, "description", "") or "").lower()
        semantic = (getattr(step, "target_semantic", "") or "").lower()
        css_hint = (getattr(step, "css_selector_hint", "") or "").lower()
        return (
            "end time" in description
            or "end time" in semantic
            or "name*='end'" in css_hint
            or "id*='end'" in css_hint
        )

    def _visible_select_options(
        self, select: Select, time_only: bool = False, limit: int = 12
    ) -> list[str]:
        options: list[str] = []
        for option in select.options:
            text = " ".join((option.text or "").split()).strip()
            if not text:
                text = (option.get_attribute("value") or "").strip()
            if not text:
                continue
            lowered = text.lower()
            if lowered in {"select", "select...", "--select--"}:
                continue
            if time_only and not self._looks_like_time_text(text):
                continue
            if text not in options:
                options.append(text)
            if len(options) >= limit:
                break
        return options

    @staticmethod
    def _looks_like_time_text(value: str) -> bool:
        normalized = (value or "").strip().lower()
        return bool(re.search(r"\b\d{1,2}:\d{2}\s*(am|pm)\b", normalized))

    def _build_select_unavailable_message(
        self, step: Step, select: Select, requested_value: str
    ) -> str:
        if self._looks_like_end_time_step(step):
            available = self._visible_select_options(select, time_only=True)
        else:
            available = self._visible_select_options(select, time_only=False)
        base = (
            f"Could not select '{requested_value}' for step '{step.description}'."
        )
        if self._looks_like_end_time_step(step):
            base = (
                f"Requested time slot is unavailable: end time '{requested_value}' "
                "is not offered for the selected room/date/start-time."
            )
            if not available:
                return (
                    "Could not find a valid end-time dropdown for the selected booking "
                    "slot. The start slot may not have been applied yet."
                )
        if available:
            return base + " Available options: " + ", ".join(available) + "."
        return base + " No selectable options were available in the dropdown."

    def _resolve_end_time_select(self, select: Select, requested_value: str) -> Select:
        if self.driver is None:
            return select

        if self._looks_like_time_dropdown(select):
            return select

        requested_hint = self._normalize_text(requested_value)
        best: Optional[tuple[int, Select]] = None
        for element in self.driver.find_elements(By.CSS_SELECTOR, "select"):
            try:
                if not element.is_displayed():
                    continue
            except Exception:  # noqa: BLE001
                continue
            candidate = Select(element)
            score = self._time_dropdown_score(candidate, requested_hint)
            if score <= 0:
                continue
            if best is None or score > best[0]:
                best = (score, candidate)

        if best is not None:
            return best[1]
        return select

    def _time_dropdown_score(self, select: Select, requested_hint: str) -> int:
        score = 0
        options = self._visible_select_options(select, time_only=False, limit=30)
        time_options = [text for text in options if self._looks_like_time_text(text)]
        if time_options:
            score += min(10, len(time_options))
        if requested_hint:
            for text in options:
                normalized = self._normalize_text(text)
                if requested_hint in normalized:
                    score += 5
                    break
        return score

    def _looks_like_time_dropdown(self, select: Select) -> bool:
        options = self._visible_select_options(select, time_only=False, limit=20)
        time_like = [text for text in options if self._looks_like_time_text(text)]
        return len(time_like) >= 2

    @staticmethod
    def _is_likely_date_step(step: Step) -> bool:
        semantic = (getattr(step, "target_semantic", "") or "").lower()
        css_hint = (getattr(step, "css_selector_hint", "") or "").lower()
        value = (getattr(step, "value", "") or "").strip()
        if "date" in semantic or "date" in css_hint:
            return True
        return bool(re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}", value))

    def _verify_typed_value(self, element, expected: str, is_date_field: bool) -> bool:
        actual = (element.get_attribute("value") or "").strip()
        expected = (expected or "").strip()
        if not expected:
            return True

        if actual == expected:
            return True
        if expected in actual:
            return True

        if is_date_field:
            expected_date = self._parse_date(expected)
            actual_date = self._parse_date(actual)
            if expected_date is not None and actual_date is not None:
                return expected_date.date() == actual_date.date()
            # Some widgets keep value elsewhere but still input is non-empty.
            return bool(actual)

        return False

    @staticmethod
    def _parse_date(value: str) -> Optional[datetime]:
        if not value:
            return None
        for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%b %d, %Y", "%B %d, %Y"):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
        return None

    def _select_date_via_picker_if_open(self, date_value: str) -> bool:
        """
        Best-effort datepicker interaction for common picker implementations.
        Returns True if a day cell was clicked.
        """
        if self.driver is None:
            return False

        target = self._parse_date(date_value)
        if target is None:
            return False

        picker_selectors = [".ui-datepicker", ".datepicker", ".flatpickr-calendar.open"]
        picker_root = None
        for selector in picker_selectors:
            visible = self.driver.find_elements(By.CSS_SELECTOR, selector)
            for candidate in visible:
                if candidate.is_displayed():
                    picker_root = candidate
                    break
            if picker_root is not None:
                break

        if picker_root is None:
            return False

        target_month_name = target.strftime("%B").lower()
        target_year = target.strftime("%Y")

        for _ in range(13):
            header_text = self._picker_header_text(picker_root).lower()
            if target_month_name in header_text and target_year in header_text:
                break
            if not self._click_picker_next(picker_root):
                break
            time.sleep(0.2)

        day_num = str(target.day)
        day_selectors = [
            "a.ui-state-default",
            "td.day",
            ".flatpickr-day",
            "button.day",
        ]
        for selector in day_selectors:
            for day in picker_root.find_elements(By.CSS_SELECTOR, selector):
                classes = (day.get_attribute("class") or "").lower()
                if any(
                    marker in classes
                    for marker in ("old", "new", "disabled", "prevmonthday", "nextmonthday")
                ):
                    continue
                if day.text.strip() == day_num and day.is_displayed():
                    day.click()
                    return True
        return False

    def _open_go_to_date_control_if_present(self) -> bool:
        if self.driver is None:
            return False

        candidates = self.driver.find_elements(
            By.XPATH,
            "//button[contains(normalize-space(.), 'Go To Date')]"
            " | //a[contains(normalize-space(.), 'Go To Date')]"
            " | //*[@aria-label='Go To Date']",
        )
        for candidate in candidates:
            if not candidate.is_displayed():
                continue
            try:
                candidate.click()
                time.sleep(0.2)
                return True
            except Exception:  # noqa: BLE001
                try:
                    self.driver.execute_script("arguments[0].click();", candidate)
                    time.sleep(0.2)
                    return True
                except Exception:  # noqa: BLE001
                    continue
        return False

    def _wait_for_auth_completion(self, *, step_index: int, current_step: int) -> bool:
        if self.driver is None:
            return False

        timeout_seconds = max(60, settings.selenium_auth_wait_seconds)
        poll_seconds = 2
        started = time.time()

        self._paused_for_auth = True
        auth_shot = self._take_screenshot(f"step_{step_index}_auth.png")
        self._set_status(
            status=RunStatus.WAITING_FOR_AUTH,
            current_step=current_step,
            message=(
                f"Authentication detected. Waiting up to {timeout_seconds} seconds "
                "for SSO to complete automatically."
            ),
            step_index=step_index,
            screenshot_path=auth_shot,
        )

        last_progress_mark = -30
        while time.time() - started <= timeout_seconds:
            if not self._is_uci_auth_page():
                self._paused_for_auth = False
                self._set_status(
                    status=RunStatus.RUNNING,
                    current_step=current_step,
                    message="Authentication completed; resuming workflow.",
                    step_index=step_index,
                )
                return True

            elapsed = int(time.time() - started)
            if elapsed - last_progress_mark >= 30:
                last_progress_mark = elapsed
                self._set_status(
                    status=RunStatus.WAITING_FOR_AUTH,
                    current_step=current_step,
                    message=(
                        "Still waiting for SSO completion. "
                        f"Elapsed {elapsed}s / {timeout_seconds}s."
                    ),
                    step_index=step_index,
                )

            try:
                self.driver.execute_script("return document.readyState")
            except Exception:  # noqa: BLE001
                break
            time.sleep(poll_seconds)

        timeout_shot = self._safe_error_screenshot()
        self._set_status(
            status=RunStatus.WAITING_FOR_AUTH,
            current_step=current_step,
            message=(
                "Authentication wait timed out. Complete SSO in the existing browser "
                "and call continue."
            ),
            step_index=step_index,
            screenshot_path=timeout_shot,
        )
        return False

    def _set_input_datepicker_value_via_js(self, element, value: str) -> None:
        if self.driver is None:
            return
        self.driver.execute_script(
            """
            const el = arguments[0];
            const val = arguments[1];
            if (!el) return;
            if (window.jQuery && typeof window.jQuery === 'function') {
              const $el = window.jQuery(el);
              if ($el && typeof $el.datepicker === 'function') {
                try {
                  $el.datepicker('setDate', val);
                  $el.trigger('change');
                } catch (_) {}
              }
            }
            """,
            element,
            value,
        )

    def _advance_schedule_to_target_date(self, target: date) -> bool:
        if self.driver is None:
            return False

        if self._page_contains_date(target):
            return True

        for _ in range(20):
            next_button = self._find_visible_next_navigation_button()
            if next_button is None:
                return False
            try:
                next_button.click()
            except Exception:  # noqa: BLE001
                try:
                    self.driver.execute_script("arguments[0].click();", next_button)
                except Exception:  # noqa: BLE001
                    return False
            time.sleep(0.25)
            if self._page_contains_date(target):
                return True

        return False

    def _find_visible_next_navigation_button(self):
        if self.driver is None:
            return None
        selectors = [
            "button[aria-label*='Next']",
            "a[aria-label*='Next']",
            "button[title*='Next']",
            "a[title*='Next']",
            "button[id*='next']",
            "a[id*='next']",
            "button[class*='next']",
            "a[class*='next']",
            ".s-lc-rm-next",
            ".fc-next-button",
            ".ui-datepicker-next",
            "button .fa-chevron-right",
            "a .fa-chevron-right",
            "button .fa-angle-right",
            "a .fa-angle-right",
        ]
        for selector in selectors:
            for element in self.driver.find_elements(By.CSS_SELECTOR, selector):
                # If the selector is on an icon, click its parent button/link.
                tag = element.tag_name.lower()
                target = element
                if tag in {"i", "svg", "span"}:
                    parent = element.find_element(By.XPATH, "..")
                    if parent is not None:
                        target = parent
                if target.is_displayed():
                    return target

        # Room pages often place previous/next buttons next to "Go To Date".
        go_to_date_next = self.driver.find_elements(
            By.XPATH,
            "//button[contains(normalize-space(.), 'Go To Date')]/following-sibling::button",
        )
        visible = [el for el in go_to_date_next if el.is_displayed()]
        if len(visible) >= 2:
            return visible[-1]
        if len(visible) == 1:
            return visible[0]

        text_based = self.driver.find_elements(
            By.XPATH,
            "//button[normalize-space(text())='>' or normalize-space(text())='›']"
            " | //a[normalize-space(text())='>' or normalize-space(text())='›']",
        )
        for element in text_based:
            if element.is_displayed():
                return element
        return None

    def _page_contains_date(self, target: date) -> bool:
        if self.driver is None:
            return False
        body = (self.driver.find_element(By.TAG_NAME, "body").text or "").lower()
        month_name = target.strftime("%B")
        weekday_name = target.strftime("%A")
        tokens = [
            f"{month_name} {target.day}, {target.year}".lower(),
            target.strftime("%B %d, %Y").lower(),
            target.strftime("%m/%d/%Y").lower(),
            f"{weekday_name}, {month_name} {target.day}, {target.year}".lower(),
            target.strftime("%A, %B %d, %Y").lower(),
        ]
        return any(token in body for token in tokens)

    @staticmethod
    def _picker_header_text(picker_root) -> str:
        selectors = [
            ".ui-datepicker-title",
            ".datepicker-switch",
            ".flatpickr-current-month",
            ".month",
            ".calendar-title",
        ]
        for selector in selectors:
            nodes = picker_root.find_elements(By.CSS_SELECTOR, selector)
            for node in nodes:
                text = (node.text or "").strip()
                if text:
                    return text
        return ""

    @staticmethod
    def _click_picker_next(picker_root) -> bool:
        selectors = [
            ".ui-datepicker-next",
            ".next",
            ".flatpickr-next-month",
            "[aria-label*='Next']",
        ]
        for selector in selectors:
            for node in picker_root.find_elements(By.CSS_SELECTOR, selector):
                if node.is_displayed():
                    node.click()
                    return True
        return False

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
            self._inject_derived_params(params)
        if key not in params:
            raise KeyError(f"Missing required workflow parameter: {key}")
        return str(params[key])

    def _inject_derived_params(self, params: dict[str, Any]) -> None:
        if "room_page_url" not in params and "room_keyword" in params:
            room_keyword = str(params.get("room_keyword", "")).strip()
            if room_keyword:
                library = str(params.get("library", "")).strip() or None
                discovered = self._discover_room_page_url(room_keyword, library=library)
                if discovered:
                    params["room_page_url"] = discovered

        if "room_id" not in params and "room_keyword" in params:
            keyword = str(params.get("room_keyword", "")).strip()
            if keyword:
                match = re.search(r"\b(\d{3,5})\b", keyword)
                if match:
                    params["room_id"] = match.group(1)
                else:
                    params["room_id"] = re.sub(r"[^A-Za-z0-9_-]", "", keyword)
            if "room_page_url" not in params and "room_id" in params:
                params["room_page_url"] = (
                    f"https://spaces.lib.uci.edu/booking/Gateway/{params['room_id']}"
                )

        if "full_name" in params:
            full_name = " ".join(str(params["full_name"]).strip().split())
            if full_name and ("full_name_first" not in params or "full_name_last" not in params):
                parts = full_name.split(" ", 1)
                params["full_name_first"] = parts[0]
                params["full_name_last"] = parts[1] if len(parts) > 1 else "."

    def _discover_room_page_url(self, room_keyword: str, library: Optional[str] = None) -> Optional[str]:
        if self.driver is None:
            return None

        hint = self._normalize_text(room_keyword)
        if not hint:
            return None
        library_hint = self._normalize_text(library or "")

        anchors = self.driver.find_elements(
            By.CSS_SELECTOR, "a[href*='/space/'], a[href*='/booking/Gateway/']"
        )
        if not anchors:
            return None

        best_href: Optional[str] = None
        best_score = -1
        for anchor in anchors:
            try:
                if not anchor.is_displayed():
                    continue
            except Exception:  # noqa: BLE001
                continue

            href = (anchor.get_attribute("href") or "").strip()
            if not href:
                continue

            aggregate_text = " ".join(
                [
                    anchor.text or "",
                    anchor.get_attribute("title") or "",
                    anchor.get_attribute("aria-label") or "",
                ]
            )
            normalized_text = self._normalize_text(aggregate_text)
            normalized_href = self._normalize_text(href)
            context_text = normalized_text
            try:
                parent_context = anchor.find_element(By.XPATH, "ancestor::*[self::tr or self::li or self::div][1]")
                context_text = self._normalize_text(
                    " ".join(
                        [
                            aggregate_text,
                            parent_context.text or "",
                        ]
                    )
                )
            except Exception:  # noqa: BLE001
                pass

            score = 0
            if hint in normalized_text:
                score += 5
            if hint in context_text:
                score += 3
            if hint in normalized_href:
                score += 2
            if "/space/" in href:
                score += 1
            if library_hint and library_hint in context_text:
                score += 4

            if score > best_score:
                best_score = score
                best_href = href

        if best_href is None or best_score <= 0:
            return None
        return urljoin(self.driver.current_url, best_href)

    def _page_debug_context(self) -> str:
        if self.driver is None:
            return "driver=none"
        try:
            current_url = self.driver.current_url
        except Exception:  # noqa: BLE001
            current_url = "<unavailable>"
        try:
            title = (self.driver.title or "").strip()
        except Exception:  # noqa: BLE001
            title = "<unavailable>"

        body_text = ""
        try:
            body_text = (self.driver.find_element(By.TAG_NAME, "body").text or "").strip()
        except Exception:  # noqa: BLE001
            pass
        body_lower = body_text.lower()

        markers: list[str] = []
        if "space checkout" in body_lower:
            markers.append("space_checkout")
        if "fill out this form to complete the booking" in body_lower:
            markers.append("booking_form_text")
        if "submit my booking" in body_lower:
            markers.append("submit_my_booking_text")
        if "go to date" in body_lower:
            markers.append("go_to_date")

        try:
            input_count = len(self.driver.find_elements(By.CSS_SELECTOR, "input"))
            select_count = len(self.driver.find_elements(By.CSS_SELECTOR, "select"))
            textarea_count = len(self.driver.find_elements(By.CSS_SELECTOR, "textarea"))
            button_count = len(self.driver.find_elements(By.CSS_SELECTOR, "button, input[type='submit']"))
        except Exception:  # noqa: BLE001
            input_count = select_count = textarea_count = button_count = -1

        snippet = " ".join(body_text.split())[:180]
        return (
            f"url={current_url}; title={title}; auth={self._is_uci_auth_page()}; "
            f"markers={','.join(markers) if markers else '-'}; "
            f"counts=input:{input_count},select:{select_count},textarea:{textarea_count},button:{button_count}; "
            f"body='{snippet}'"
        )

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

    def _is_spaces_auth_page(self) -> bool:
        if self.driver is None:
            return False
        current_url = self.driver.current_url.lower()
        return "spaces.lib.uci.edu/spaces/auth" in current_url

    def _wait_condition_satisfied(self, step: Step) -> bool:
        if self.driver is None:
            return False
        if step.until_selector:
            return bool(self.driver.find_elements(By.CSS_SELECTOR, step.until_selector))
        if step.until_url_contains:
            return step.until_url_contains in self.driver.current_url
        if step.until_text_visible:
            try:
                body_text = self.driver.find_element(By.TAG_NAME, "body").text or ""
            except Exception:  # noqa: BLE001
                return False
            return step.until_text_visible in body_text
        return True

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

    @staticmethod
    def _resolve_chromedriver_path(installed_path: str) -> str:
        """
        Resolve the real chromedriver binary path.

        Some webdriver-manager versions may return
        THIRD_PARTY_NOTICES.chromedriver instead of the executable.
        """
        candidate = Path(installed_path)

        def looks_like_driver(path: Path) -> bool:
            if not path.is_file():
                return False
            name = path.name.lower()
            if "third_party_notices" in name:
                return False
            if "chromedriver" not in name:
                return False
            return True

        if looks_like_driver(candidate):
            return str(candidate)

        search_roots = [
            candidate.parent,
            candidate.parent.parent if candidate.parent != candidate else candidate.parent,
        ]

        for root in search_roots:
            if not root.exists():
                continue
            for found in root.rglob("*"):
                if looks_like_driver(found):
                    return str(found)

        raise RuntimeError(
            f"Could not locate chromedriver executable from webdriver-manager path: {installed_path}"
        )


# Backward-compatible alias if other modules import SeleniumRunner.
SeleniumRunner = WorkflowRunner