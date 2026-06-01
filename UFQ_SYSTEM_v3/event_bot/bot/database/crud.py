import aiosqlite
from contextlib import asynccontextmanager
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy import desc
from datetime import datetime, timedelta
import logging

from bot.database.models import Event, Registration, Ticket, EventStatus, RegStatus
from bot.database.db import AsyncSessionLocal
from bot.utils.ticket_generator import generate_pin, generate_security_hash, generate_qr_data, generate_ticket_image
from bot.utils.status_manager import calculate_user_status
from bot.config import DB_PATH, SUPER_ADMIN_ID

logger = logging.getLogger(__name__)


@asynccontextmanager
async def get_db():
    db = await aiosqlite.connect(DB_PATH)
    try:
        await db.execute("PRAGMA busy_timeout=5000")
        await db.execute("PRAGMA foreign_keys=ON")
        db.row_factory = aiosqlite.Row
        yield db
    finally:
        await db.close()


def get_db_path():
    return DB_PATH


# --- USER FUNCTIONS (raw aiosqlite on shared table) ---

async def get_user_by_tg_id(telegram_id: int):
    """Get user from shared users table via raw aiosqlite. Returns dict or None."""
    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,))
        row = await cursor.fetchone()
        if row is None:
            return None
        return dict(row)


async def create_user(telegram_id: int, full_name: str, username: str = None, club_id: int = None):
    """Create or update user in shared users table via raw aiosqlite."""
    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,))
        existing = await cursor.fetchone()

        if existing:
            # User exists, just update username
            if username:
                await db.execute(
                    "UPDATE users SET username=? WHERE telegram_id=?",
                    (username, telegram_id)
                )
                await db.commit()
            cursor2 = await db.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,))
            row = await cursor2.fetchone()
            return dict(row)

        # Insert new user
        await db.execute(
            """INSERT INTO users (telegram_id, full_name, username, club_id, total_points, user_status, is_cp, is_bp, score)
               VALUES (?, ?, ?, ?, 0, 'BRONZE', 0, 0, 0)""",
            (telegram_id, full_name, username, club_id)
        )
        await db.commit()
        cursor3 = await db.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,))
        row = await cursor3.fetchone()
        return dict(row)


async def get_all_clubs():
    """Get all clubs from shared clubs table via raw aiosqlite. Returns list of dicts."""
    async with get_db() as db:
        cursor = await db.execute("SELECT id, name FROM clubs")
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def is_user_president(telegram_id: int) -> bool:
    """Check if user has is_cp=1 in shared users table."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT is_cp FROM users WHERE telegram_id=?", (telegram_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            return False
        return bool(row['is_cp'])


async def is_user_admin(telegram_id: int) -> bool:
    """Check if user is SUPER_ADMIN."""
    return telegram_id == SUPER_ADMIN_ID


# --- EVENT FUNCTIONS (SQLAlchemy) ---

async def get_active_events(limit: int = 50):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Event).where(Event.status == EventStatus.ACTIVE).order_by(Event.id.desc()).limit(limit)
        )
        return result.scalars().all()


async def get_event_by_id(event_id: int):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Event).where(Event.id == event_id))
        return result.scalars().first()


async def create_event(title: str, desc: str, link: str, reg_pts: int, att_pts: int, created_by_tg_id: int, event_date=None, location: str = None):
    """Create event. Gets user info from shared table via raw query."""
    # Get user from shared table
    user = await get_user_by_tg_id(created_by_tg_id)
    if not user:
        return False, "Foydalanuvchi topilmadi"

    async with AsyncSessionLocal() as session:
        new_event = Event(
            title=title,
            description=desc,
            post_link=link,
            club_id=user.get('club_id'),
            registration_points=reg_pts,
            attendance_points=att_pts,
            created_by=user['id'],
            event_date=event_date,
            location=location
        )
        session.add(new_event)
        await session.commit()
        return True, "Muvaffaqiyatli yaratildi"


# --- REGISTRATION & LEADERBOARD FUNCTIONS ---

async def register_user_for_event(user_tg_id: int, event_id: int):
    """Register user for event atomically using a single DB connection."""
    async with get_db() as db:
        # Get user
        cursor = await db.execute("SELECT * FROM users WHERE telegram_id=?", (user_tg_id,))
        user = await cursor.fetchone()
        if not user:
            return False, "Foydalanuvchi topilmadi"
        user = dict(user)

        # Get event
        cursor = await db.execute(
            "SELECT * FROM events WHERE id=? AND status='ACTIVE'",
            (event_id,)
        )
        event = await cursor.fetchone()
        if not event:
            return False, "Tadbir topilmadi yoki yopilgan."
        event = dict(event)

        # BUG FIX: O'z klubining tadbiriga ro'yxatdan o'tishni bloklash
        if user.get('club_id') and event.get('club_id') and user['club_id'] == event['club_id']:
            return False, "Siz o'z klubingiz tadbiriga ro'yxatdan o'ta olmaysiz!"

        # Check if already registered
        cursor = await db.execute(
            "SELECT id FROM registrations WHERE user_id=? AND event_id=?",
            (user['id'], event_id)
        )
        existing = await cursor.fetchone()
        if existing:
            return False, "Allaqachon ro'yxatdan o'tgansiz!"

        # Insert registration — try/except for race condition (bug #4)
        try:
            await db.execute(
                "INSERT INTO registrations (user_id, event_id, status, reg_date) VALUES (?, ?, 'REGISTERED', ?)",
                (user['id'], event_id, datetime.utcnow().isoformat())
            )
        except Exception as e:
            if "UNIQUE" in str(e).upper() or "unique" in str(e).lower():
                return False, "Allaqachon ro'yxatdan o'tgansiz!"
            raise

        # Update total_points
        new_points = user['total_points'] + event['registration_points']
        await db.execute(
            "UPDATE users SET total_points = ? WHERE telegram_id=?",
            (new_points, user_tg_id)
        )

        # Recalculate status
        new_status = calculate_user_status(new_points)
        if new_status != user['user_status']:
            await db.execute(
                "UPDATE users SET user_status=? WHERE telegram_id=?",
                (new_status, user_tg_id)
            )

        await db.commit()

    return True, f"Muvaffaqiyatli! Sizga {event['registration_points']} ball qo'shildi."


async def get_top_users(limit: int = 10):
    """Get top users from shared table via raw aiosqlite."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT telegram_id, full_name, total_points, user_status FROM users WHERE is_bp=0 ORDER BY total_points DESC LIMIT ?",
            (limit,)
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_user_results(telegram_id: int):
    """Get user points and attended events count."""
    # Get points from shared table
    user = await get_user_by_tg_id(telegram_id)
    if not user:
        return 0, 0

    points = user.get('total_points', 0)

    # Get attended events count via SQLAlchemy
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Registration).where(
                Registration.user_id == user['id'],
                Registration.status == RegStatus.ATTENDED
            )
        )
        attended_events = len(result.scalars().all())

    return points, attended_events


async def get_event_registrations(event_id: int):
    """Get registrations for an event. Returns list of (registration, user_dict) tuples."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Registration).where(Registration.event_id == event_id)
        )
        registrations = result.scalars().all()

    if not registrations:
        return []

    # Batch fetch all users in one query
    user_ids = [reg.user_id for reg in registrations]
    placeholders = ','.join(['?' for _ in user_ids])

    async with get_db() as db:
        cursor = await db.execute(
            f"SELECT * FROM users WHERE id IN ({placeholders})", tuple(user_ids)
        )
        user_rows = await cursor.fetchall()

    user_map = {row['id']: dict(row) for row in user_rows}

    results = []
    for reg in registrations:
        user_data = user_map.get(reg.user_id)
        if user_data:
            results.append((reg, user_data))

    return results


async def mark_attendance(reg_id: int, status: RegStatus):
    """Mark attendance atomically using a single DB connection (bug #5 fix)."""
    async with get_db() as db:
        # Fetch registration
        cursor = await db.execute(
            "SELECT r.*, e.attendance_points, e.club_id "
            "FROM registrations r JOIN events e ON r.event_id = e.id "
            "WHERE r.id = ?", (reg_id,)
        )
        reg_row = await cursor.fetchone()
        if not reg_row:
            return False

        reg = dict(reg_row)
        current_status = reg['status']
        if current_status == status.value:
            return False

        # Get user
        cursor = await db.execute("SELECT * FROM users WHERE id=?", (reg['user_id'],))
        user_row = await cursor.fetchone()
        if not user_row:
            return False
        user = dict(user_row)

        # Calculate point change
        point_change = 0
        if status == RegStatus.ATTENDED and current_status != RegStatus.ATTENDED.value:
            point_change = reg['attendance_points']
        elif status != RegStatus.ATTENDED and current_status == RegStatus.ATTENDED.value:
            point_change = -reg['attendance_points']

        # All changes in one transaction
        await db.execute("BEGIN IMMEDIATE")
        try:
            await db.execute(
                "UPDATE registrations SET status=? WHERE id=?",
                (status.value, reg_id)
            )
            if point_change != 0:
                await db.execute(
                    "UPDATE users SET total_points = MAX(0, total_points + ?) WHERE id=?",
                    (point_change, reg['user_id'])
                )
                # Recalculate status
                new_pts = max(0, user['total_points'] + point_change)
                new_status = calculate_user_status(new_pts)
                if new_status != user.get('user_status', 'BRONZE'):
                    await db.execute(
                        "UPDATE users SET user_status=? WHERE id=?",
                        (new_status, reg['user_id'])
                    )
            await db.commit()
        except Exception:
            await db.execute("ROLLBACK")
            raise

    return True


# --- TICKET FUNCTIONS ---

async def create_ticket(user_tg_id: int, event_id: int):
    """Create ticket for user. Mix of raw (user data) and SQLAlchemy (ticket creation).
    Retries up to 5 times on PIN collision."""
    user = await get_user_by_tg_id(user_tg_id)
    if not user:
        return None, "Foydalanuvchi topilmadi"

    max_retries = 5
    for attempt in range(max_retries):
        async with AsyncSessionLocal() as session:
            # Check event exists
            event = await session.get(Event, event_id)
            if not event:
                return None, "Tadbir topilmadi"

            # Check if ticket already exists
            existing = await session.execute(
                select(Ticket).where(Ticket.user_id == user['id'], Ticket.event_id == event_id)
            )
            if existing.scalars().first():
                return None, "Allaqachon chipta mavjud"

            # Generate PIN and security hash
            pin = generate_pin()
            timestamp = datetime.utcnow().isoformat()
            security_hash = generate_security_hash(user['id'], event_id, pin, timestamp)

            # Create ticket without qr_data initially (placeholder)
            ticket = Ticket(
                user_id=user['id'],
                event_id=event_id,
                ticket_pin=pin,
                security_hash=security_hash,
                qr_data="placeholder"
            )
            session.add(ticket)
            try:
                await session.commit()
                await session.refresh(ticket)
            except IntegrityError:
                await session.rollback()
                if attempt < max_retries - 1:
                    logger.warning(f"PIN collision on attempt {attempt + 1}, retrying...")
                    continue
                else:
                    logger.error("PIN collision: max retries exceeded")
                    return None, "Chipta yaratishda xatolik (PIN collision). Qayta urinib ko'ring."

            # Now ticket has an ID - generate QR data with new format
            qr_data = generate_qr_data(ticket.id, pin)
            ticket.qr_data = qr_data
            await session.commit()
            break

    # Get club name from shared table
    club_name = "UFQ Community"
    if user.get('club_id'):
        async with get_db() as db:
            cursor = await db.execute("SELECT name FROM clubs WHERE id=?", (user['club_id'],))
            club_row = await cursor.fetchone()
            if club_row:
                club_name = club_row['name']

    event_date = event.event_date.strftime("%d-%b, %H:%M") if event.event_date else "Tez orada"

    ticket_image = await generate_ticket_image(
        user_full_name=user['full_name'],
        user_points=user.get('total_points', 0),
        event_title=event.title,
        event_date=event_date,
        club_name=club_name,
        pin=pin,
        qr_data=qr_data
    )

    return ticket, ticket_image


async def verify_and_checkin(security_hash: str, event_id: int, scanner_tg_id: int, expected_user_tg_id: int = None):
    """QR code scan and check-in. Mix of raw queries and SQLAlchemy.
    Returns (success, scanner_msg, extra_data_dict_or_None).
    """
    # Check scanner permissions via raw query
    scanner = await get_user_by_tg_id(scanner_tg_id)
    if not scanner:
        return False, "Sizda skanerlash huquqi yo'q!", None

    # Scanner must be CP or SUPER_ADMIN
    is_admin = await is_user_admin(scanner_tg_id)
    is_president = await is_user_president(scanner_tg_id)
    if not is_admin and not is_president:
        return False, "Sizda skanerlash huquqi yo'q!", None

    async with AsyncSessionLocal() as session:
        # Find ticket
        ticket_result = await session.execute(
            select(Ticket).where(
                Ticket.security_hash == security_hash,
                Ticket.event_id == event_id
            )
        )
        ticket = ticket_result.scalars().first()

        if not ticket:
            logger.warning(
                f"QR SCAN FAILED: Ticket not found. security_hash='{security_hash}', event_id={event_id}"
            )
            return False, "Noto'g'ri yoki yaroqsiz chipta!", None

        # Already used?
        if ticket.is_used:
            logger.info(f"QR SCAN FAILED: Ticket already used. ticket_id={ticket.id}, used_at={ticket.used_at}")
            used_time = ticket.used_at.strftime("%H:%M") if ticket.used_at else "noma'lum vaqt"
            return False, f"Bu chipta allaqachon ishlatilgan!\nSkanerlangan vaqt: {used_time}", None

        # Get event
        event = await session.get(Event, event_id)
        if not event:
            return False, "Xatolik: Ma'lumot topilmadi", None

        # Time-based scan validation (bug #1: UTC vaqtida taqqoslaymiz)
        if event.event_date:
            try:
                if isinstance(event.event_date, str):
                    event_dt = datetime.fromisoformat(event.event_date)
                else:
                    event_dt = event.event_date

                scan_allowed_from = event_dt - timedelta(hours=2)
                now = datetime.utcnow()

                if now < scan_allowed_from:
                    # Display time in Tashkent (UTC+5) for the user
                    tashkent_dt = event_dt + timedelta(hours=5)
                    formatted_date = tashkent_dt.strftime("%d.%m.%Y %H:%M")
                    return False, f"Bu tadbir hali boshlanmagan!\nSkanerlash {formatted_date} dan 2 soat oldin boshlanadi (Toshkent vaqti).", None
            except (ValueError, TypeError) as e:
                logger.warning(f"Event date parsing error: {e}")

        # Get ticket owner from shared table
        async with get_db() as db:
            cursor = await db.execute("SELECT * FROM users WHERE id=?", (ticket.user_id,))
            user_row = await cursor.fetchone()
            if not user_row:
                return False, "Xatolik: Ma'lumot topilmadi", None
            user_data = dict(user_row)

        # BUG #2 FIX: Verify QR kod ichidagi user_tg_id chipta egasiga mos kelishini tekshirish
        if expected_user_tg_id is not None:
            if user_data['telegram_id'] != expected_user_tg_id:
                logger.warning(
                    f"user_tg_id mismatch: QR={expected_user_tg_id}, DB={user_data['telegram_id']}"
                )
                return False, "Noto'g'ri yoki yaroqsiz chipta!", None

        # Check scanner can manage this event (same club or SUPER_ADMIN)
        if not is_admin:
            if event.club_id and scanner.get('club_id') != event.club_id:
                logger.warning(
                    f"QR SCAN FAILED: Club mismatch. scanner_club={scanner.get('club_id')}, event_club={event.club_id}"
                )
                return False, "Siz bu tadbirni boshqara olmaysiz!", None

        # Find registration
        reg_result = await session.execute(
            select(Registration).where(
                Registration.user_id == ticket.user_id,
                Registration.event_id == event_id
            )
        )
        registration = reg_result.scalars().first()

        if not registration:
            logger.warning(
                f"QR SCAN FAILED: No registration. user_id={ticket.user_id}, event_id={event_id}"
            )
            return False, "Foydalanuvchi bu tadbirga ro'yxatdan o'tmagan!", None

        # Perform check-in
        ticket.is_used = True
        ticket.used_at = datetime.utcnow()
        registration.status = RegStatus.ATTENDED
        registration.check_in_time = datetime.utcnow()
        await session.commit()

    # Update points and status in shared table (single connection for atomicity)
    old_points = user_data.get('total_points', 0)
    new_points = old_points + event.attendance_points
    old_status = user_data.get('user_status', 'BRONZE')
    new_status = calculate_user_status(new_points)

    async with get_db() as db:
        await db.execute(
            "UPDATE users SET total_points = total_points + ? WHERE id=?",
            (event.attendance_points, ticket.user_id)
        )
        if old_status != new_status:
            await db.execute(
                "UPDATE users SET user_status=? WHERE id=?",
                (new_status, ticket.user_id)
            )
        await db.commit()

    # Status change message
    status_change_msg = ""
    if old_status != new_status:
        from bot.utils.status_manager import get_status_name_uz
        old_name = get_status_name_uz(old_status)
        new_name = get_status_name_uz(new_status)
        status_change_msg = f"\n🎉 Status o'zgardi: {old_name} → {new_name}"

    # BUG #8 FIX: Skaner uchun va foydalanuvchi uchun alohida xabarlar
    scanner_msg = (
        f"✅ Muvaffaqiyatli!\n\n"
        f"👤 {user_data['full_name']}\n"
        f"📅 {event.title}\n"
        f"+{event.attendance_points} ball (Jami: {new_points}){status_change_msg}"
    )

    user_notify_msg = (
        f"🎉 <b>Tabriklaymiz!</b>\n\n"
        f"Siz <b>{event.title}</b> tadbiriga muvaffaqiyatli qatnashdingiz!\n\n"
        f"<b>+{event.attendance_points} ball</b> qo'shildi\n"
        f"Jami ballingiz: <b>{new_points}</b>"
    )
    if status_change_msg:
        user_notify_msg += f"\n{status_change_msg}"

    extra = {
        'user_name': user_data['full_name'],
        'user_tg_id': user_data['telegram_id'],
        'att_pts': event.attendance_points,
        'new_points': new_points,
        'user_notify_msg': user_notify_msg,
    }

    logger.info(f"QR SCAN SUCCESS: ticket_id={ticket.id}, user={user_data['full_name']}, event={event.title}")

    return True, scanner_msg, extra


async def update_user_status_if_needed(telegram_id: int):
    """Update user_status in shared table based on total_points."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT total_points, user_status FROM users WHERE telegram_id=?", (telegram_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return

        new_status = calculate_user_status(row['total_points'])
        current_status = row['user_status']
        if current_status != new_status:
            await db.execute(
                "UPDATE users SET user_status=? WHERE telegram_id=?",
                (new_status, telegram_id)
            )
            await db.commit()


async def scan_checkin(ticket_id: int, pin: str, scanner_tg_id: int):
    """Simple QR scan check-in. Returns (success, message, extra_data)"""
    # 1. Check scanner permissions (must be SUPER_ADMIN_ID or is_cp=1)
    is_admin = await is_user_admin(scanner_tg_id)
    is_president = await is_user_president(scanner_tg_id)
    if not is_admin and not is_president:
        return False, "Sizda skanerlash huquqi yo'q!", None

    # 2. Find ticket by ID using SQLAlchemy
    async with AsyncSessionLocal() as session:
        ticket = await session.get(Ticket, ticket_id)
        if not ticket:
            return False, "Chipta topilmadi!", None

        # 3. Verify PIN matches ticket.ticket_pin
        if ticket.ticket_pin != pin:
            return False, "Noto'g'ri PIN kod!", None

        # 4. Check ticket not already used
        if ticket.is_used:
            used_time = ticket.used_at.strftime("%H:%M") if ticket.used_at else "noma'lum vaqt"
            return False, f"Bu chipta allaqachon ishlatilgan!\nSkanerlangan vaqt: {used_time}", None

        # 5. Get the event - check status is ACTIVE
        event = await session.get(Event, ticket.event_id)
        if not event:
            return False, "Tadbir topilmadi!", None
        if event.status != EventStatus.ACTIVE:
            return False, "Bu tadbir faol emas!", None

        # 6. Check time: if event.event_date is set, current time must be <= event_date + 1 hour
        now = datetime.utcnow()
        if event.event_date:
            try:
                if isinstance(event.event_date, str):
                    event_dt = datetime.fromisoformat(event.event_date)
                else:
                    event_dt = event.event_date
                deadline = event_dt + timedelta(hours=1)
                if now > deadline:
                    return False, "Check-in vaqti tugagan!", None
            except (ValueError, TypeError) as e:
                logger.warning(f"Event date parsing error: {e}")

        # 7. Find registration for this ticket's user_id and event_id
        reg_result = await session.execute(
            select(Registration).where(
                Registration.user_id == ticket.user_id,
                Registration.event_id == ticket.event_id
            )
        )
        registration = reg_result.scalars().first()
        if not registration:
            return False, "Foydalanuvchi bu tadbirga ro'yxatdan o'tmagan!", None

        # 8. Mark registration.status = ATTENDED, registration.check_in_time = now
        registration.status = RegStatus.ATTENDED
        registration.check_in_time = now

        # 9. Mark ticket.is_used = True, ticket.used_at = now
        ticket.is_used = True
        ticket.used_at = now

        # 10. Commit
        await session.commit()

    # 11. Get user info from shared table for response
    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM users WHERE id=?", (ticket.user_id,))
        user_row = await cursor.fetchone()
        if not user_row:
            return True, "Check-in muvaffaqiyatli!", None
        user = dict(user_row)

    # 12. Return (True, scanner_message, extra_data_dict)
    check_in_time = now.strftime("%H:%M")
    scanner_message = (
        f"Ishtirokchi: {user['full_name']}\n"
        f"Tadbir: {event.title}\n"
        f"Check-in vaqti: {check_in_time}"
    )
    extra_data = {
        'user_tg_id': user['telegram_id'],
        'user_name': user['full_name'],
        'event_title': event.title
    }

    return True, scanner_message, extra_data


async def auto_close_events():
    """Close expired events and distribute points. Returns list of report dicts."""
    reports = []
    now = datetime.utcnow()

    # 1. Find ACTIVE events where event_date IS NOT NULL AND event_date + 1 hour < now
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Event).where(
                Event.status == EventStatus.ACTIVE,
                Event.event_date.isnot(None)
            )
        )
        active_events = result.scalars().all()

    expired_events = []
    for event in active_events:
        try:
            if isinstance(event.event_date, str):
                event_dt = datetime.fromisoformat(event.event_date)
            else:
                event_dt = event.event_date
            if event_dt + timedelta(hours=1) < now:
                expired_events.append(event)
        except (ValueError, TypeError) as e:
            logger.warning(f"Event date parsing error for event {event.id}: {e}")

    # 2. For each expired event:
    for event in expired_events:
        try:
            attendees_info = []

            # a. Find all registrations with status ATTENDED
            async with AsyncSessionLocal() as session:
                reg_result = await session.execute(
                    select(Registration).where(
                        Registration.event_id == event.id,
                        Registration.status == RegStatus.ATTENDED
                    )
                )
                attended_regs = reg_result.scalars().all()

                # Get total registered count
                all_reg_result = await session.execute(
                    select(Registration).where(Registration.event_id == event.id)
                )
                all_regs = all_reg_result.scalars().all()
                total_registered = len(all_regs)
                total_attended = len(attended_regs)

            # b. For each attended registration: add points
            for reg in attended_regs:
                async with get_db() as db:
                    cursor = await db.execute("SELECT * FROM users WHERE id=?", (reg.user_id,))
                    user_row = await cursor.fetchone()
                    if not user_row:
                        continue
                    user = dict(user_row)

                    # Add attendance_points to user's total_points
                    new_points = user['total_points'] + event.attendance_points
                    await db.execute(
                        "UPDATE users SET total_points=? WHERE id=?",
                        (new_points, reg.user_id)
                    )

                    # Recalculate and update user_status
                    new_status = calculate_user_status(new_points)
                    if new_status != user.get('user_status', 'BRONZE'):
                        await db.execute(
                            "UPDATE users SET user_status=? WHERE id=?",
                            (new_status, reg.user_id)
                        )
                    await db.commit()

                    attendees_info.append({
                        'name': user['full_name'],
                        'points_given': event.attendance_points
                    })

            # c. Mark event.status = EventStatus.COMPLETED
            async with AsyncSessionLocal() as session:
                ev = await session.get(Event, event.id)
                if ev:
                    ev.status = EventStatus.COMPLETED
                    await session.commit()

            # e. Get event creator's telegram_id from shared users table
            creator_tg_id = None
            async with get_db() as db:
                cursor = await db.execute(
                    "SELECT telegram_id FROM users WHERE id=?", (event.created_by,)
                )
                creator_row = await cursor.fetchone()
                if creator_row:
                    creator_tg_id = creator_row['telegram_id']

            # f. Build report dict
            report = {
                'event_title': event.title,
                'event_id': event.id,
                'creator_tg_id': creator_tg_id,
                'total_registered': total_registered,
                'total_attended': total_attended,
                'attendees': attendees_info
            }
            reports.append(report)

        except Exception as e:
            logger.error(f"Auto-close error for event {event.id}: {e}")

    return reports
