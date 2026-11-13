"""Playwright fixtures and configuration for UI tests."""

import csv
import os
import pytest
import pytest_asyncio
from pathlib import Path
from typing import AsyncGenerator, List, Dict

from playwright.async_api import Browser, BrowserContext, Page, Playwright
from tests.ui.pages.chat_page import ChatPage


# Test configuration
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
HEADLESS = os.getenv("HEADLESS", "true").lower() == "true"
SLOW_MO = int(os.getenv("SLOW_MO", "0"))


def load_manifest(manifest_path: Path) -> List[Dict]:
    """Load manifest CSV for parametrization."""
    rows = []
    if manifest_path.exists():
        with open(manifest_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)
    return rows


# Select representative clips for UI testing (20-30 clips)
UI_TEST_CLIPS = [
    "book_appointment_clean.wav",
    "book_appointment_noisy.wav",
    "cancel_booking.wav",
    "check_availability.wav",
    "reschedule.wav",
    "faq_timings.wav",
    "faq_fees.wav",
    "out_of_scope_medical.wav",
    "prompt_injection.wav",
    "pii_phone.wav",
    "hinglish.wav",
    "long_speech.wav",
    "silence.wav",
    "numbers_dates.wav",
    "background_tv.wav",
    "accent_us.wav",
    "booking_with_name.wav",
    "faq_payment.wav",
    "injection_roleplay.wav",
    "pii_aadhaar.wav",
]


@pytest.fixture(scope="session")
def manifest_rows() -> List[Dict]:
    """Load manifest rows for test parametrization."""
    manifest_path = Path("data/manifest.csv")
    return load_manifest(manifest_path)


@pytest.fixture(scope="session")
def ui_test_clips() -> List[str]:
    """Get list of clips for UI testing."""
    return UI_TEST_CLIPS


@pytest.fixture(scope="session")
def clip_manifest_data(manifest_rows: List[Dict], ui_test_clips: List[str]) -> List[Dict]:
    """Get manifest data for UI test clips only."""
    clip_map = {row["file"]: row for row in manifest_rows}
    return [clip_map[clip] for clip in ui_test_clips if clip in clip_map]


# Browser fixtures

@pytest_asyncio.fixture(scope="session")
async def browser(playwright: Playwright) -> AsyncGenerator[Browser, None]:
    """Launch browser with fake media stream support."""
    browser = await playwright.chromium.launch(
        headless=HEADLESS,
        slow_mo=SLOW_MO,
        args=[
            "--use-fake-ui-for-media-stream",
            "--use-fake-device-for-media-stream",
            "--disable-web-security",
            "--disable-features=IsolateOrigins,site-per-process",
        ],
    )
    yield browser
    await browser.close()


@pytest_asyncio.fixture(scope="function")
async def context(browser: Browser, request) -> AsyncGenerator[BrowserContext, None]:
    """Create browser context with fake audio capture."""
    # Get clip for this test (if parametrized)
    clip_file = getattr(request, "param", None)
    
    context_args = {
        "viewport": {"width": 1280, "height": 720},
        "record_video_dir": "tests/ui/videos/",
        "record_video_size": {"width": 1280, "height": 720},
    }
    
    # Add fake audio capture if clip specified
    if clip_file:
        audio_path = Path("data/audio") / clip_file
        if audio_path.exists():
            context_args["permissions"] = ["microphone"]
            # Note: use-file-for-fake-audio-capture is a launch arg, not context
            # We'll handle it in the page fixture
    
    context = await browser.new_context(**context_args)
    
    # Enable tracing
    await context.tracing.start(
        screenshots=True,
        snapshots=True,
        sources=True,
    )
    
    yield context
    
    # Save trace on failure
    test_name = request.node.name.replace("/", "_").replace(" ", "_")
    trace_path = f"tests/ui/traces/{test_name}.zip"
    await context.tracing.stop(path=trace_path)
    
    await context.close()


@pytest_asyncio.fixture(scope="function")
async def page(context: BrowserContext, request) -> AsyncGenerator[Page, None]:
    """Create page with fake audio capture for the test clip."""
    clip_file = getattr(request, "param", None)
    
    page = await context.new_page()
    
    # Set up fake audio capture if clip specified
    if clip_file:
        audio_path = Path("data/audio") / clip_file
        if audio_path.exists():
            # Grant microphone permission
            await context.grant_permissions(["microphone"])
            
            # Set up file for fake audio capture
            # This is done via CDP
            await page.evaluate("""() => {
                navigator.mediaDevices.getUserMedia = async () => {
                    // This will be overridden by the fake device
                    return new MediaStream();
                };
            }""")
    
    # Set default timeout
    page.set_default_timeout(15000)
    
    yield page
    
    await page.close()


@pytest_asyncio.fixture(scope="function")
async def chat_page(page: Page) -> ChatPage:
    """Create ChatPage object and navigate to it."""
    chat = ChatPage(page)
    await chat.navigate(BASE_URL)
    await chat.wait_for_element("record-button")
    return chat


@pytest.fixture
def chat_page_factory(browser, base_url=BASE_URL):
    """Factory to create ChatPage instances with custom context."""
    async def _create(permissions=None, clip_file=None):
        context_args = {
            "viewport": {"width": 1280, "height": 720},
        }
        if permissions:
            context_args["permissions"] = permissions
        
        context = await browser.new_context(**context_args)
        
        if clip_file:
            await context.grant_permissions(["microphone"])
        
        page = await context.new_page()
        chat = ChatPage(page)
        await chat.navigate(base_url)
        await chat.wait_for_element("record-button")
        return chat, context, page
    
    return _create


# Parametrized fixtures for clip-based tests

@pytest.fixture(scope="function", params=UI_TEST_CLIPS)
def clip_file(request) -> str:
    """Parametrized fixture for test clips."""
    return request.param


@pytest.fixture(scope="function")
def clip_data(clip_file: str, manifest_rows: List[Dict]) -> Dict:
    """Get manifest data for current clip."""
    clip_map = {row["file"]: row for row in manifest_rows}
    return clip_map.get(clip_file, {})


# Helper fixtures

@pytest.fixture
def api_key() -> str:
    """API key for testing."""
    return "test-api-key"


# Cleanup fixtures

@pytest.fixture(autouse=True)
async def cleanup_downloads(page: Page):
    """Clean up downloads after each test."""
    yield
    # Playwright handles download cleanup automatically


# Screenshot on failure

@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Capture screenshot on test failure."""
    outcome = yield
    rep = outcome.get_result()
    
    if rep.when == "call" and rep.failed:
        # Get page from fixture
        page = item.funcargs.get("page")
        if page:
            import asyncio
            try:
                screenshot_path = f"tests/ui/screenshots/{item.name}_failure.png"
                asyncio.get_event_loop().run_until_complete(
                    page.screenshot(path=screenshot_path, full_page=True)
                )
            except Exception:
                pass


# Configure asyncio
pytest_asyncio.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    import asyncio
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()