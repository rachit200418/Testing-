"""Database models and operations for the clinic appointment system."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Column, DateTime, String, Text, create_engine, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings
from app.logging_utils import get_logger

logger = get_logger(__name__)
settings = get_settings()


class Base(DeclarativeBase):
    pass


class BookingDB(Base):
    __tablename__ = "bookings"

    booking_id = Column(String(20), primary_key=True)
    patient_name = Column(String(100), nullable=False)
    date = Column(String(20), nullable=False)  # YYYY-MM-DD
    time = Column(String(10), nullable=False)  # HH:MM
    doctor = Column(String(100), nullable=False)
    specialty = Column(String(50), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String(20), default="confirmed")  # confirmed, cancelled


class SessionDB(Base):
    __tablename__ = "sessions"

    session_id = Column(String(50), primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    history = Column(Text, default="[]")  # JSON array
    pending_confirmation = Column(Text, nullable=True)  # JSON object


# Async engine and session
engine = create_async_engine(settings.database_url, echo=settings.debug)
async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    """Initialize database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database initialized")


async def close_db():
    """Close database connections."""
    await engine.dispose()


# Booking operations


async def check_availability(date: str, time: str | None = None) -> list[dict[str, Any]]:
    """Check available slots for a given date."""
    # Mock availability - in real app, this would query doctor schedules
    # Return some default slots
    slots = [
        {"date": date, "time": "09:00", "doctor": "Dr. Priya Sharma", "specialty": "Pediatrics", "available": True},
        {"date": date, "time": "10:00", "doctor": "Dr. Priya Sharma", "specialty": "Pediatrics", "available": True},
        {"date": date, "time": "11:00", "doctor": "Dr. Anjali Mehta", "specialty": "Gynecology", "available": True},
        {"date": date, "time": "14:00", "doctor": "Dr. Rajesh Kumar", "specialty": "Cardiology", "available": True},
        {"date": date, "time": "15:00", "doctor": "Dr. Rajesh Kumar", "specialty": "Cardiology", "available": True},
        {"date": date, "time": "16:00", "doctor": "Dr. Rajesh Kumar", "specialty": "Cardiology", "available": True},
    ]

    # Filter out already booked slots
    async with async_session_maker() as session:
        result = await session.execute(
            select(BookingDB).where(BookingDB.date == date, BookingDB.status == "confirmed")
        )
        bookings = result.scalars().all()

        booked_slots = {(b.time, b.doctor) for b in bookings}
        for slot in slots:
            if (slot["time"], slot["doctor"]) in booked_slots:
                slot["available"] = False

    if time:
        slots = [s for s in slots if s["time"] == time]

    return [s for s in slots if s["available"]]


async def book_slot(name: str, date: str, time: str) -> dict[str, Any]:
    """Book an appointment slot."""
    # Find available doctor for the time
    slots = await check_availability(date, time)
    if not slots:
        return {"success": False, "error": "No available slots for that time"}

    slot = slots[0]
    booking_id = f"BK{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

    async with async_session_maker() as session:
        booking = BookingDB(
            booking_id=booking_id,
            patient_name=name,
            date=date,
            time=time,
            doctor=slot["doctor"],
            specialty=slot["specialty"],
            status="confirmed",
        )
        session.add(booking)
        await session.commit()

    logger.info(f"Booked appointment: {booking_id} for {name} on {date} at {time}")
    return {
        "success": True,
        "booking_id": booking_id,
        "patient_name": name,
        "date": date,
        "time": time,
        "doctor": slot["doctor"],
        "specialty": slot["specialty"],
    }


async def cancel_booking(booking_id: str) -> dict[str, Any]:
    """Cancel a booking."""
    async with async_session_maker() as session:
        result = await session.execute(select(BookingDB).where(BookingDB.booking_id == booking_id))
        booking = result.scalar_one_or_none()

        if not booking:
            return {"success": False, "error": "Booking not found"}

        if booking.status == "cancelled":
            return {"success": False, "error": "Booking already cancelled"}

        booking.status = "cancelled"
        await session.commit()

    logger.info(f"Cancelled booking: {booking_id}")
    return {"success": True, "booking_id": booking_id}


async def get_booking(booking_id: str) -> dict[str, Any] | None:
    """Get booking details."""
    async with async_session_maker() as session:
        result = await session.execute(select(BookingDB).where(BookingDB.booking_id == booking_id))
        booking = result.scalar_one_or_none()

        if not booking:
            return None

        return {
            "booking_id": booking.booking_id,
            "patient_name": booking.patient_name,
            "date": booking.date,
            "time": booking.time,
            "doctor": booking.doctor,
            "specialty": booking.specialty,
            "status": booking.status,
        }


# Session operations


async def get_session(session_id: str) -> dict[str, Any] | None:
    """Get session data."""
    async with async_session_maker() as session:
        result = await session.execute(select(SessionDB).where(SessionDB.session_id == session_id))
        session_db = result.scalar_one_or_none()

        if not session_db:
            return None

        return {
            "session_id": session_db.session_id,
            "created_at": session_db.created_at.isoformat(),
            "updated_at": session_db.updated_at.isoformat(),
            "history": json.loads(session_db.history),
            "pending_confirmation": json.loads(session_db.pending_confirmation) if session_db.pending_confirmation else None,
        }


async def create_session(session_id: str) -> dict[str, Any]:
    """Create a new session."""
    async with async_session_maker() as session:
        session_db = SessionDB(session_id=session_id, history=json.dumps([]))
        session.add(session_db)
        await session.commit()

    return {
        "session_id": session_id,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
        "history": [],
        "pending_confirmation": None,
    }


async def update_session(
    session_id: str,
    user_message: str,
    assistant_reply: str,
    intent: str,
    slots: dict[str, Any],
    tool_calls: list[dict[str, Any]],
    pending_confirmation: dict[str, Any] | None = None,
) -> None:
    """Update session with new conversation turn."""
    async with async_session_maker() as session:
        result = await session.execute(select(SessionDB).where(SessionDB.session_id == session_id))
        session_db = result.scalar_one_or_none()

        if not session_db:
            await create_session(session_id)
            result = await session.execute(select(SessionDB).where(SessionDB.session_id == session_id))
            session_db = result.scalar_one_or_none()

        history = json.loads(session_db.history)
        history.append(
            {
                "timestamp": datetime.utcnow().isoformat(),
                "user": user_message,
                "assistant": assistant_reply,
                "intent": intent,
                "slots": slots,
                "tool_calls": tool_calls,
            }
        )

        session_db.history = json.dumps(history)
        session_db.updated_at = datetime.utcnow()
        if pending_confirmation is not None:
            session_db.pending_confirmation = json.dumps(pending_confirmation)
        elif pending_confirmation is False:  # Explicit clear
            session_db.pending_confirmation = None

        await session.commit()


async def delete_session(session_id: str) -> bool:
    """Delete a session."""
    async with async_session_maker() as session:
        result = await session.execute(select(SessionDB).where(SessionDB.session_id == session_id))
        session_db = result.scalar_one_or_none()

        if not session_db:
            return False

        await session.delete(session_db)
        await session.commit()
        return True


# FAQ operations


def load_faq() -> list[dict[str, Any]]:
    """Load FAQ from JSON file."""
    faq_path = Path(settings.faq_path)
    if faq_path.exists():
        with open(faq_path) as f:
            return json.load(f)
    return []


async def answer_faq(question: str) -> dict[str, Any]:
    """Answer a question using FAQ data (simple keyword matching)."""
    faq_data = load_faq()
    question_lower = question.lower()

    best_match = None
    best_score = 0

    for entry in faq_data:
        entry_keywords = set(entry["question"].lower().split())
        question_keywords = set(question_lower.split())
        overlap = len(entry_keywords & question_keywords)
        if overlap > best_score:
            best_score = overlap
            best_match = entry

    if best_match and best_score >= 2:
        return {"found": True, "answer": best_match["answer"], "source_id": best_match["id"], "category": best_match["category"]}

    return {"found": False, "answer": "I don't have that information in my FAQ. Please ask about clinic timings, fees, doctors, location, or other services."}