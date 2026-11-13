"""Playwright Page Object Model - Chat Page."""

from playwright.async_api import Page, Locator, expect
from typing import List, Optional
from tests.ui.pages.base_page import BasePage


class ChatPage(BasePage):
    """Page object for the voice assistant chat UI."""

    # Selectors using data-testid
    RECORD_BUTTON = "record-button"
    STOP_BUTTON = "stop-button"
    RECORD_BUTTON_TEXT = "record-btn-text"
    STOP_BUTTON_TEXT = "stop-btn-text"
    TRANSCRIPT_BOX = "transcript-box"
    TRANSCRIPT_TEXT = "transcript-text"
    CHAT_HISTORY = "chat-history"
    STATUS_INDICATOR = "status-indicator"
    STATUS_TEXT = "status-text"
    ERROR_BANNER = "error-banner"
    WELCOME_MESSAGE = "welcome-message"
    WELCOME_TEXT = "welcome-text"
    AUDIO_VISUALIZER = "audio-visualizer"

    def __init__(self, page: Page):
        super().__init__(page)
        self._message_count = 0

    async def navigate(self, base_url: str = "http://localhost:8000"):
        """Navigate to the chat page."""
        await self.goto(f"{base_url}/web")

    async def is_loaded(self) -> bool:
        """Check if page is fully loaded."""
        try:
            await self.wait_for_element(self.RECORD_BUTTON)
            await self.wait_for_element(self.CHAT_HISTORY)
            await self.wait_for_element(self.WELCOME_MESSAGE)
            return True
        except Exception:
            return False

    # Recording controls

    async def start_recording(self):
        """Click the record button."""
        await self.click(self.RECORD_BUTTON)
        # Wait for recording state
        await self.expect_disabled(self.RECORD_BUTTON)
        await self.expect_enabled(self.STOP_BUTTON)
        await self._wait_for_status("recording")

    async def stop_recording(self):
        """Click the stop button."""
        await self.click(self.STOP_BUTTON)
        # Wait for processing state
        await self._wait_for_status("processing")
        # Wait for response
        await self._wait_for_status("ready", timeout=15000)

    async def _wait_for_status(self, expected_status: str, timeout: int = 5000):
        """Wait for status indicator to show expected state."""
        await expect(self.get_by_test_id(self.STATUS_TEXT)).to_contain_text(
            {"recording": "Recording", "processing": "Processing", "ready": "Ready"}[expected_status],
            timeout=timeout
        )
        # Also check indicator class
        indicator = self.get_by_test_id(self.STATUS_INDICATOR)
        await expect(indicator).to_have_class(f"status-indicator {expected_status}", timeout=timeout)

    def is_recording(self) -> bool:
        """Check if currently recording."""
        return self.get_by_test_id(self.RECORD_BUTTON).is_disabled()

    # Transcript

    async def get_transcript(self) -> str:
        """Get current transcript text."""
        return await self.get_attribute(self.TRANSCRIPT_TEXT, "value") or ""

    async def wait_for_transcript(self, expected_text: str = None, timeout: int = 10000):
        """Wait for transcript to appear."""
        if expected_text:
            await expect(self.get_by_test_id(self.TRANSCRIPT_TEXT)).to_have_value(expected_text, timeout=timeout)
        else:
            # Wait for any non-empty transcript
            await self.page.wait_for_function(
                f"document.querySelector('[data-testid=\"{self.TRANSCRIPT_TEXT}\"]').value.length > 0",
                timeout=timeout
            )

    # Chat history

    async def get_messages(self) -> List[dict]:
        """Get all messages in chat history."""
        messages = []
        message_elements = self.get_by_test_id_all("user-message") + self.get_by_test_id_all("bot-message")
        
        for elem in message_elements:
            try:
                sender = await elem.locator("[data-testid='user-sender'], [data-testid='bot-sender']").inner_text()
                text = await elem.locator("[data-testid='user-text'], [data-testid='bot-text']").inner_text()
                messages.append({"sender": sender.strip(), "text": text.strip()})
            except Exception:
                continue
        return messages

    async def get_last_bot_message(self) -> Optional[str]:
        """Get the last bot message text."""
        messages = await self.get_messages()
        for msg in reversed(messages):
            if msg["sender"] == "Assistant":
                return msg["text"]
        return None

    async def get_last_user_message(self) -> Optional[str]:
        """Get the last user message text."""
        messages = await self.get_messages()
        for msg in reversed(messages):
            if msg["sender"] == "You":
                return msg["text"]
        return None

    async def wait_for_bot_reply(self, timeout: int = 15000):
        """Wait for a new bot message to appear."""
        initial_count = len(await self.get_messages())
        await self.page.wait_for_function(
            f"() => document.querySelectorAll('[data-testid=\"user-message\"], [data-testid=\"bot-message\"]').length > {initial_count}",
            timeout=timeout
        )

    # Audio playback

    async def get_bot_audio_src(self) -> Optional[str]:
        """Get the audio source URL of the last bot message."""
        try:
            audio = self.page.locator("[data-testid='bot-audio']").last
            return await audio.get_attribute("src")
        except Exception:
            return None

    async def play_bot_audio(self):
        """Play the last bot audio message."""
        audio = self.page.locator("[data-testid='bot-audio']").last
        await audio.evaluate("el => el.play()")

    # Error handling

    async def get_error_message(self) -> Optional[str]:
        """Get error banner message if visible."""
        if await self.is_visible(self.ERROR_BANNER):
            return await self.get_text(self.ERROR_BANNER)
        return None

    async def wait_for_error(self, timeout: int = 5000):
        """Wait for error banner to appear."""
        await expect(self.get_by_test_id(self.ERROR_BANNER)).to_be_visible(timeout=timeout)

    # Status

    async def get_status_text(self) -> str:
        """Get current status text."""
        return await self.get_text(self.STATUS_TEXT)

    async def get_status_state(self) -> str:
        """Get current status indicator state."""
        indicator = self.get_by_test_id(self.STATUS_INDICATOR)
        classes = await indicator.get_attribute("class") or ""
        for state in ["recording", "processing", "ready", "error"]:
            if state in classes:
                return state
        return "unknown"

    # Visual regression

    async def screenshot_chat(self, path: str):
        """Screenshot the chat history area."""
        chat_history = self.get_by_test_id(self.CHAT_HISTORY)
        await chat_history.screenshot(path=path)

    async def screenshot_full(self, path: str):
        """Screenshot full page."""
        await self.screenshot(path, full_page=True)

    # Interactions for edge cases

    async def double_click_record(self):
        """Double-click record button (test idempotency)."""
        await self.get_by_test_id(self.RECORD_BUTTON).dblclick()

    async def click_record_while_recording(self):
        """Click record button while already recording."""
        await self.click(self.RECORD_BUTTON)

    # Accessibility checks

    async def check_accessibility(self):
        """Basic accessibility checks."""
        # Check record button has aria-label
        record_btn = self.get_by_test_id(self.RECORD_BUTTON)
        aria_label = await record_btn.get_attribute("aria-label")
        assert aria_label, "Record button missing aria-label"

        # Check status has aria-live
        status_bar = self.page.locator("[data-testid='status-bar']")
        aria_live = await status_bar.get_attribute("aria-live")
        assert aria_live == "polite", "Status bar missing aria-live"

        # Check error banner has role=alert
        error_banner = self.get_by_test_id(self.ERROR_BANNER)
        role = await error_banner.get_attribute("role")
        assert role == "alert", "Error banner missing role=alert"

        # Check chat history has role=log
        chat_history = self.get_by_test_id(self.CHAT_HISTORY)
        role = await chat_history.get_attribute("role")
        assert role == "log", "Chat history missing role=log"