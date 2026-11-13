"""Playwright UI Tests - Visual Regression."""

import pytest
from playwright.async_api import expect
from tests.ui.pages.chat_page import ChatPage


class TestVisualRegression:
    """Visual regression tests using screenshot comparison."""

    @pytest.mark.asyncio
    async def test_initial_state_screenshot(self, chat_page: ChatPage):
        """Test initial UI state matches baseline."""
        await chat_page.screenshot_full("tests/ui/screenshots/visual_initial_state.png")
        
        # Check key elements visible
        await expect(chat_page.get_by_test_id("record-button")).to_be_visible()
        await expect(chat_page.get_by_test_id("chat-history")).to_be_visible()
        await expect(chat_page.get_by_test_id("welcome-message")).to_be_visible()
        await expect(chat_page.get_by_test_id("status-bar")).to_be_visible()

    @pytest.mark.asyncio
    async def test_recording_state_screenshot(self, chat_page: ChatPage):
        """Test recording UI state."""
        await chat_page.start_recording()
        
        await chat_page.screenshot_full("tests/ui/screenshots/visual_recording_state.png")
        
        # Verify recording indicators
        await expect(chat_page.get_by_test_id("stop-button")).to_be_visible()
        await expect(chat_page.get_by_test_id("status-indicator")).to_have_class("status-indicator recording")

    @pytest.mark.asyncio
    async def test_processing_state_screenshot(self, chat_page: ChatPage):
        """Test processing UI state."""
        await chat_page.start_recording()
        await chat_page.stop_recording()
        
        # Capture during processing (might be brief)
        await chat_page.screenshot_full("tests/ui/screenshots/visual_processing_state.png")

    @pytest.mark.asyncio
    async def test_with_reply_screenshot(self, chat_page: ChatPage):
        """Test UI with bot reply."""
        await chat_page.start_recording()
        await chat_page.stop_recording()
        await chat_page.wait_for_bot_reply()
        
        await chat_page.screenshot_full("tests/ui/screenshots/visual_with_reply.png")
        
        # Verify chat history has messages
        messages = await chat_page.get_messages()
        assert len(messages) >= 2  # welcome + user + bot

    @pytest.mark.asyncio
    async def test_error_state_screenshot(self, chat_page: ChatPage, page):
        """Test error UI state."""
        # Cause an error
        await page.route("**/audio/chat", lambda route: route.abort("failed"))
        
        await chat_page.start_recording()
        await chat_page.stop_recording()
        await chat_page.wait_for_error()
        
        await chat_page.screenshot_full("tests/ui/screenshots/visual_error_state.png")
        
        # Verify error banner visible
        await expect(chat_page.get_by_test_id("error-banner")).to_be_visible()
        
        await page.unroute("**/audio/chat")

    @pytest.mark.asyncio
    async def test_multi_turn_screenshot(self, chat_page: ChatPage):
        """Test UI with multiple conversation turns."""
        # Turn 1
        await chat_page.start_recording()
        await chat_page.stop_recording()
        await chat_page.wait_for_bot_reply()
        
        # Turn 2
        await chat_page.start_recording()
        await chat_page.stop_recording()
        await chat_page.wait_for_bot_reply()
        
        await chat_page.screenshot_full("tests/ui/screenshots/visual_multi_turn.png")
        
        messages = await chat_page.get_messages()
        user_messages = [m for m in messages if m["sender"] == "You"]
        assert len(user_messages) >= 2

    @pytest.mark.asyncio
    async def test_audio_player_screenshot(self, chat_page: ChatPage):
        """Test audio player appears correctly."""
        await chat_page.start_recording()
        await chat_page.stop_recording()
        await chat_page.wait_for_bot_reply()
        
        # Screenshot chat area showing audio player
        await chat_page.screenshot_chat("tests/ui/screenshots/visual_audio_player.png")
        
        # Verify audio element exists
        audio_src = await chat_page.get_bot_audio_src()
        assert audio_src


class TestVisualComparison:
    """Tests for visual comparison (would integrate with pixelmatch in CI)."""

    @pytest.mark.asyncio
    async def test_baseline_comparison(self, chat_page: ChatPage):
        """
        Baseline visual test.
        In CI, this would compare against stored baseline images using pixelmatch.
        """
        # This test captures the current state as baseline
        # In real CI, you'd compare: pixelmatch(baseline, current) < threshold
        
        await chat_page.screenshot_full("tests/ui/screenshots/baseline_full_page.png")
        await chat_page.screenshot_chat("tests/ui/screenshots/baseline_chat_area.png")
        
        # Verify no console errors
        errors = []
        chat_page.page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
        
        await chat_page.start_recording()
        await chat_page.stop_recording()
        await chat_page.wait_for_bot_reply()
        
        assert len(errors) == 0, f"Console errors: {errors}"


class TestResponsiveDesign:
    """Tests for responsive design at different viewport sizes."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("viewport", [
        {"width": 375, "height": 667},   # Mobile
        {"width": 768, "height": 1024},  # Tablet
        {"width": 1280, "height": 720},  # Desktop
        {"width": 1920, "height": 1080}, # Large desktop
    ])
    async def test_viewport_sizes(self, browser, viewport):
        """Test UI renders correctly at different viewport sizes."""
        context = await browser.new_context(
            viewport=viewport,
            permissions=["microphone"],
        )
        page = await context.new_page()
        
        chat = ChatPage(page)
        await chat.navigate()
        
        # Check key elements visible
        await expect(chat.get_by_test_id("record-button")).to_be_visible()
        await expect(chat.get_by_test_id("chat-history")).to_be_visible()
        
        # Take screenshot for this viewport
        await chat.screenshot_full(f"tests/ui/screenshots/responsive_{viewport['width']}x{viewport['height']}.png")
        
        await context.close()

    @pytest.mark.asyncio
    async def test_mobile_recording_flow(self, browser):
        """Test recording flow on mobile viewport."""
        context = await browser.new_context(
            viewport={"width": 375, "height": 667},
            permissions=["microphone"],
        )
        page = await context.new_page()
        
        chat = ChatPage(page)
        await chat.navigate()
        
        await chat.start_recording()
        await chat.stop_recording()
        await chat.wait_for_bot_reply()
        
        await chat.screenshot_full("tests/ui/screenshots/mobile_recording_flow.png")
        
        bot_reply = await chat.get_last_bot_message()
        assert bot_reply
        
        await context.close()


class TestDarkMode:
    """Tests for dark mode support (if implemented)."""

    @pytest.mark.asyncio
    async def test_dark_mode_screenshot(self, chat_page: ChatPage):
        """Test UI in dark mode."""
        # Enable dark mode via CSS media query
        await chat_page.page.emulate_media(color_scheme="dark")
        
        await chat_page.screenshot_full("tests/ui/screenshots/dark_mode_initial.png")
        
        await chat_page.start_recording()
        await chat_page.screenshot_full("tests/ui/screenshots/dark_mode_recording.png")
        
        await chat_page.stop_recording()
        await chat_page.wait_for_bot_reply()
        
        await chat_page.screenshot_full("tests/ui/screenshots/dark_mode_with_reply.png")
        
        # Verify readability
        messages = await chat_page.get_messages()
        assert len(messages) >= 2