"""
Browser automation module for AI Job Hunter Agent.

Provides Playwright-based browser control for job portal scraping
and application submission.
"""

import logging
from contextlib import contextmanager
from typing import Any, Generator, List, Optional

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

from config.settings import settings

logger = logging.getLogger(__name__)

# Args that reduce "automation" detection (sites like Naukri may block headless otherwise)
STEALTH_LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-infobars",
    "--window-size=1920,1080",
]


@contextmanager
def get_browser(
    headless: Optional[bool] = None,
    launch_timeout_ms: Optional[int] = None,
    channel: Optional[str] = None,
    args: Optional[List[str]] = None,
) -> Generator[Browser, None, None]:
    """
    Context manager for Playwright browser instance.

    Args:
        headless: Run browser headless. Uses settings if None.
        launch_timeout_ms: Max ms to wait for browser launch. Uses settings.browser_timeout_ms if None.
        channel: Browser channel, e.g. "chrome" to use installed Chrome.
        args: Extra launch args (e.g. STEALTH_LAUNCH_ARGS to reduce bot detection).

    Yields:
        Playwright Browser instance.
    """
    headless = headless if headless is not None else settings.headless
    timeout = launch_timeout_ms if launch_timeout_ms is not None else settings.browser_timeout_ms
    launch_kw: dict = {"headless": headless, "timeout": timeout}
    if args:
        launch_kw["args"] = args
    with sync_playwright() as p:
        try:
            if channel:
                browser = p.chromium.launch(**{**launch_kw, "channel": channel})
            else:
                browser = p.chromium.launch(**launch_kw)
        except Exception as e:
            if channel:
                logger.debug("Launch with channel=%s failed (%s), retrying with Chromium", channel, e)
                launch_kw.pop("channel", None)
                browser = p.chromium.launch(**launch_kw)
            else:
                raise
        try:
            yield browser
        finally:
            browser.close()


@contextmanager
def get_browser_context(
    browser: Optional[Browser] = None,
    **kwargs: Any,
) -> Generator[BrowserContext, None, None]:
    """
    Context manager for browser context (isolated session).

    Args:
        browser: Existing browser or None to create new one.
        **kwargs: Additional context options (viewport, locale, etc.).

    Yields:
        BrowserContext instance.
    """
    own_browser = browser is None
    ctx_opts = {
        "viewport": {"width": 1920, "height": 1080},
        **kwargs,
    }
    if own_browser:
        with get_browser() as b:
            context = b.new_context(**ctx_opts)
            context.set_default_timeout(settings.browser_timeout_ms)
            try:
                yield context
            finally:
                context.close()
    else:
        context = browser.new_context(**ctx_opts)
        context.set_default_timeout(settings.browser_timeout_ms)
        try:
            yield context
        finally:
            context.close()


def navigate_and_wait(page: Page, url: str, wait_until: str = "domcontentloaded") -> bool:
    """
    Navigate to URL and wait for page load.

    Args:
        page: Playwright Page instance.
        url: URL to navigate to.
        wait_until: Wait strategy (load, domcontentloaded, networkidle).

    Returns:
        True if navigation succeeded, False otherwise.
    """
    try:
        page.goto(url, wait_until=wait_until, timeout=settings.browser_timeout_ms)
        return True
    except Exception as e:
        logger.exception("Navigation to %s failed: %s", url, e)
        return False


def fill_form_field(page: Page, selector: str, value: str) -> bool:
    """
    Safely fill a form field by selector.

    Args:
        page: Playwright Page instance.
        selector: CSS selector for the input element.
        value: Value to fill.

    Returns:
        True if successful.
    """
    try:
        page.fill(selector, value, timeout=5000)
        return True
    except Exception as e:
        logger.warning("Failed to fill %s: %s", selector, e)
        return False


def click_element(page: Page, selector: str) -> bool:
    """
    Safely click an element by selector.

    Args:
        page: Playwright Page instance.
        selector: CSS selector for the element.

    Returns:
        True if successful.
    """
    try:
        page.click(selector, timeout=5000)
        return True
    except Exception as e:
        logger.warning("Failed to click %s: %s", selector, e)
        return False


def upload_file(page: Page, selector: str, file_path: str) -> bool:
    """
    Upload a file to an input[type="file"] element.

    Args:
        page: Playwright Page instance.
        selector: CSS selector for the file input.
        file_path: Absolute path to the file.

    Returns:
        True if successful.
    """
    try:
        page.set_input_files(selector, file_path, timeout=5000)
        return True
    except Exception as e:
        logger.warning("Failed to upload file to %s: %s", selector, e)
        return False


def extract_text(page: Page, selector: str) -> Optional[str]:
    """
    Extract text content from an element.

    Args:
        page: Playwright Page instance.
        selector: CSS selector for the element.

    Returns:
        Text content or None if not found.
    """
    try:
        element = page.query_selector(selector)
        return element.text_content() if element else None
    except Exception as e:
        logger.warning("Failed to extract text from %s: %s", selector, e)
        return None
