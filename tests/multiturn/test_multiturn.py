"""Multi-turn Conversation and Tool Tests."""

import pytest
from app.adapters.factory import create_llm_adapter
from app.tools.database import (
    check_availability,
    book_slot,
    cancel_booking,
    get_booking,
    create_session,
    update_session,
    get_session,
    delete_session,
)
from app.guardrails.guardrails import check_confirmation_required, validate_tool_call


class TestMultiTurnConversations:
    """Test multi-turn conversation context retention."""

    @pytest.fixture(scope="class")
    def llm_adapter(self):
        return create_llm_adapter()

    @pytest.fixture
    def session_id(self):
        import uuid
        return f"test_multi_{uuid.uuid4().hex[:8]}"

    def _chat(self, llm_adapter, messages):
        import asyncio
        return asyncio.run(llm_adapter.chat(messages))

    def test_context_retention_name(self, llm_adapter, session_id):
        """Test that name provided in turn 1 is remembered in turn 2."""
        # Turn 1: Request booking
        result1 = self._chat(llm_adapter, [{"role": "user", "content": "I want to book an appointment"}])
        assert result1.intent == "book_appointment"

        # Turn 2: Provide name
        messages = [
            {"role": "user", "content": "I want to book an appointment"},
            {"role": "assistant", "content": result1.reply},
            {"role": "user", "content": "My name is Alice Smith"},
        ]
        result2 = self._chat(llm_adapter, messages)
        assert result2.slots.get("patient_name") == "Alice Smith"

    def test_context_retention_date_time(self, llm_adapter, session_id):
        """Test date/time provided across turns."""
        messages = [
            {"role": "user", "content": "Book appointment for Bob"},
            {"role": "assistant", "content": "What date and time?"},
            {"role": "user", "content": "Next Friday at 2 PM"},
        ]
        result = self._chat(llm_adapter, messages)
        assert result.slots.get("date") == "Next Friday"
        assert "2 PM" in result.slots.get("time", "") or "14:00" in result.slots.get("time", "")

    def test_multi_turn_booking_flow(self, llm_adapter, session_id):
        """Complete booking flow across multiple turns."""
        messages = [
            {"role": "user", "content": "I want to book an appointment"},
        ]
        result = self._chat(llm_adapter, messages)
        assert "name" in result.reply.lower()

        messages.append({"role": "assistant", "content": result.reply})
        messages.append({"role": "user", "content": "Jane Doe"})
        result = self._chat(llm_adapter, messages)
        assert result.slots.get("patient_name") == "Jane Doe"

        messages.append({"role": "assistant", "content": result.reply})
        messages.append({"role": "user", "content": "Tomorrow at 4 PM"})
        result = self._chat(llm_adapter, messages)
        assert "confirm" in result.reply.lower()

        messages.append({"role": "assistant", "content": result.reply})
        messages.append({"role": "user", "content": "Yes, confirm"})
        result = self._chat(llm_adapter, messages)
        assert "booked" in result.reply.lower() or "booking id" in result.reply.lower()
        assert len(result.tool_calls) > 0

    def test_multi_turn_cancel_flow(self, llm_adapter, session_id):
        """Complete cancellation flow."""
        messages = [
            {"role": "user", "content": "Cancel my appointment"},
        ]
        result = self._chat(llm_adapter, messages)
        assert "booking id" in result.reply.lower()

        messages.append({"role": "assistant", "content": result.reply})
        messages.append({"role": "user", "content": "BK1234567890"})
        result = self._chat(llm_adapter, messages)
        assert "confirm" in result.reply.lower()

        messages.append({"role": "assistant", "content": result.reply})
        messages.append({"role": "user", "content": "Yes"})
        result = self._chat(llm_adapter, messages)
        assert "cancelled" in result.reply.lower()

    def test_context_switch_topic(self, llm_adapter, session_id):
        """Test switching from booking to FAQ mid-conversation."""
        messages = [
            {"role": "user", "content": "I want to book an appointment"},
        ]
        result = self._chat(llm_adapter, messages)

        messages.append({"role": "assistant", "content": result.reply})
        messages.append({"role": "user", "content": "Actually, what are your hours?"})
        result = self._chat(llm_adapter, messages)
        assert result.intent == "faq"
        assert "9:00" in result.reply or "Monday" in result.reply

    def test_follow_up_question(self, llm_adapter, session_id):
        """Test follow-up question after FAQ answer."""
        messages = [
            {"role": "user", "content": "What are your hours?"},
        ]
        result = self._chat(llm_adapter, messages)
        assert result.intent == "faq"

        messages.append({"role": "assistant", "content": result.reply})
        messages.append({"role": "user", "content": "Are you open on Sundays?"})
        result = self._chat(llm_adapter, messages)
        assert result.intent == "faq"
        assert "closed" in result.reply.lower() or "sunday" in result.reply.lower()


class TestToolExecution:
    """Test tool calling: correct tool, correct args, error handling."""

    @pytest.fixture(scope="class")
    def llm_adapter(self):
        return create_llm_adapter()

    def _chat(self, llm_adapter, messages):
        import asyncio
        return asyncio.run(llm_adapter.chat(messages))

    def test_tool_check_availability(self, llm_adapter):
        """Test check_availability tool called with correct args."""
        messages = [{"role": "user", "content": "What slots are available on Monday?"}]
        result = self._chat(llm_adapter, messages)

        assert result.intent == "check_availability"
        assert len(result.tool_calls) > 0
        tool = result.tool_calls[0]
        assert tool["name"] == "check_availability"
        assert "date" in tool["arguments"]
        assert tool["arguments"]["date"] == "Monday"

    def test_tool_book_slot_args(self, llm_adapter):
        """Test book_slot called with correct arguments after confirmation."""
        messages = [
            {"role": "user", "content": "Book appointment for Carol on Tuesday at 10 AM"},
            {"role": "assistant", "content": "Please confirm: Book appointment for Carol on Tuesday at 10 AM?"},
            {"role": "user", "content": "Yes"},
        ]
        result = self._chat(llm_adapter, messages)

        # Should have executed book_slot
        book_tools = [t for t in result.tool_calls if t["name"] == "book_slot"]
        assert len(book_tools) > 0
        tool = book_tools[0]
        assert tool["arguments"]["name"] == "Carol"
        assert "Tuesday" in tool["arguments"]["date"]
        assert "10" in tool["arguments"]["time"] or "10:00" in tool["arguments"]["time"]

    def test_tool_cancel_booking_args(self, llm_adapter):
        """Test cancel_booking called with correct booking_id."""
        messages = [
            {"role": "user", "content": "Cancel booking BK1234567890"},
            {"role": "assistant", "content": "Please confirm: Cancel booking BK1234567890?"},
            {"role": "user", "content": "Yes"},
        ]
        result = self._chat(llm_adapter, messages)

        cancel_tools = [t for t in result.tool_calls if t["name"] == "cancel_booking"]
        assert len(cancel_tools) > 0
        tool = cancel_tools[0]
        assert tool["arguments"]["booking_id"] == "BK1234567890"

    def test_no_tool_when_not_needed(self, llm_adapter):
        """Test no tool called for simple FAQ."""
        messages = [{"role": "user", "content": "What are your hours?"}]
        result = self._chat(llm_adapter, messages)

        # Should use answer_faq tool or just respond
        if result.tool_calls:
            # If tool used, should be answer_faq
            for tool in result.tool_calls:
                assert tool["name"] in ["answer_faq", "check_availability"]

    def test_wrong_tool_not_called(self, llm_adapter):
        """Test that wrong tool is not called (e.g., book_slot for FAQ)."""
        messages = [{"role": "user", "content": "What are your hours?"}]
        result = self._chat(llm_adapter, messages)

        book_tools = [t for t in result.tool_calls if t["name"] == "book_slot"]
        assert len(book_tools) == 0, "book_slot should not be called for FAQ"

    def test_tool_validation(self):
        """Test tool argument validation."""
        # Valid book_slot
        valid, err = validate_tool_call("book_slot", {"name": "John", "date": "2024-01-15", "time": "10:00"})
        assert valid is True
        assert err is None

        # Missing name
        valid, err = validate_tool_call("book_slot", {"date": "2024-01-15", "time": "10:00"})
        assert valid is False
        assert "name" in err

        # Invalid booking_id format
        valid, err = validate_tool_call("cancel_booking", {"booking_id": "invalid"})
        assert valid is False
        assert "format" in err

    def test_confirmation_required(self):
        """Test confirmation required detection."""
        assert check_confirmation_required("book_slot") is True
        assert check_confirmation_required("cancel_booking") is True
        assert check_confirmation_required("check_availability") is False
        assert check_confirmation_required("answer_faq") is False


class TestDatabaseTools:
    """Test database tool functions directly."""

    @pytest.mark.asyncio
    async def test_check_availability_returns_slots(self):
        slots = await check_availability("2024-01-15")
        assert len(slots) > 0
        for slot in slots:
            assert "date" in slot
            assert "time" in slot
            assert "doctor" in slot
            assert "specialty" in slot
            assert "available" in slot

    @pytest.mark.asyncio
    async def test_book_slot_creates_booking(self):
        result = await book_slot("Test Patient", "2024-01-15", "10:00")
        assert result["success"] is True
        assert "booking_id" in result
        assert result["patient_name"] == "Test Patient"
        assert result["date"] == "2024-01-15"
        assert result["time"] == "10:00"

        # Verify booking exists
        booking = await get_booking(result["booking_id"])
        assert booking is not None
        assert booking["patient_name"] == "Test Patient"

    @pytest.mark.asyncio
    async def test_cancel_booking(self):
        # First book
        result = await book_slot("Cancel Test", "2024-01-15", "11:00")
        booking_id = result["booking_id"]

        # Then cancel
        cancel_result = await cancel_booking(booking_id)
        assert cancel_result["success"] is True

        # Verify cancelled
        booking = await get_booking(booking_id)
        assert booking["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_double_booking_prevention(self):
        """Test that same slot can't be double booked."""
        # Book first
        result1 = await book_slot("Patient A", "2024-01-15", "10:00")
        assert result1["success"] is True

        # Try to book same slot - should fail or get different slot
        # Note: Current implementation picks first available, so this tests the logic
        slots = await check_availability("2024-01-15", "10:00")
        # The booked slot should not be available
        booked_slot = next((s for s in slots if s["time"] == "10:00" and s["doctor"] == result1["doctor"]), None)
        if booked_slot:
            assert booked_slot["available"] is False

    @pytest.mark.asyncio
    async def test_session_management(self):
        import uuid
        session_id = f"test_db_{uuid.uuid4().hex[:8]}"

        # Create session
        session = await create_session(session_id)
        assert session["session_id"] == session_id

        # Update session
        await update_session(
            session_id,
            "User message",
            "Assistant reply",
            "book_appointment",
            {"patient_name": "Test"},
            [{"name": "book_slot", "arguments": {}}],
            pending_confirmation={"tool": "book_slot", "arguments": {"name": "Test"}},
        )

        # Get session
        retrieved = await get_session(session_id)
        assert len(retrieved["history"]) == 1
        assert retrieved["pending_confirmation"] is not None

        # Clear confirmation
        await update_session(
            session_id,
            "Yes",
            "Booked!",
            "book_appointment",
            {},
            [],
            pending_confirmation=False,
        )
        retrieved = await get_session(session_id)
        assert retrieved["pending_confirmation"] is None

        # Delete session
        deleted = await delete_session(session_id)
        assert deleted is True
        retrieved = await get_session(session_id)
        assert retrieved is None


class TestToolErrorRecovery:
    """Test tool error handling and recovery."""

    @pytest.mark.asyncio
    async def test_book_slot_invalid_time(self):
        """Test booking with invalid time returns error."""
        # This would need a mock DB that returns no slots for that time
        # Current mock always returns some slots
        pass

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_booking(self):
        result = await cancel_booking("BK0000000000")
        assert result["success"] is False
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_cancel_already_cancelled(self):
        result = await book_slot("Test", "2024-01-15", "10:00")
        booking_id = result["booking_id"]
        await cancel_booking(booking_id)
        result2 = await cancel_booking(booking_id)
        assert result2["success"] is False
        assert "already cancelled" in result2["error"].lower()