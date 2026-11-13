"""Playwright UI Tests - Edge Cases and Error Scenarios."""

import pytest
from playwright.async_api import Page, expect
from tests.ui.pages.chat_page import ChatPage


class TestMicPermission:
    """Tests for microphone permission handling."""

    @pytest.mark.asyncio
    async def test_mic_permission_denied(self, browser, chat_page_factory):
        """Test UI handles microphone permission denied."""
        # Create context without microphone permission
        context = await browser.new_context(
            viewport={"width": 1280, "height": 720},
            permissions=[],  # No permissions granted
        )
        
        page = await context.new_page()
        chat = ChatPage(page)
        await chat.navigate()
        
        # Try to start recording
        await chat.click("record-button")
        
        # Should show error
        await chat.wait_for_error()
        error = await chat.get_error_message()
        assert error
        assert "microphone" in error.lower() or "permission" in error.lower()
        
        await context.close()

    @pytest.mark.asyncio
    async def test_mic_permission_granted_after_denied(self, browser):
        """Test recovery after granting permission."""
        context = await browser.new_context(
            viewport={"width": 1280, "height": 720},
            permissions=[],
        )
        
        page = await context.new_page()
        chat = ChatPage(page)
        await chat.navigate()
        
        # First attempt - denied
        await chat.click("record-button")
        await chat.wait_for_error()
        
        # Grant permission
        await context.grant_permissions(["microphone"])
        
        # Retry - should work now
        await chat.click("record-button")
        await chat.expect_disabled("record-button")
        await chat.expect_enabled("stop-button")
        
        await context.close()


class TestSilenceHandling:
    """Tests for silence/empty audio handling."""

    @pytest.mark.asyncio
    async def test_silence_clip(self, chat_page: ChatPage, clip_file: str):
        """Test handling of silence audio clip."""
        if "silence" not in clip_file:
            pytest.skip("Not a silence clip")
        
        await chat_page.start_recording()
        await chat_page.stop_recording()
        await chat_page.wait_for_bot_reply()
        
        # Should handle gracefully - either no transcript or error handled
        transcript = await chat_page.get_transcript()
        # Silence might result in empty transcript or "could not understand"
        # Bot should still respond
        bot_reply = await chat_page.get_last_bot_message()
        assert bot_reply, "Bot should reply even to silence"


class TestLongAudio:
    """Tests for long audio handling."""

    @pytest.mark.asyncio
    async def test_long_speech_clip(self, chat_page: ChatPage, clip_file: str, clip_data: dict):
        """Test handling of long speech clip."""
        if "long" not in clip_file and clip_data.get("tags", "").find("long") == -1:
            pytest.skip("Not a long speech clip")
        
        await chat_page.start_recording()
        await chat_page.stop_recording()
        
        # Long audio might take longer to process
        await chat_page.wait_for_bot_reply(timeout=30000)
        
        transcript = await chat_page.get_transcript()
        assert len(transcript) > 50, "Long speech should produce substantial transcript"
        
        bot_reply = await chat_page.get_last_bot_message()
        assert bot_reply


class TestDoubleClickAndReRecord:
    """Tests for double-click and mid-recording interactions."""

    @pytest.mark.asyncio
    async def test_double_click_record(self, chat_page: ChatPage):
        """Test double-clicking record button doesn't break."""
        await chat_page.double_click_record()
        
        # Should still be in recording state
        await chat_page.expect_disabled("record-button")
        await chat_page.expect_enabled("stop-button")
        
        await chat_page.stop_recording()
        await chat_page.wait_for_bot_reply()

    @pytest.mark.asyncio
    async def test_click_record_while_recording(self, chat_page: ChatPage):
        """Test clicking record button while already recording."""
        await chat_page.start_recording()
        
        # Click record again (should be ignored or handled)
        await chat_page.click_record_while_recording()
        
        # Should still be recording
        await chat_page.expect_disabled("record-button")
        await chat_page.expect_enabled("stop-button")
        
        await chat_page.stop_recording()
        await chat_page.wait_for_bot_reply()

    @pytest.mark.asyncio
    async def test_rapid_start_stop(self, chat_page: ChatPage):
        """Test rapid start/stop cycles."""
        for _ in range(3):
            await chat_page.start_recording()
            await chat_page.stop_recording()
            await chat_page.wait_for_bot_reply(timeout=10000)
            
            # Ready for next
            await chat_page.expect_enabled("record-button")


class TestOfflineMode:
    """Tests for offline/network failure scenarios."""

    @pytest.mark.asyncio
    async def test_offline_mode(self, chat_page: ChatPage, page: Page):
        """Test UI handles offline mode."""
        # Go offline
        await page.context.set_offline(True)
        
        await chat_page.start_recording()
        await chat_page.stop_recording()
        
        # Should show error
        await chat_page.wait_for_error(timeout=10000)
        error = await chat_page.get_error_message()
        assert error
        assert "network" in error.lower() or "offline" in error.lower() or "failed" in error.lower()
        
        # Go back online
        await page.context.set_offline(False)
        
        # Should be able to record again
        await chat_page.start_recording()
        await chat_page.stop_recording()
        await chat_page.wait_for_bot_reply()


class TestSlowAndFailedAPI:
    """Tests for slow or failing API responses."""

    @pytest.mark.asyncio
    async def test_slow_api_response(self, chat_page: ChatPage, page: Page):
        """Test UI handles slow API responses."""
        # Delay API responses
        async def delay_route(route):
            await page.wait_for_timeout(5000)  # 5 second delay
            await route.continue_()
        
        await page.route("**/audio/chat", delay_route)
        
        await chat_page.start_recording()
        await chat_page.stop_recording()
        
        # Should show processing for longer
        status = await chat_page.get_status_text()
        assert "processing" in status.lower() or "recording" in status.lower()
        
        # Eventually should complete or timeout
        try:
            await chat_page.wait_for_bot_reply(timeout=15000)
        except Exception:
            # Timeout is acceptable for this test
            pass
        
        await page.unroute("**/audio/chat")

    @pytest.mark.asyncio
    async def test_api_error_500(self, chat_page: ChatPage, page: Page):
        """Test UI handles 500 errors."""
        async def error_route(route):
            await route.fulfill(status=500, body="Internal Server Error")
        
        await page.route("**/audio/chat", error_route)
        
        await chat_page.start_recording()
        await chat_page.stop_recording()
        
        await chat_page.wait_for_error()
        error = await chat_page.get_error_message()
        assert error
        
        await page.unroute("**/audio/chat")

    @pytest.mark.asyncio
    async def test_api_timeout(self, chat_page: ChatPage, page: Page):
        """Test UI handles request timeout."""
        async def timeout_route(route):
            # Never respond - simulates timeout
            await page.wait_for_timeout(60000)
        
        await page.route("**/audio/chat", timeout_route)
        
        await chat_page.start_recording()
        await chat_page.stop_recording()
        
        # Should eventually show error
        await chat_page.wait_for_error(timeout=15000)
        error = await chat_page.get_error_message()
        assert error
        
        await page.unroute("**/audio/chat")


class TestParametrizedClips:
    """Tests running with parametrized audio clips from manifest."""

    @pytest.mark.asyncio
    async def test_clip_transcript_matches_manifest(
        self, 
        chat_page: ChatPage, 
        clip_file: str, 
        clip_data: dict
    ):
        """Test that transcript matches manifest for each clip."""
        if not clip_data:
            pytest.skip(f"No manifest data for {clip_file}")
        
        expected_transcript = clip_data.get("transcript", "")
        expected_intent = clip_data.get("intent", "")
        
        if not expected_transcript.strip():
            pytest.skip(f"Empty transcript for {clip_file}")
        
        await chat_page.start_recording()
        await chat_page.stop_recording()
        await chat_page.wait_for_bot_reply()
        
        transcript = await chat_page.get_transcript()
        
        # Transcript should be similar to expected (mock STT returns exact)
        assert transcript == expected_transcript or expected_transcript in transcript, \
            f"Transcript mismatch for {clip_file}: got '{transcript}', expected '{expected_transcript}'"
        
        # Check bot replied appropriately
        bot_reply = await chat_page.get_last_bot_message()
        assert bot_reply


class TestConcurrency:
    """Tests for concurrent interactions."""

    @pytest.mark.asyncio
    async def test_multiple_tabs(self, browser):
        """Test multiple tabs with voice assistant."""
        contexts = []
        pages = []
        chats = []
        
        try:
            for i in range(3):
                context = await browser.new_context(
                    viewport={"width": 1280, "height": 720},
                    permissions=["microphone"],
                )
                contexts.append(context)
                page = await context.new_page()
                pages.append(page)
                
                chat = ChatPage(page)
                await chat.navigate()
                chats.append(chat)
            
            # Start recording on all
            for chat in chats:
                await chat.start_recording()
            
            # Stop all
            for chat in chats:
                await chat.stop_recording()
            
            # All should get replies
            for chat in chats:
                await chat.wait_for_bot_reply()
                bot_reply = await chat.get_last_bot_message()
                assert bot_reply
                
        finally:
            for context in contexts:
                await context.close()


class TestBrowserCompatibility:
    """Cross-browser smoke tests (Firefox, WebKit)."""

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Run manually for cross-browser verification")
    async def test_firefox_smoke(self, playwright):
        """Smoke test on Firefox."""
        browser = await playwright.firefox.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 720},
            permissions=["microphone"],
        )
        page = await context.new_page()
        
        chat = ChatPage(page)
        await chat.navigate()
        await chat.start_recording()
        await chat.stop_recording()
        await chat.wait_for_bot_reply()
        
        bot_reply = await chat.get_last_bot_message()
        assert bot_reply
        
        await browser.close()

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Run manually for cross-browser verification")
    async def test_webkit_smoke(self, playwright):
        """Smoke test on WebKit."""
        browser = await playwright.webkit.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 720},
            permissions=["microphone"],
        )
        page = await context.new_page()
        
        chat = ChatPage(page)
        await chat.navigate()
        await chat.start_recording()
        await chat.stop_recording()
        await chat.wait_for_bot_reply()
        
        bot_reply = await chat.get_last_bot_message()
        assert bot_reply
        
        await browser.close()