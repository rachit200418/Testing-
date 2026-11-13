"""Playwright UI Tests - Happy Flow and Basic Interactions."""

import pytest
from playwright.async_api import Page, expect
from tests.ui.pages.chat_page import ChatPage


class TestHappyFlow:
    """Happy path tests for the voice assistant UI."""

    @pytest.mark.asyncio
    async def test_page_loads(self, chat_page: ChatPage):
        """Test that the page loads correctly with all elements."""
        assert await chat_page.is_loaded()
        
        # Check key elements visible
        await chat_page.wait_for_element("record-button")
        await chat_page.wait_for_element("chat-history")
        await chat_page.wait_for_element("welcome-message")
        await chat_page.wait_for_element("status-bar")
        
        # Check welcome message
        welcome_text = await chat_page.get_text("welcome-text")
        assert "assistant" in welcome_text.lower()
        assert "appointment" in welcome_text.lower()

    @pytest.mark.asyncio
    async def test_record_button_enabled_initially(self, chat_page: ChatPage):
        """Test record button is enabled on load."""
        await chat_page.expect_enabled("record-button")
        await chat_page.expect_disabled("stop-button")

    @pytest.mark.asyncio
    async def test_status_shows_ready(self, chat_page: ChatPage):
        """Test status shows ready initially."""
        status = await chat_page.get_status_text()
        assert "ready" in status.lower()

    @pytest.mark.asyncio
    async def test_no_error_banner_initially(self, chat_page: ChatPage):
        """Test no error banner on load."""
        error = await chat_page.get_error_message()
        assert error is None


class TestRecordingFlow:
    """Tests for the recording interaction flow."""

    @pytest.mark.asyncio
    async def test_start_recording_changes_ui(self, chat_page: ChatPage):
        """Test UI changes when recording starts."""
        await chat_page.start_recording()
        
        # Record button should be hidden/disabled
        await chat_page.expect_disabled("record-button")
        
        # Stop button should be visible/enabled
        await chat_page.expect_enabled("stop-button")
        
        # Status should show recording
        status = await chat_page.get_status_text()
        assert "recording" in status.lower()
        
        status_state = await chat_page.get_status_state()
        assert status_state == "recording"

    @pytest.mark.asyncio
    async def test_stop_recording_shows_processing(self, chat_page: ChatPage):
        """Test UI shows processing after stop."""
        await chat_page.start_recording()
        await chat_page.stop_recording()
        
        # Should show processing briefly
        status = await chat_page.get_status_text()
        assert "processing" in status.lower() or "ready" in status.lower()

    @pytest.mark.asyncio
    async def test_full_recording_cycle(self, chat_page: ChatPage):
        """Test complete recording cycle with mock audio."""
        # This test uses the fake media stream from the browser launch args
        # The audio file is played as the microphone input
        
        await chat_page.start_recording()
        await chat_page.stop_recording()
        
        # Wait for response
        await chat_page.wait_for_bot_reply()
        
        # Check transcript appeared
        transcript = await chat_page.get_transcript()
        assert transcript, "Transcript should not be empty"
        
        # Check bot replied
        bot_reply = await chat_page.get_last_bot_message()
        assert bot_reply, "Bot should have replied"
        
        # Check user message in history
        user_msg = await chat_page.get_last_user_message()
        assert user_msg == transcript, "User message should match transcript"
        
        # Check status back to ready
        await chat_page._wait_for_status("ready")
        
        # Record button should be enabled again
        await chat_page.expect_enabled("record-button")


class TestChatHistory:
    """Tests for chat history display."""

    @pytest.mark.asyncio
    async def test_messages_appear_in_history(self, chat_page: ChatPage):
        """Test user and bot messages appear in chat history."""
        initial_messages = await chat_page.get_messages()
        initial_count = len(initial_messages)
        
        await chat_page.start_recording()
        await chat_page.stop_recording()
        await chat_page.wait_for_bot_reply()
        
        messages = await chat_page.get_messages()
        assert len(messages) > initial_count, "New messages should appear"
        
        # Should have both user and bot messages
        senders = [m["sender"] for m in messages]
        assert "You" in senders, "Should have user message"
        assert "Assistant" in senders, "Should have bot message"

    @pytest.mark.asyncio
    async def test_message_structure(self, chat_page: ChatPage):
        """Test message structure has sender and text."""
        await chat_page.start_recording()
        await chat_page.stop_recording()
        await chat_page.wait_for_bot_reply()
        
        messages = await chat_page.get_messages()
        for msg in messages:
            assert "sender" in msg
            assert "text" in msg
            assert msg["sender"] in ["You", "Assistant"]
            assert len(msg["text"]) > 0

    @pytest.mark.asyncio
    async def test_audio_player_present(self, chat_page: ChatPage):
        """Test audio player appears for bot replies."""
        await chat_page.start_recording()
        await chat_page.stop_recording()
        await chat_page.wait_for_bot_reply()
        
        audio_src = await chat_page.get_bot_audio_src()
        assert audio_src, "Bot reply should have audio player"
        assert "/audio/replies/" in audio_src, "Audio URL should point to replies"


class TestAccessibility:
    """Basic accessibility tests."""

    @pytest.mark.asyncio
    async def test_aria_attributes(self, chat_page: ChatPage):
        """Test key ARIA attributes present."""
        await chat_page.check_accessibility()

    @pytest.mark.asyncio
    async def test_keyboard_navigation(self, chat_page: ChatPage):
        """Test keyboard navigation works."""
        # Tab to record button
        await chat_page.page.keyboard.press("Tab")
        await chat_page.page.keyboard.press("Tab")
        
        # Enter should start recording
        await chat_page.page.keyboard.press("Enter")
        
        await chat_page.expect_disabled("record-button")
        await chat_page.expect_enabled("stop-button")
        
        # Stop recording
        await chat_page.page.keyboard.press("Enter")
        await chat_page._wait_for_status("ready")


class TestVisualRegression:
    """Visual regression tests (screenshot comparison)."""

    @pytest.mark.asyncio
    async def test_chat_ui_screenshot(self, chat_page: ChatPage):
        """Take baseline screenshot of chat UI."""
        await chat_page.screenshot_chat("tests/ui/screenshots/chat_ui_baseline.png")
        
        # After recording
        await chat_page.start_recording()
        await chat_page.screenshot_chat("tests/ui/screenshots/chat_ui_recording.png")
        
        await chat_page.stop_recording()
        await chat_page.wait_for_bot_reply()
        await chat_page.screenshot_chat("tests/ui/screenshots/chat_ui_with_reply.png")


class TestErrorHandling:
    """Error handling tests."""

    @pytest.mark.asyncio
    async def test_network_error_handling(self, chat_page: ChatPage, page: Page):
        """Test UI handles network errors gracefully."""
        # Block API requests
        await page.route("**/audio/chat", lambda route: route.abort("failed"))
        
        await chat_page.start_recording()
        await chat_page.stop_recording()
        
        # Should show error
        await chat_page.wait_for_error()
        error_msg = await chat_page.get_error_message()
        assert error_msg, "Error message should appear"
        assert "network" in error_msg.lower() or "error" in error_msg.lower()
        
        # Clean up route
        await page.unroute("**/audio/chat")


class TestMultiTurn:
    """Multi-turn conversation tests."""

    @pytest.mark.asyncio
    async def test_follow_up_question(self, chat_page: ChatPage):
        """Test follow-up question in conversation."""
        # First interaction
        await chat_page.start_recording()
        await chat_page.stop_recording()
        await chat_page.wait_for_bot_reply()
        
        first_bot = await chat_page.get_last_bot_message()
        assert first_bot
        
        # Second interaction
        await chat_page.start_recording()
        await chat_page.stop_recording()
        await chat_page.wait_for_bot_reply()
        
        second_bot = await chat_page.get_last_bot_message()
        assert second_bot
        
        # History should have both turns
        messages = await chat_page.get_messages()
        user_messages = [m for m in messages if m["sender"] == "You"]
        assert len(user_messages) >= 2, "Should have at least 2 user messages"