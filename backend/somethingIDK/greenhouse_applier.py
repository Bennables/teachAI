"""
Selenium-based filler for Greenhouse job application forms.

Greenhouse forms use standard ids: first_name, last_name, email, phone, resume, etc.
We wait for the form to be ready, then find by id and fill.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

# Unfilled field info for retry: question label, field id (if known), and type
UnfilledField = dict[str, str]

from selenium import webdriver
from selenium.common.exceptions import (
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from app.core.config import settings

# Standard Greenhouse input ids (they use id="first_name" etc.)
_FORM_READY_TIMEOUT = 15
_FIELD_TIMEOUT = 3
# Delays to avoid rate limiting (seconds)
_DELAY_AFTER_PAGE = 2
_DELAY_BETWEEN_FIELDS = 0.5
_DELAY_SELECT_OPEN = 0.5
_DELAY_SELECT_BEFORE_CHOOSE = .5  # Wait for dropdown options to render before typing answer
_DELAY_SELECT_TYPE = 0.5
_DELAY_BETWEEN_SELECTS = 0.3
_DELAY_PER_KEY = 0.03  # Seconds between each keystroke (slower, more human-like)


def _send_keys_slow(el: WebElement, text: str, delay: float = _DELAY_PER_KEY) -> None:
    """Type text one character at a time with a delay between each key."""
    for char in text:
        el.send_keys(char)
        time.sleep(delay)


def _click_away(driver: webdriver.Chrome) -> None:
    """Click neutral whitespace (top-left of <body>) to dismiss any open dropdown."""
    try:
        driver.execute_script("document.activeElement.blur();")
        body = driver.find_element(By.TAG_NAME, "body")
        # ActionChains move-and-click at an offset well away from form elements
        from selenium.webdriver.common.action_chains import ActionChains
        ActionChains(driver).move_to_element_with_offset(body, 10, 10).click().perform()
    except Exception:
        pass
    time.sleep(0.3)


def _wait_form_ready(driver: webdriver.Chrome, timeout: int = _FORM_READY_TIMEOUT) -> None:
    """Wait until the main form input is present and clickable (SPA may still be rendering)."""
    wait = WebDriverWait(driver, timeout)
    wait.until(EC.element_to_be_clickable((By.ID, "first_name")))


def _find_input_by_id(driver: webdriver.Chrome, field_id: str) -> Optional[WebElement]:
    """Find a visible input by id. Uses short wait."""
    try:
        wait = WebDriverWait(driver, _FIELD_TIMEOUT)
        el = wait.until(EC.presence_of_element_located((By.ID, field_id)))
        return el if el.is_displayed() else None
    except TimeoutException:
        return None


# Keyword → possible answers (try in order; use partial match so "No" matches "No, I am not...", etc.)
_SELECT_QUESTION_RULES: list[tuple[list[str], list[str]]] = [
    (["legally authorized", "authorized to work", "work authorization"], ["Yes", "yes"]),
    (["sponsorship", "require sponsorship", "visa sponsorship", "sponsorship now", "future sponsorship"], ["No"]),
    (["hear", "how did you hear", "hear about us", "referral source"], ["Other", "other", "Company"]),
    (["veteran", "veteran status", "protected veteran"], ["No", "no"]),
    (["disability", "disabled", "disability status", "have a disability"], ["No"]),
    (["hispanic", "latino", "hispanic or latino"], ["No"]),
    (["gender", "sex", "gender identity"], ["Male", "male", "Man"]),
]


def _select_option_by_keywords(driver: webdriver.Chrome, el: WebElement, answers: list[str]) -> bool:
    """Click a select/combobox, wait for options, try each answer until one works. Returns True if done."""
    for answer in answers:
        try:
            el.click()
            time.sleep(_DELAY_SELECT_OPEN)
            time.sleep(_DELAY_SELECT_BEFORE_CHOOSE)
            try:
                el.clear()
            except Exception:
                pass
            _send_keys_slow(el, answer)
            time.sleep(_DELAY_SELECT_TYPE)
            el.send_keys(Keys.ENTER)
            time.sleep(_DELAY_BETWEEN_SELECTS)
            _click_away(driver)
            return True
        except Exception:
            time.sleep(0.3)
            continue
    return False


def _fill_select_questions_by_keywords(driver: webdriver.Chrome) -> int:
    """
    Find select questions by label keywords and fill with Yes/No/Other.
    Returns count of questions filled.
    """
    filled = 0
    try:
        # Greenhouse uses labels with for="question_..." and inputs with matching id
        labels = driver.find_elements(By.CSS_SELECTOR, "label.select_label, label[class*='select'], .select_container label")
        print(f"[greenhouse] Select questions: found {len(labels)} label(s)")
        for label in labels:
            try:
                text = (label.text or "").strip().lower()
                if not text:
                    continue
                for keywords, answer in _SELECT_QUESTION_RULES:
                    if any(kw.lower() in text for kw in keywords):
                        inp = None
                        input_id = label.get_attribute("for")
                        if input_id:
                            try:
                                inp = driver.find_element(By.ID, input_id)
                            except NoSuchElementException:
                                pass
                        if not inp:
                            try:
                                container = label.find_element(By.XPATH, "./ancestor::div[contains(@class,'select') or contains(@class,'select_container')][1]")
                                inp = container.find_element(By.CSS_SELECTOR, "input[role='combobox'], input.select__input, input[id]")
                            except NoSuchElementException:
                                continue
                        if inp and inp.is_displayed() and _select_option_by_keywords(driver, inp, answer):
                            filled += 1
                            print(f"[greenhouse] Filled select: label={text[:60]!r} -> {answer[0]!r}")
                        break
            except (NoSuchElementException, StaleElementReferenceException):
                continue
    except Exception:
        pass
    return filled


def _select_country_united_states(driver: webdriver.Chrome) -> bool:
    """Select United States in the country combobox (id=country). Returns True if selected."""
    try:
        el = driver.find_element(By.ID, "country")
        if not el.is_displayed():
            return False
        el.click()
        time.sleep(_DELAY_SELECT_OPEN)
        time.sleep(_DELAY_SELECT_BEFORE_CHOOSE)
        _send_keys_slow(el, "United States")
        time.sleep(_DELAY_SELECT_TYPE)
        el.send_keys(Keys.ENTER)
        time.sleep(_DELAY_BETWEEN_SELECTS)
        _click_away(driver)
        return True
    except (NoSuchElementException, StaleElementReferenceException, Exception):
        return False


def _add_unfilled(
    el: WebElement,
    driver: webdriver.Chrome,
    queries: list[str],
    unfilled_fields: list[UnfilledField],
    seen: set[str],
    field_type: str,
    reason: str,
) -> None:
    """Add an unfilled/errored field to queries and unfilled_fields."""
    label_text = _get_label_for_element(driver, el)
    el_id = el.get_attribute("id") or el.get_attribute("name") or ""
    desc = label_text or el_id or "(unknown)"
    if desc.lower() not in seen:
        seen.add(desc.lower())
        queries.append(desc)
        unfilled_fields.append({
            "question": desc,
            "field_id": el_id,
            "field_type": field_type,
            "reason": reason,
        })


def _collect_p_tag_errors_in_field_div(driver: webdriver.Chrome) -> list[str]:
    """
    Collect validation errors rendered in <p> tags inside the same nearest <div>
    container as each input/select/textarea field.
    """
    errors: list[str] = []
    seen: set[str] = set()
    try:
        fields = driver.find_elements(By.CSS_SELECTOR, "input, select, textarea")
        for field in fields:
            try:
                if not field.is_displayed():
                    continue
                container = field.find_element(By.XPATH, "./ancestor::div[1]")
                p_tags = container.find_elements(By.TAG_NAME, "p")
                for p in p_tags:
                    text = (p.text or "").strip()
                    if not text:
                        continue
                    p_class = (p.get_attribute("class") or "").lower()
                    text_lower = text.lower()
                    looks_like_error = (
                        "error" in p_class
                        or "invalid" in p_class
                        or any(
                            kw in text_lower
                            for kw in (
                                "required",
                                "invalid",
                                "please",
                                "must",
                                "select",
                                "enter",
                            )
                        )
                    )
                    if not looks_like_error:
                        continue
                    label = _get_label_for_element(driver, field) or field.get_attribute("id") or field.get_attribute("name") or "(unknown)"
                    item = f"{label}: {text}"
                    if item.lower() not in seen:
                        seen.add(item.lower())
                        errors.append(item)
            except (NoSuchElementException, StaleElementReferenceException):
                continue
    except Exception:
        pass
    print(f"[greenhouse] P-tag field errors: {errors}")
    return errors


def _collect_flagged_queries(driver: webdriver.Chrome) -> tuple[list[str], list[UnfilledField]]:
    """
    After submit, scan for validation errors and unfilled fields (empty required inputs,
    empty selects). Returns (queries, unfilled_fields) for display and retry.
    """
    queries: list[str] = []
    unfilled_fields: list[UnfilledField] = []
    seen: set[str] = set()
    had_errors: list[str] = []
    try:
        # Inputs with aria-invalid="true" - get their label
        aria_invalid = driver.find_elements(By.CSS_SELECTOR, '[aria-invalid="true"]')
        print(f"[greenhouse] Found {len(aria_invalid)} elements with aria-invalid=true")
        for el in aria_invalid:
            try:
                el_id = el.get_attribute("id") or el.get_attribute("name") or "(no id)"
                label_text = _get_label_for_element(driver, el)
                desc = label_text or el_id
                had_errors.append(f"aria-invalid: {desc}")
                print(f"[greenhouse] aria-invalid el id={el_id!r} -> label={label_text!r}")
                _add_unfilled(el, driver, queries, unfilled_fields, seen, "input", "aria-invalid")
            except (NoSuchElementException, StaleElementReferenceException):
                pass

        # Empty required text inputs (not file, not hidden)
        for el in driver.find_elements(By.CSS_SELECTOR, "input[required]:not([type=file]):not([type=hidden])"):
            try:
                if not el.is_displayed():
                    continue
                val = (el.get_attribute("value") or "").strip()
                if not val:
                    _add_unfilled(el, driver, queries, unfilled_fields, seen, "input", "empty_required")
            except (NoSuchElementException, StaleElementReferenceException):
                pass

        # Empty selects / comboboxes (placeholder or no selection)
        for el in driver.find_elements(By.CSS_SELECTOR, "input[role='combobox'], input.select__input, select"):
            try:
                if not el.is_displayed():
                    continue
                tag = el.tag_name.lower()
                val = ""
                if tag == "select":
                    from selenium.webdriver.support.select import Select
                    sel = Select(el)
                    try:
                        first = sel.first_selected_option
                        val = (first.get_attribute("value") or first.text or "").strip()
                    except Exception:
                        pass
                else:
                    val = (el.get_attribute("value") or "").strip()
                if not val:
                    _add_unfilled(el, driver, queries, unfilled_fields, seen, "select", "empty")
            except (NoSuchElementException, StaleElementReferenceException):
                pass
        # Error message elements - use text or find related input's label
        # Avoid [class*="error"]/[class*="invalid"] - too broad, catches unrelated elements
        for sel in (
            '[role="alert"]',
            '.error',
            '.validation-error',
            '.field-error',
        ):
            err_els = driver.find_elements(By.CSS_SELECTOR, sel)
            if err_els:
                print(f"[greenhouse] Selector {sel!r}: found {len(err_els)} elements")
            for el in err_els:
                try:
                    if not el.is_displayed():
                        continue
                    text = (el.text or "").strip()
                    if not text or len(text) > 200:
                        continue
                    # Try to find input that references this error (aria-describedby)
                    el_id = el.get_attribute("id")
                    related_label: Optional[str] = None
                    if el_id:
                        try:
                            inp = driver.find_element(
                                By.CSS_SELECTOR, f'[aria-describedby*="{el_id}"]'
                            )
                            related_label = _get_label_for_element(driver, inp)
                        except NoSuchElementException:
                            pass
                    if related_label and related_label.lower() not in seen:
                        seen.add(related_label.lower())
                        queries.append(related_label)
                        had_errors.append(f"error({sel}): {related_label}")
                        inp_id = inp.get_attribute("id") or inp.get_attribute("name") or ""
                        inp_type = "select" if inp.get_attribute("role") == "combobox" else "input"
                        unfilled_fields.append({
                            "question": related_label,
                            "field_id": inp_id,
                            "field_type": inp_type,
                            "reason": f"error_{sel}",
                        })
                        print(f"[greenhouse] Error el -> related_label={related_label!r}")
                    elif text and text.lower() not in seen:
                        seen.add(text.lower())
                        queries.append(text)
                        had_errors.append(f"error({sel}): {text[:80]}")
                        unfilled_fields.append({
                            "question": text,
                            "field_id": "",
                            "field_type": "unknown",
                            "reason": f"error_{sel}",
                        })
                        print(f"[greenhouse] Error el -> text={text!r}")
                except (NoSuchElementException, StaleElementReferenceException):
                    pass
    except Exception:
        pass
    if had_errors:
        print(f"[greenhouse] Elements that had errors: {had_errors}")
    print(f"[greenhouse] Flagged queries collected: {queries}")
    print(f"[greenhouse] Unfilled fields (for retry): {unfilled_fields}")
    return queries, unfilled_fields


def _retry_fill_unfilled(
    driver: webdriver.Chrome,
    unfilled_fields: list[UnfilledField],
    extra_answers: dict[str, str],
) -> int:
    """
    Retry filling unfilled fields. Uses extra_answers (question -> answer) and
    _SELECT_QUESTION_RULES for selects. Returns count of fields filled.
    """
    filled = 0
    for uf in unfilled_fields:
        question = (uf.get("question") or "").strip().lower()
        field_id = uf.get("field_id") or ""
        field_type = uf.get("field_type") or ""
        if not question:
            continue
        answer: Optional[str] = None
        for k, v in extra_answers.items():
            if k.strip().lower() == question:
                answer = v
                break
        if not answer and field_type == "select":
            for keywords, answers in _SELECT_QUESTION_RULES:
                if any(kw.lower() in question for kw in keywords):
                    answer = answers[0] if answers else None
                    break
        if not answer:
            continue
        el: Optional[WebElement] = None
        try:
            if field_id:
                try:
                    el = driver.find_element(By.ID, field_id)
                except NoSuchElementException:
                    pass
            if not el:
                # Find by label text (scan labels for matching question)
                for lbl in driver.find_elements(By.CSS_SELECTOR, "label"):
                    if not lbl.is_displayed():
                        continue
                    if (lbl.text or "").strip().lower() == question:
                        lid = lbl.get_attribute("for")
                        if lid:
                            try:
                                el = driver.find_element(By.ID, lid)
                                break
                            except NoSuchElementException:
                                pass
                        try:
                            container = lbl.find_element(By.XPATH, "./ancestor::div[contains(@class,'select') or contains(@class,'select_container')][1]")
                            el = container.find_element(By.CSS_SELECTOR, "input[role='combobox'], input.select__input, input[id]")
                            break
                        except NoSuchElementException:
                            pass
            if not el:
                continue
            if not el.is_displayed():
                continue
            if field_type == "select":
                el.click()
                time.sleep(_DELAY_SELECT_OPEN)
                time.sleep(_DELAY_SELECT_BEFORE_CHOOSE)
                try:
                    el.clear()
                except Exception:
                    pass
                _send_keys_slow(el, answer)
                time.sleep(_DELAY_SELECT_TYPE)
                el.send_keys(Keys.ENTER)
                time.sleep(_DELAY_BETWEEN_SELECTS)
                _click_away(driver)
                filled += 1
                print(f"[greenhouse] Retry filled select: {question[:40]!r} -> {answer!r}")
            else:
                el.click()
                time.sleep(0.2)
                el.clear()
                _send_keys_slow(el, answer)
                time.sleep(_DELAY_BETWEEN_FIELDS)
                filled += 1
                print(f"[greenhouse] Retry filled input: {question[:40]!r} -> {answer!r}")
        except NoSuchElementException:
            pass
    return filled


def _get_label_for_element(driver: webdriver.Chrome, el: WebElement) -> Optional[str]:
    """Get the label or question text for an input (label, aria-labelledby, or text right above)."""
    try:
        el_id = el.get_attribute("id")
        if el_id:
            try:
                label = driver.find_element(By.CSS_SELECTOR, f'label[for="{el_id}"]')
                if label.is_displayed():
                    t = (label.text or "").strip()
                    if t:
                        return t
            except NoSuchElementException:
                pass
        labelledby = el.get_attribute("aria-labelledby")
        if labelledby:
            for lid in labelledby.split():
                try:
                    lbl = driver.find_element(By.ID, lid.strip())
                    if lbl.is_displayed():
                        t = (lbl.text or "").strip()
                        if t:
                            return t
                except NoSuchElementException:
                    pass
        try:
            parent = el.find_element(By.XPATH, "./ancestor::label[1]")
            if parent and parent.is_displayed():
                t = (parent.text or "").strip()
                if t:
                    return t
        except NoSuchElementException:
            pass
        # Text right above: preceding sibling or parent's preceding sibling (label, div, span, p)
        for xpath in (
            "./preceding-sibling::label[1]",
            "./preceding-sibling::div[1]",
            "./preceding-sibling::span[1]",
            "./preceding-sibling::p[1]",
            "./parent::*/preceding-sibling::label[1]",
            "./parent::*/preceding-sibling::div[1]",
            "./parent::*/preceding-sibling::span[1]",
            "./parent::*/preceding-sibling::p[1]",
        ):
            try:
                node = el.find_element(By.XPATH, xpath)
                if node and node.is_displayed():
                    t = (node.text or "").strip()
                    if t and len(t) < 300:
                        return t
            except NoSuchElementException:
                pass
    except (NoSuchElementException, StaleElementReferenceException):
        pass
    return None


def _extract_form_fields_from_dom(driver: webdriver.Chrome) -> list[dict]:
    """Extract all visible form fields with their labels, IDs, types, and current values."""
    fields: list[dict] = []
    seen_keys: set[str] = set()
    try:
        elements = driver.find_elements(
            By.CSS_SELECTOR,
            "input:not([type=hidden]):not([type=file]):not([type=submit]):not([type=button]):not([type=reset]),"
            " select, textarea",
        )
        for el in elements:
            try:
                if not el.is_displayed():
                    continue
                el_id = el.get_attribute("id") or ""
                el_name = el.get_attribute("name") or ""
                tag = el.tag_name.lower()
                el_type = el.get_attribute("type") or tag
                role = el.get_attribute("role") or ""
                val = (el.get_attribute("value") or "").strip()
                placeholder = el.get_attribute("placeholder") or ""
                label = _get_label_for_element(driver, el) or ""
                key = el_id or el_name or label
                if not key or key in seen_keys:
                    continue
                seen_keys.add(key)
                fields.append({
                    "id": el_id,
                    "name": el_name,
                    "type": "select" if (tag == "select" or role == "combobox") else el_type,
                    "label": label,
                    "current_value": val,
                    "placeholder": placeholder,
                })
            except (NoSuchElementException, StaleElementReferenceException):
                continue
    except Exception:
        pass
    return fields


def _ask_grok_for_fields(
    driver: webdriver.Chrome,
    applicant_info: dict[str, str],
    already_filled_ids: set[str],
) -> dict[str, str]:
    """
    Use Grok vision AI to analyze the form screenshot and suggest answers for
    any unfilled fields not already handled by rule-based logic.
    Returns {field_id: answer} dict (or {label: answer} when id is absent).
    """
    import json as _json

    if not settings.grok_api_key:
        print("[greenhouse] Grok API key not set, skipping AI field detection")
        return {}
    try:
        fields = _extract_form_fields_from_dom(driver)
        unfilled = [
            f for f in fields
            if f["id"] not in already_filled_ids
            and f["name"] not in already_filled_ids
            and not f["current_value"]
        ]
        if not unfilled:
            print("[greenhouse] Grok: no unfilled fields detected, skipping")
            return {}

        screenshot_b64 = driver.get_screenshot_as_base64()
        fields_text = _json.dumps(unfilled, indent=2)
        applicant_text = _json.dumps(applicant_info, indent=2)
        prompt = (
            "You are filling out a job application form on Greenhouse.\n\n"
            f"Applicant info:\n{applicant_text}\n\n"
            f"Unfilled form fields (id, label, type):\n{fields_text}\n\n"
            "Look at the screenshot and the field list. Return ONLY a valid JSON object "
            "mapping each field's \"id\" (use \"label\" when id is empty) to the correct answer.\n\n"
            "Core philosophy: answer honestly but optimistically to maximize hiring chances.\n"
            "- COMMITMENTS the applicant can genuinely make → answer positively (Yes, willing, open to it)\n"
            "- VERIFIABLE FACTS (certifications, specific tools, degrees, years of exp) → be honest; don't claim something that could be checked and disproven in an interview\n\n"
            "Fixed rules:\n"
            "- Work authorization / legally authorized to work → \"Yes\"\n"
            "- Sponsorship required / need visa sponsorship → \"No\"\n"
            "- Veteran status → \"I am not a protected veteran\"\n"
            "- Disability → \"I don't wish to answer\"\n"
            "- Gender → \"Male\"\n"
            "- Race/ethnicity → \"I don't wish to answer\"\n"
            "- LinkedIn/website/portfolio URL → omit (leave empty)\n"
            "- Salary/compensation → omit\n"
            "- Any field already having a value → omit\n\n"
            "For everything else:\n"
            "- Willingness to relocate, travel, work on-site, work overtime → \"Yes\" (commitment)\n"
            "- Availability / start date → soonest option or 'Immediately' (commitment)\n"
            "- Employment type → 'Full-time' (commitment)\n"
            "- 'How did you hear about us?' → 'LinkedIn' or 'Company Website' (shows intent, not verifiable)\n"
            "- Specific skill / tool / certification you may not have → honest; pick 'No' or the lower option\n"
            "- Years of experience → pick honestly based on context; don't over-inflate\n"
            "- Free-text field you cannot determine → omit (empty string)\n"
            "Do NOT omit a select/dropdown — always provide an answer.\n\n"
            "Return ONLY the JSON object with no explanation."
        )

        client = OpenAI(api_key=settings.grok_api_key, base_url="https://api.x.ai/v1")
        response = client.chat.completions.create(
            model="grok-2-vision-1212",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{screenshot_b64}",
                                "detail": "high",
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
            max_tokens=1000,
            temperature=0.1,
        )
        content = response.choices[0].message.content or ""
        print(f"[greenhouse] Grok raw response: {content[:600]}")
        start = content.find("{")
        end = content.rfind("}") + 1
        if start == -1 or end == 0:
            print("[greenhouse] Grok: no JSON object found in response")
            return {}
        answers = _json.loads(content[start:end])
        if not isinstance(answers, dict):
            return {}
        clean = {str(k): str(v) for k, v in answers.items() if v and str(v).strip()}
        print(f"[greenhouse] Grok suggested {len(clean)} answer(s): {clean}")
        return clean
    except Exception as e:
        print(f"[greenhouse] Grok error: {type(e).__name__}: {e}")
        return {}


def _apply_grok_answers(driver: webdriver.Chrome, answers: dict[str, str]) -> int:
    """
    Fill form fields using answers from Grok. Tries to find each field by ID then by label.
    Returns number of fields successfully filled.
    """
    filled = 0
    for field_ref, answer in answers.items():
        if not answer or not field_ref:
            continue
        el: Optional[WebElement] = None
        is_select = False
        try:
            try:
                candidate = driver.find_element(By.ID, field_ref)
                if candidate.is_displayed():
                    el = candidate
            except NoSuchElementException:
                pass
            if not el:
                for lbl in driver.find_elements(By.CSS_SELECTOR, "label"):
                    if not lbl.is_displayed():
                        continue
                    if (lbl.text or "").strip().lower() == field_ref.lower():
                        lid = lbl.get_attribute("for")
                        if lid:
                            try:
                                candidate = driver.find_element(By.ID, lid)
                                if candidate.is_displayed():
                                    el = candidate
                                    break
                            except NoSuchElementException:
                                pass
                        try:
                            container = lbl.find_element(
                                By.XPATH,
                                "./ancestor::div[contains(@class,'select') or contains(@class,'select_container')][1]",
                            )
                            el = container.find_element(
                                By.CSS_SELECTOR, "input[role='combobox'], input.select__input"
                            )
                            break
                        except NoSuchElementException:
                            pass
            if not el:
                continue
            tag = el.tag_name.lower()
            role = el.get_attribute("role") or ""
            is_select = tag == "select" or role == "combobox"
            # Skip if already has a value
            current = (el.get_attribute("value") or "").strip()
            if current:
                print(f"[greenhouse] Grok skip (already filled): {field_ref!r} = {current!r}")
                continue
            if is_select:
                el.click()
                time.sleep(_DELAY_SELECT_OPEN)
                time.sleep(_DELAY_SELECT_BEFORE_CHOOSE)
                try:
                    el.clear()
                except Exception:
                    pass
                _send_keys_slow(el, answer)
                time.sleep(_DELAY_SELECT_TYPE)
                el.send_keys(Keys.ENTER)
                time.sleep(_DELAY_BETWEEN_SELECTS)
                _click_away(driver)
            else:
                el.click()
                time.sleep(0.2)
                el.clear()
                _send_keys_slow(el, answer)
                time.sleep(_DELAY_BETWEEN_FIELDS)
                _click_away(driver)
            filled += 1
            print(f"[greenhouse] Grok filled: {field_ref!r} -> {answer!r}")
        except (NoSuchElementException, StaleElementReferenceException):
            continue
        except Exception as e:
            print(f"[greenhouse] Grok fill error for {field_ref!r}: {e}")
    return filled


def _get_combobox_options(driver: webdriver.Chrome, el: WebElement) -> list[str]:
    """Open a combobox, scrape visible option text, then close it."""
    options: list[str] = []
    try:
        el.click()
        time.sleep(_DELAY_SELECT_OPEN + _DELAY_SELECT_BEFORE_CHOOSE)
        for sel in (
            '[role="option"]',
            '[class*="option"]:not([class*="input"]):not([class*="container"])',
            'li[class*="item"]',
            'div[class*="menu"] li',
            'div[class*="dropdown"] li',
        ):
            try:
                items = driver.find_elements(By.CSS_SELECTOR, sel)
                texts = [i.text.strip() for i in items if i.is_displayed() and i.text.strip()]
                if texts:
                    options = texts
                    break
            except Exception:
                continue
    except Exception:
        pass
    finally:
        _click_away(driver)
    return options


def _collect_empty_select_fields(driver: webdriver.Chrome) -> list[dict]:
    """
    Scan all visible select/combobox elements. For those that are empty, collect
    their label and full list of available options so AI can choose the right one.
    """
    from selenium.webdriver.support.select import Select as _Select

    result: list[dict] = []
    seen: set[str] = set()
    try:
        elements = driver.find_elements(
            By.CSS_SELECTOR,
            "input[role='combobox'], input.select__input, select",
        )
        for el in elements:
            try:
                if not el.is_displayed():
                    continue
                tag = el.tag_name.lower()
                el_id = el.get_attribute("id") or ""
                label = _get_label_for_element(driver, el) or el_id or ""
                key = el_id or label
                if not key or key in seen:
                    continue

                if tag == "select":
                    sel_obj = _Select(el)
                    try:
                        cur_val = (sel_obj.first_selected_option.get_attribute("value") or
                                   sel_obj.first_selected_option.text or "").strip()
                    except Exception:
                        cur_val = ""
                    if cur_val and cur_val not in ("", "0"):
                        continue
                    options = [
                        o.text.strip() for o in sel_obj.options
                        if o.text.strip() and (o.get_attribute("value") or "").strip() not in ("", "0")
                    ]
                    field_type = "select"
                else:
                    cur_val = (el.get_attribute("value") or "").strip()
                    if cur_val:
                        continue
                    options = _get_combobox_options(driver, el)
                    field_type = "combobox"

                if not options:
                    continue
                seen.add(key)
                result.append({
                    "id": el_id,
                    "label": label,
                    "type": field_type,
                    "options": options,
                })
                print(f"[greenhouse] Empty select found: {label!r} ({field_type}) options={options}")
            except (NoSuchElementException, StaleElementReferenceException):
                continue
    except Exception:
        pass
    return result


def _ask_grok_for_select_answers(
    fields: list[dict],
    applicant_info: dict[str, str],
) -> dict[str, str]:
    """
    Send every empty select field (with its full options list) to Grok in one call.
    Returns {field_id_or_label: chosen_option_text}.
    Uses the text-only model — no screenshot needed since we have the exact option strings.
    """
    import json as _json

    if not settings.grok_api_key:
        return {}
    try:
        from openai import OpenAI

        fields_text = _json.dumps(fields, indent=2)
        applicant_text = _json.dumps(applicant_info, indent=2)
        prompt = (
            "You are filling out a job application form on Greenhouse.\n\n"
            f"Applicant info:\n{applicant_text}\n\n"
            "Below are dropdown/select fields that still need an answer. "
            "Each entry has an 'id', 'label', 'type', and the exact 'options' available.\n\n"
            f"{fields_text}\n\n"
            "For EVERY field listed, choose EXACTLY one option from its 'options' list.\n\n"
            "Core philosophy: answer honestly but optimistically to maximize hiring chances.\n"
            "- COMMITMENTS the applicant can genuinely make → answer positively\n"
            "- VERIFIABLE FACTS (specific tools, certs, degrees, years of experience) → be honest; "
            "don't claim something that could be checked and disproven in an interview\n\n"
            "Fixed rules:\n"
            "- Work authorization / legally authorized to work in the US → 'Yes' option\n"
            "- Sponsorship / visa sponsorship required → 'No' option\n"
            "- Veteran status → option closest to 'I am not a protected veteran'\n"
            "- Disability → 'I don't wish to answer' or 'I do not have a disability'\n"
            "- Gender → 'Male' or closest option\n"
            "- Race / ethnicity → 'I don't wish to answer' or 'Decline to self-identify'\n\n"
            "For everything else:\n"
            "- Willingness to relocate, travel, work on-site, work overtime → 'Yes' (commitment)\n"
            "- Availability / start date → soonest option (commitment)\n"
            "- Employment type → 'Full-time' (commitment)\n"
            "- 'How did you hear about us?' → 'LinkedIn' or 'Company Website' (not verifiable, shows intent)\n"
            "- Specific skill, tool, certification the applicant may not have → honest; pick 'No' or the lower/entry option\n"
            "- Years of experience → pick honestly; don't over-inflate\n"
            "- Any other unknown field → pick the option that sounds most motivated and capable\n\n"
            "Return ONLY a valid JSON object mapping each field's 'id' (use 'label' when id is empty) "
            "to the chosen option string — copied exactly from the options list, no paraphrasing.\n"
            "Example: {\"field_id\": \"No\", \"other_label\": \"I don't wish to answer\"}"
        )

        client = OpenAI(api_key=settings.grok_api_key, base_url="https://api.x.ai/v1")
        response = client.chat.completions.create(
            model="grok-beta",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=600,
            temperature=0.1,
        )
        content = response.choices[0].message.content or ""
        print(f"[greenhouse] Grok select batch response: {content[:500]}")
        start = content.find("{")
        end = content.rfind("}") + 1
        if start == -1 or end == 0:
            return {}
        answers = _json.loads(content[start:end])
        return {str(k): str(v) for k, v in answers.items() if v and str(v).strip()}
    except Exception as e:
        print(f"[greenhouse] Grok select batch error: {type(e).__name__}: {e}")
        return {}


_SAFE_SELECT_DEFAULTS = [
    "No",
    "I don't wish to answer",
    "Decline to self-identify",
    "I prefer not to answer",
    "Prefer not to say",
    "Prefer not to answer",
]


def _ensure_selects_filled(
    driver: webdriver.Chrome,
    applicant_info: dict[str, str],
) -> int:
    """
    Collect every still-empty select/combobox, ask Grok to pick the right answer
    from its exact option list, then fill each one. Falls back to safe defaults
    if Grok is not configured.
    Returns count of fields newly filled.
    """
    from selenium.webdriver.support.select import Select as _Select

    fields = _collect_empty_select_fields(driver)
    if not fields:
        print("[greenhouse] No empty selects to fill")
        return 0

    print(f"[greenhouse] Asking Grok to pick answers for {len(fields)} empty select(s)...")
    ai_answers = _ask_grok_for_select_answers(fields, applicant_info)

    filled = 0
    for field_info in fields:
        el_id = field_info["id"]
        label = field_info["label"]
        field_type = field_info["type"]
        options: list[str] = field_info["options"]
        key = el_id or label

        # AI answer (by id first, then label)
        answer = ai_answers.get(el_id) or ai_answers.get(label)

        # Validate: answer must be one of the actual options (case-insensitive partial ok)
        if answer:
            match = next((o for o in options if answer.lower() == o.lower()), None)
            if not match:
                match = next((o for o in options if answer.lower() in o.lower()), None)
            answer = match  # None if truly not found

        # Safe-default fallback when AI gave no usable answer
        if not answer:
            for default in _SAFE_SELECT_DEFAULTS:
                match = next((o for o in options if default.lower() in o.lower()), None)
                if match:
                    answer = match
                    break
        if not answer:
            answer = options[0] if options else None
        if not answer:
            continue

        # Find the element
        el: Optional[WebElement] = None
        try:
            if el_id:
                el = driver.find_element(By.ID, el_id)
            else:
                for lbl in driver.find_elements(By.CSS_SELECTOR, "label"):
                    if (lbl.text or "").strip().lower() == label.lower():
                        lid = lbl.get_attribute("for")
                        if lid:
                            try:
                                el = driver.find_element(By.ID, lid)
                                break
                            except NoSuchElementException:
                                pass
            if not el or not el.is_displayed():
                continue

            if field_type == "select":
                sel_obj = _Select(el)
                try:
                    sel_obj.select_by_visible_text(answer)
                except Exception:
                    # Partial-match fallback
                    for opt in sel_obj.options:
                        if answer.lower() in opt.text.lower():
                            sel_obj.select_by_visible_text(opt.text)
                            break
                _click_away(driver)
            else:
                el.click()
                time.sleep(_DELAY_SELECT_OPEN)
                time.sleep(_DELAY_SELECT_BEFORE_CHOOSE)
                try:
                    el.clear()
                except Exception:
                    pass
                _send_keys_slow(el, answer)
                time.sleep(_DELAY_SELECT_TYPE)
                el.send_keys(Keys.ENTER)
                time.sleep(_DELAY_BETWEEN_SELECTS)
                _click_away(driver)

            filled += 1
            print(f"[greenhouse] Ensure filled: {label!r} -> {answer!r}")
        except (NoSuchElementException, StaleElementReferenceException):
            continue
        except Exception as e:
            print(f"[greenhouse] Ensure fill error for {label!r}: {e}")
    return filled


def _find_resume_input(driver: webdriver.Chrome) -> Optional[WebElement]:
    """
    Find the resume file input. Greenhouse often hides the real <input type=file>
    behind a styled 'Attach' button, so we look for it even when not visible and
    use JS to make it interactable.
    """
    candidates: list[WebElement] = []
    # Preferred: id=resume
    try:
        el = driver.find_element(By.CSS_SELECTOR, 'input[type="file"]#resume')
        candidates.insert(0, el)
    except NoSuchElementException:
        pass
    # Any file input on the page
    for el in driver.find_elements(By.CSS_SELECTOR, 'input[type="file"]'):
        if el not in candidates:
            candidates.append(el)
    for el in candidates:
        try:
            # Make it interactable even if hidden behind an "Attach" button
            driver.execute_script(
                "arguments[0].style.display='block';"
                "arguments[0].style.visibility='visible';"
                "arguments[0].style.opacity='1';"
                "arguments[0].removeAttribute('hidden');",
                el,
            )
            return el
        except Exception:
            continue
    return None


def _fill_text_safe(driver: webdriver.Chrome, field_id: str, value: str) -> bool:
    """Find field by id, fill it. Retry once on stale. Returns True if filled."""
    for _ in range(2):
        el = _find_input_by_id(driver, field_id)
        if not el:
            return False
        try:
            el.click()
            time.sleep(0.2)
            el.clear()
            _send_keys_slow(el, value)
            time.sleep(_DELAY_BETWEEN_FIELDS)
            return True
        except StaleElementReferenceException:
            time.sleep(0.5)
            continue
        except Exception:
            return False
    return False


def apply_to_greenhouse(
    application_url: str,
    first_name: str,
    last_name: str,
    email: str,
    phone: str,
    resume_path: str,
    address: Optional[str] = None,
    headless: Optional[bool] = None,
    timeout: int = 15,
    submit: bool = False,
    extra_answers: Optional[dict[str, str]] = None,
) -> dict[str, str | bool]:
    """
    Open a Greenhouse job application page and fill standard fields.

    Returns:
        Dict with "success", "message", and optional "submit_clicked".
    """
    resume_file = Path(resume_path).resolve()
    if not resume_file.is_file():
        return {
            "success": False,
            "message": f"Resume file not found: {resume_path}",
        }

    headless = headless if headless is not None else settings.selenium_headless
    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    driver: Optional[webdriver.Chrome] = None
    last_error: Optional[str] = None

    try:
        driver = webdriver.Chrome(options=options)
        driver.implicitly_wait(0)  # Use explicit waits only

        driver.get(application_url)
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        time.sleep(_DELAY_AFTER_PAGE)
        _wait_form_ready(driver, timeout=timeout)
        time.sleep(0.5)

        filled: list[str] = []
        failed: list[str] = []

        if _fill_text_safe(driver, "first_name", first_name):
            filled.append("first_name")
        else:
            failed.append("first_name")

        if _fill_text_safe(driver, "last_name", last_name):
            filled.append("last_name")
        else:
            failed.append("last_name")

        if _fill_text_safe(driver, "email", email):
            filled.append("email")
        else:
            failed.append("email")

        if _fill_text_safe(driver, "phone", phone):
            filled.append("phone")
        else:
            failed.append("phone")

        if address:
            if _fill_text_safe(driver, "address", address):
                filled.append("address")
            else:
                failed.append("address")

        if _select_country_united_states(driver):
            filled.append("country")
        time.sleep(_DELAY_BETWEEN_FIELDS)

        select_count = _fill_select_questions_by_keywords(driver)
        if select_count > 0:
            filled.append(f"select_questions({select_count})")
        time.sleep(_DELAY_BETWEEN_FIELDS)

        # AI-powered field detection: send screenshot + field list to Grok to fill
        # anything that wasn't covered by the standard rule-based logic above.
        already_filled_ids = {"first_name", "last_name", "email", "phone", "address", "country", "resume"}
        grok_answers = _ask_grok_for_fields(
            driver,
            applicant_info={
                "first_name": first_name,
                "last_name": last_name,
                "email": email,
                "phone": phone,
                "address": address or "",
            },
            already_filled_ids=already_filled_ids,
        )
        if grok_answers:
            grok_filled = _apply_grok_answers(driver, grok_answers)
            if grok_filled:
                filled.append(f"grok_ai({grok_filled})")
            time.sleep(_DELAY_BETWEEN_FIELDS)

        # Ensure every select/combobox has a value — ask AI to pick from real options
        ensured = _ensure_selects_filled(
            driver,
            applicant_info={
                "first_name": first_name,
                "last_name": last_name,
                "email": email,
                "phone": phone,
                "address": address or "",
            },
        )
        if ensured:
            filled.append(f"ensured_selects({ensured})")
        time.sleep(_DELAY_BETWEEN_FIELDS)

        # Upload resume — file inputs are often hidden behind an "Attach" button on Greenhouse
        resume_el = _find_resume_input(driver)
        print(f"[greenhouse] Resume input: {'found' if resume_el else 'not found'}")
        resume_uploaded = False
        if resume_el:
            try:
                resume_el.send_keys(str(resume_file))
                resume_uploaded = True
                filled.append("resume")
                time.sleep(_DELAY_BETWEEN_FIELDS)
            except Exception as exc:
                print(f"[greenhouse] Resume send_keys failed: {exc}")
        if not resume_uploaded:
            # Try clicking any visible "Attach" / "Upload" button near a resume label
            for btn_sel in (
                'button[aria-label*="resume" i]',
                'button[aria-label*="attach" i]',
                'label[for="resume"]',
                'label[class*="attach" i]',
                'a[class*="attach" i]',
                'span[class*="attach" i]',
                '[data-mapped-name*="resume" i]',
            ):
                try:
                    btn = driver.find_element(By.CSS_SELECTOR, btn_sel)
                    if btn.is_displayed():
                        btn.click()
                        time.sleep(1.0)
                        # After clicking the trigger the hidden input may now accept keys
                        resume_el2 = _find_resume_input(driver)
                        if resume_el2:
                            resume_el2.send_keys(str(resume_file))
                            resume_uploaded = True
                            filled.append("resume")
                            time.sleep(_DELAY_BETWEEN_FIELDS)
                            print(f"[greenhouse] Resume uploaded via attach trigger: {btn_sel!r}")
                            break
                except (NoSuchElementException, Exception):
                    continue
        if not resume_uploaded:
            failed.append("resume")

        time.sleep(1.0)
        submit_clicked = False
        flagged_queries: list[str] = []
        unfilled_fields: list[UnfilledField] = []
        p_tag_errors: list[str] = []
        if submit:
            for selector in (
                'button[type="submit"]',
                'input[type="submit"]',
                '[data-mapped-name="submit"]',
                'input[value*="Submit"]',
                'input[value*="Apply"]',
            ):
                try:
                    btn = driver.find_element(By.CSS_SELECTOR, selector)
                    if btn.is_displayed():
                        print(f"[greenhouse] Submit button found: {selector!r}")
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                        btn.click()
                        submit_clicked = True
                        break
                except NoSuchElementException:
                    continue
            if submit_clicked:
                time.sleep(2.0)  # Wait for validation to appear
                p_tag_errors = _collect_p_tag_errors_in_field_div(driver)
                flagged_queries, unfilled_fields = _collect_flagged_queries(driver)
                # Retry: fill unfilled fields using extra_answers, Grok, or _SELECT_QUESTION_RULES
                if unfilled_fields:
                    # Ask Grok again about the remaining unfilled fields after submit errors
                    post_submit_grok = _ask_grok_for_fields(
                        driver,
                        applicant_info={
                            "first_name": first_name,
                            "last_name": last_name,
                            "email": email,
                            "phone": phone,
                            "address": address or "",
                        },
                        already_filled_ids=already_filled_ids,
                    )
                    merged_extra = {**post_submit_grok, **(extra_answers or {})}
                    retry_filled = _retry_fill_unfilled(
                        driver, unfilled_fields, merged_extra
                    )
                    if retry_filled > 0:
                        print(f"[greenhouse] Retry filled {retry_filled} field(s), submitting again")
                        time.sleep(1.0)
                        for selector in (
                            'button[type="submit"]',
                            'input[type="submit"]',
                            '[data-mapped-name="submit"]',
                            'input[value*="Submit"]',
                            'input[value*="Apply"]',
                        ):
                            try:
                                btn = driver.find_element(By.CSS_SELECTOR, selector)
                                if btn.is_displayed():
                                    btn.click()
                                    break
                            except NoSuchElementException:
                                continue
                        time.sleep(2.0)
                        p_tag_errors = _collect_p_tag_errors_in_field_div(driver)
                        flagged_queries, unfilled_fields = _collect_flagged_queries(driver)

        print(f"[greenhouse] Filled: {filled}, Failed: {failed}")
        if failed:
            out: dict[str, str | bool | list[str] | list[UnfilledField]] = {
                "success": False,
                "message": f"Could not find or fill: {', '.join(failed)}. Filled: {', '.join(filled)}.",
                "submit_clicked": submit_clicked,
            }
            if flagged_queries:
                out["flagged_queries"] = flagged_queries
            if unfilled_fields:
                out["unfilled_fields"] = unfilled_fields
            if p_tag_errors:
                out["p_tag_errors"] = p_tag_errors
            return out

        out = {
            "success": True,
            "message": f"Filled: {', '.join(filled)}." + (" Submit clicked." if submit_clicked else ""),
            "submit_clicked": submit_clicked,
        }
        if flagged_queries:
            out["flagged_queries"] = flagged_queries
        if unfilled_fields:
            out["unfilled_fields"] = unfilled_fields
        if p_tag_errors:
            out["p_tag_errors"] = p_tag_errors
        return out

    except TimeoutException as e:
        last_error = f"Page or form did not load in time: {e!s}"
    except Exception as e:
        last_error = f"{type(e).__name__}: {e!s}"
    finally:
        time.sleep(10)
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass

    if last_error:
        return {
            "success": False,
            "message": last_error,
            "submit_clicked": False,
        }
    return {
        "success": False,
        "message": "Unknown error",
        "submit_clicked": False,
    }
