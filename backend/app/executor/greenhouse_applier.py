"""
Selenium-based filler for Greenhouse job application forms.

Fills common fields: first name, last name, email, phone, resume upload,
and optional address. Uses multiple selector strategies to handle
company-specific Greenhouse form customizations.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

from app.core.config import settings


# Common Greenhouse form field names (and common variants).
_FIELD_SELECTORS = {
    "first_name": [
        'input[name="first_name"]',
        'input#first_name',
        'input[placeholder*="First"]',
        'input[aria-label*="first"]',
    ],
    "last_name": [
        'input[name="last_name"]',
        'input#last_name',
        'input[placeholder*="Last"]',
        'input[aria-label*="last"]',
    ],
    "email": [
        'input[name="email"]',
        'input#email',
        'input[type="email"]',
    ],
    "phone": [
        'input[name="phone"]',
        'input#phone',
        'input[type="tel"]',
        'input[placeholder*="phone"]',
    ],
    "address": [
        'input[name="address"]',
        'input#address',
        'input[name="location"]',
        'input[placeholder*="address"]',
        'input[placeholder*="location"]',
    ],
    "resume": [
        'input[type="file"][name="resume"]',
        'input[type="file"][name="job_application[resume]"]',
        'input[type="file"]',
    ],
}


def _find_field(driver: webdriver.Chrome, wait: WebDriverWait, field_key: str) -> Optional[WebElement]:
    """Find a form field using configured selector list. Returns None if not found."""
    selectors = _FIELD_SELECTORS.get(field_key, [])
    for selector in selectors:
        try:
            el = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
            if el.is_displayed():
                return el
        except TimeoutException:
            continue
    # Fallback: by name attribute
    name_map = {
        "first_name": "first_name",
        "last_name": "last_name",
        "email": "email",
        "phone": "phone",
        "address": "address",
        "resume": None,
    }
    name = name_map.get(field_key)
    if name:
        try:
            el = driver.find_element(By.CSS_SELECTOR, f'input[name="{name}"]')
            if el.is_displayed():
                return el
        except NoSuchElementException:
            pass
    return None


def _fill_text(element: WebElement, value: str, clear_first: bool = True) -> None:
    element.click()
    if clear_first:
        element.clear()
    element.send_keys(value)


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
) -> dict[str, str | bool]:
    """
    Open a Greenhouse job application page and fill standard fields with Selenium.

    Args:
        application_url: Full URL of the Greenhouse "Apply" page.
        first_name: Applicant first name.
        last_name: Applicant last name.
        email: Email address.
        phone: Phone number.
        resume_path: Absolute or relative path to the resume file (PDF or DOC).
        address: Optional address/location string.
        headless: If True, run Chrome headless. Defaults to settings.selenium_headless.
        timeout: Max seconds to wait for form elements.
        submit: If True, look for and click a submit button after filling (default False).

    Returns:
        Dict with "success" (bool), "message" (str), and optional "submit_clicked" (bool).
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
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    driver: Optional[webdriver.Chrome] = None
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        driver.implicitly_wait(3)
        wait = WebDriverWait(driver, timeout)

        driver.get(application_url)
        wait.until(lambda d: d.execute_script("return document.readyState") == "complete")

        filled: list[str] = []
        failed: list[str] = []

        # First name
        el = _find_field(driver, wait, "first_name")
        if el:
            _fill_text(el, first_name)
            filled.append("first_name")
        else:
            failed.append("first_name")

        # Last name
        el = _find_field(driver, wait, "last_name")
        if el:
            _fill_text(el, last_name)
            filled.append("last_name")
        else:
            failed.append("last_name")

        # Email
        el = _find_field(driver, wait, "email")
        if el:
            _fill_text(el, email)
            filled.append("email")
        else:
            failed.append("email")

        # Phone
        el = _find_field(driver, wait, "phone")
        if el:
            _fill_text(el, phone)
            filled.append("phone")
        else:
            failed.append("phone")

        # Optional address
        if address:
            el = _find_field(driver, wait, "address")
            if el:
                _fill_text(el, address)
                filled.append("address")
            else:
                failed.append("address")

        # Resume (file input)
        el = _find_field(driver, wait, "resume")
        if el:
            el.send_keys(str(resume_file))
            filled.append("resume")
        else:
            failed.append("resume")

        submit_clicked = False
        if submit:
            for selector in [
                'button[type="submit"]',
                'input[type="submit"]',
                'a[data-mapped-name="submit"]',
                '[data-mapped-name="submit"]',
                'button[class*="submit"], input[value*="Submit"], input[value*="Apply"]',
                '.submit',
            ]:
                try:
                    btn = driver.find_element(By.CSS_SELECTOR, selector)
                    if btn.is_displayed():
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                        btn.click()
                        submit_clicked = True
                        break
                except NoSuchElementException:
                    continue

        if failed:
            return {
                "success": False,
                "message": f"Could not find or fill fields: {', '.join(failed)}. Filled: {', '.join(filled)}.",
                "submit_clicked": submit_clicked,
            }

        return {
            "success": True,
            "message": f"Filled: {', '.join(filled)}. Review the form and submit manually." + (
                " Submit button clicked." if submit_clicked else ""
            ),
            "submit_clicked": submit_clicked,
        }
    except TimeoutException as e:
        return {
            "success": False,
            "message": f"Page or form did not load in time: {e!s}",
            "submit_clicked": False,
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Error: {e!s}",
            "submit_clicked": False,
        }
    finally:
        if driver is not None:
            driver.quit()
