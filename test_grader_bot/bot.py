"""
Main Telegram bot for test grading using OMR (V3).
Features: roster auto-naming, /edit command, document support,
uncertain answer handling, multi-admin support.
"""

import json
import logging
import os
import re
import tempfile
from pathlib import Path

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

from config import BOT_TOKEN, ADMIN_IDS, DATA_DIR, MAX_STUDENTS
from sheet_generator import generate_answer_sheet
from omr_scanner import scan_answer_sheet
from excel_export import generate_results_excel

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Conversation states
(
    AWAITING_NUM_QUESTIONS,
    AWAITING_NUM_OPTIONS,
    AWAITING_ANSWERS,
    AWAITING_SCAN_PHOTO,
    AWAITING_STUDENT_NAME,
    BATCH_SCANNING,
    BATCH_NAMING,
    AWAITING_ROSTER,
    AWAITING_UNCERTAIN_ANSWERS,
) = range(9)


# ============================================================
# Session storage helpers
# ============================================================


def _get_session_path(user_id: int) -> Path:
    """Get path to session JSON file for a user."""
    return DATA_DIR / f"session_{user_id}.json"


def _load_session(user_id: int) -> dict:
    """Load session data from JSON file. Returns empty dict if corrupted."""
    path = _get_session_path(user_id)
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return {}
            return data
        except (json.JSONDecodeError, ValueError, OSError):
            logger.warning("Session file corrupted for user %s, resetting.", user_id)
            return {}
    return {}


def _save_session(user_id: int, data: dict) -> None:
    """Save session data to JSON file atomically (temp file + os.replace)."""
    path = _get_session_path(user_id)
    tmp_path = path.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


# ============================================================
# Access control
# ============================================================


async def _check_admin(update: Update) -> bool:
    """Check if the user is in the admin list. If not, send rejection."""
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("Sizda ruxsat yo'q.")
        return False
    return True


# ============================================================
# Roster helpers
# ============================================================


def _parse_roster_text(text: str) -> dict:
    """Parse roster text into {number: name} dict.
    Supports both numbered (1. Ali Valiyev) and unnumbered (one name per line).
    """
    raw_lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if not raw_lines:
        return {}

    roster = {}
    numbered_pattern = re.compile(r"^(\d+)[.)\-\s]+(.+)$")

    first_match = numbered_pattern.match(raw_lines[0])
    if first_match:
        # Numbered list
        for line in raw_lines:
            m = numbered_pattern.match(line)
            if m:
                num = int(m.group(1))
                name = m.group(2).strip()
                if name:
                    roster[num] = name
    else:
        # Unnumbered list - auto-assign numbers 1, 2, 3...
        for i, line in enumerate(raw_lines, start=1):
            if line:
                roster[i] = line

    return roster


# ============================================================
# Command handlers
# ============================================================


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle /start command."""
    await update.message.reply_text(
        "Assalomu alaykum! Men test tekshiruvchi botman.\n\n"
        "Buyruqlar:\n"
        "/new_test - Yangi test yaratish\n"
        "/roster - O'quvchilar ro'yxatini kiritish (auto-naming)\n"
        "/scan - Javob varaqalarini skanerlash\n"
        "/edit - To'g'ri javobni o'zgartirish (masalan: /edit 5 B)\n"
        "/results - Natijalarni Excel fayl sifatida olish\n"
        "/stats - Statistika ko'rish\n"
        "/cancel - Bekor qilish\n\n"
        "Boshlash uchun /new_test buyrug'ini yuboring.\n"
        "Ro'yxat kiritilsa, skanerlashda ismlar avtomatik aniqlanadi."
    )
    return ConversationHandler.END


async def new_test_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle /new_test - start creating a new test."""
    if not await _check_admin(update):
        return ConversationHandler.END

    await update.message.reply_text(
        "Yangi test yaratamiz.\n\n"
        "Savollar sonini kiriting (1 dan 74 gacha):"
    )
    return AWAITING_NUM_QUESTIONS


async def receive_num_questions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive number of questions."""
    text = update.message.text.strip()
    try:
        num = int(text)
        if num < 1 or num > 74:
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            "Iltimos, 1 dan 74 gacha son kiriting:"
        )
        return AWAITING_NUM_QUESTIONS

    context.user_data["num_questions"] = num
    await update.message.reply_text(
        f"Savollar soni: {num}\n\n"
        "Har bir savol uchun variantlar sonini kiriting (2, 3, 4 yoki 5):"
    )
    return AWAITING_NUM_OPTIONS


async def receive_num_options(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive number of options per question."""
    text = update.message.text.strip()
    try:
        num = int(text)
        if num < 2 or num > 5:
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            "Iltimos, 2 dan 5 gacha son kiriting:"
        )
        return AWAITING_NUM_OPTIONS

    context.user_data["num_options"] = num
    option_letters = "ABCDE"[:num]
    num_q = context.user_data["num_questions"]
    await update.message.reply_text(
        f"Variantlar soni: {num} ({option_letters})\n\n"
        f"Endi to'g'ri javoblarni ketma-ket yozing ({num_q} ta harf).\n"
        f"Masalan: {''.join(option_letters[i % num] for i in range(min(num_q, 5)))}...\n\n"
        f"Yoki vergul bilan: A,B,C,D,A,B..."
    )
    return AWAITING_ANSWERS


async def receive_answers(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive correct answers string."""
    text = update.message.text.strip().upper()
    num_q = context.user_data["num_questions"]
    num_opt = context.user_data["num_options"]
    option_letters = "ABCDE"[:num_opt]

    # Parse answers - support both "ABCD" and "A,B,C,D" formats
    if "," in text:
        answers_str = [a.strip() for a in text.split(",")]
    else:
        answers_str = list(text)

    # Validate
    if len(answers_str) != num_q:
        await update.message.reply_text(
            f"Xatolik: {len(answers_str)} ta javob kiritildi, "
            f"lekin {num_q} ta kerak.\n\n"
            f"Qaytadan kiriting:"
        )
        return AWAITING_ANSWERS

    # Convert to indices
    correct_indices = []
    for i, ans in enumerate(answers_str):
        if ans not in option_letters:
            await update.message.reply_text(
                f"Xatolik: {i+1}-savol javobida '{ans}' noto'g'ri. "
                f"Faqat {option_letters} harflaridan foydalaning.\n\n"
                f"Qaytadan kiriting:"
            )
            return AWAITING_ANSWERS
        correct_indices.append(option_letters.index(ans))

    # Save session
    user_id = update.effective_user.id
    session = _load_session(user_id)
    session["num_questions"] = num_q
    session["num_options"] = num_opt
    session["correct_answers"] = correct_indices
    session["correct_letters"] = answers_str
    session["students"] = []
    # Preserve roster if exists
    if "roster" not in session:
        session["roster"] = {}
    _save_session(user_id, session)

    # Generate answer sheet
    await update.message.reply_text("Javob varaqasi tayyorlanmoqda...")
    img = generate_answer_sheet(num_q, num_opt)

    # Save to temp file and send
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        img.save(tmp.name, "PNG")
        tmp_path = tmp.name

    try:
        with open(tmp_path, "rb") as f:
            await update.message.reply_document(
                document=f,
                filename=f"javob_varaqasi_{num_q}_savol.png",
                caption=(
                    f"Javob varaqasi tayyor!\n"
                    f"Savollar: {num_q}, Variantlar: {option_letters}\n\n"
                    f"Bu varaqani chop eting va o'quvchilarga tarqating.\n"
                    f"Tekshirish uchun /scan buyrug'ini yuboring."
                ),
            )
    finally:
        os.unlink(tmp_path)

    return ConversationHandler.END


# ============================================================
# Roster command
# ============================================================


async def roster_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle /roster - start entering student roster."""
    if not await _check_admin(update):
        return ConversationHandler.END

    await update.message.reply_text(
        "O'quvchilar ro'yxatini kiriting.\n\n"
        "Raqamlangan ro'yxat:\n"
        "1. Ali Valiyev\n"
        "2. Bobur Karimov\n\n"
        "Yoki raqamsiz (har qator = 1 ism):\n"
        "Ali Valiyev\n"
        "Bobur Karimov\n\n"
        "Yoki .txt fayl yuboring.\n"
        "Bekor qilish: /cancel"
    )
    return AWAITING_ROSTER


async def receive_roster_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive roster as text message."""
    text = update.message.text.strip()
    roster = _parse_roster_text(text)

    if not roster:
        await update.message.reply_text(
            "Ro'yxat bo'sh. Qaytadan yuboring yoki /cancel."
        )
        return AWAITING_ROSTER

    user_id = update.effective_user.id
    session = _load_session(user_id)
    # Roster keys are stored as strings for JSON compatibility; lookups use str(student_number)
    session["roster"] = {str(k): v for k, v in roster.items()}
    _save_session(user_id, session)

    await update.message.reply_text(
        f"Ro'yxat saqlandi! {len(roster)} ta o'quvchi."
    )
    return ConversationHandler.END


async def receive_roster_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive roster as .txt document."""
    document = update.message.document
    if not document:
        await update.message.reply_text(
            "Iltimos, .txt fayl yoki matn yuboring."
        )
        return AWAITING_ROSTER

    # Check if it is a text file
    file_name = document.file_name or ""
    if not file_name.lower().endswith(".txt"):
        await update.message.reply_text(
            "Faqat .txt fayl qabul qilinadi. Qaytadan yuboring."
        )
        return AWAITING_ROSTER

    file = await document.get_file()
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="wb") as tmp:
        await file.download_to_drive(tmp.name)
        tmp_path = tmp.name

    try:
        with open(tmp_path, "r", encoding="utf-8") as f:
            text = f.read()
    finally:
        os.unlink(tmp_path)

    roster = _parse_roster_text(text)
    if not roster:
        await update.message.reply_text(
            "Fayl bo'sh yoki noto'g'ri formatda. Qaytadan yuboring."
        )
        return AWAITING_ROSTER

    user_id = update.effective_user.id
    session = _load_session(user_id)
    session["roster"] = {str(k): v for k, v in roster.items()}
    _save_session(user_id, session)

    await update.message.reply_text(
        f"Ro'yxat saqlandi! {len(roster)} ta o'quvchi."
    )
    return ConversationHandler.END


# ============================================================
# Scan command and batch scanning
# ============================================================


async def scan_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle /scan - start scanning mode (batch mode by default)."""
    if not await _check_admin(update):
        return ConversationHandler.END

    user_id = update.effective_user.id
    session = _load_session(user_id)

    if not session.get("correct_answers"):
        await update.message.reply_text(
            "Avval /new_test orqali test yarating.\n"
            "To'g'ri javoblar kiritilmagan."
        )
        return ConversationHandler.END

    if len(session.get("students", [])) >= MAX_STUDENTS:
        await update.message.reply_text(
            f"Sessiya limiti ({MAX_STUDENTS} ta o'quvchi) tugadi.\n"
            f"/results bilan natijalarni oling va /new_test bilan yangi test yarating."
        )
        return ConversationHandler.END

    # Initialize batch scanning data
    context.user_data["batch_results"] = []
    context.user_data["unidentified_results"] = []
    context.user_data["auto_saved_count"] = 0
    context.user_data["batch_naming_index"] = 0

    has_roster = bool(session.get("roster"))
    roster_info = ""
    if has_roster:
        roster_info = (
            f"\nRo'yxat mavjud ({len(session['roster'])} ta). "
            "Raqami mos kelsa avtomatik saqlanadi."
        )

    await update.message.reply_text(
        "Skanerlash rejimi yoqildi (Ommaviy rejim).\n\n"
        "Barcha javob varaqalarini ketma-ket rasm sifatida yuboring.\n"
        "Rasmni fayl (document) sifatida ham yuborishingiz mumkin."
        f"{roster_info}\n\n"
        "Tugagandan so'ng /done buyrug'ini yuboring.\n"
        "Yakka rejim (har bir rasmdan keyin ism): /names_first\n"
        "Bekor qilish: /cancel"
    )
    return BATCH_SCANNING


async def names_first_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Switch to single mode (name after each photo)."""
    await update.message.reply_text(
        "Yakka rejim yoqildi.\n\n"
        "Rasm yuboring - keyin ism kiritasiz.\n"
        "Bekor qilish: /cancel"
    )
    return AWAITING_SCAN_PHOTO


async def _process_scan_image(tmp_path: str, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process a scanned image (shared logic for photos and documents in batch mode)."""
    user_id = update.effective_user.id
    session = _load_session(user_id)

    current_count = len(session.get("students", []))
    auto_count = context.user_data.get("auto_saved_count", 0)
    unid_count = len(context.user_data.get("unidentified_results", []))
    if current_count + auto_count + unid_count >= MAX_STUDENTS:
        os.unlink(tmp_path)
        await update.message.reply_text(
            f"Sessiya limiti ({MAX_STUDENTS} ta) tugadi. /done bilan davom eting."
        )
        return BATCH_SCANNING

    try:
        result = scan_answer_sheet(
            tmp_path,
            session["num_questions"],
            session["num_options"],
            session["correct_answers"],
        )
    finally:
        os.unlink(tmp_path)

    if result["error"]:
        await update.message.reply_text(
            f"Xatolik: {result['error']}\n\n"
            "Bu rasm o'tkazib yuborildi. Keyingi rasmni yuboring."
        )
        return BATCH_SCANNING

    roster = session.get("roster", {})
    student_number = result.get("student_number")
    score = result["score"]
    total = result["total"]
    pct = round((score / total) * 100, 1) if total > 0 else 0
    idx = context.user_data.get("auto_saved_count", 0) + len(context.user_data.get("unidentified_results", [])) + 1

    # Check uncertain questions
    uncertain = result.get("uncertain_questions", [])
    uncertain_info = ""
    if uncertain:
        uncertain_info = f"\nNoaniq savollar: {', '.join(str(q) for q in uncertain)}"

    # Auto-save logic: if student_number detected AND in roster
    if student_number and roster and str(student_number) in roster:
        name = roster[str(student_number)]
        # Auto-save immediately
        name_parts = name.split()
        student_record = {
            "name": name_parts[0] if name_parts else name,
            "surname": " ".join(name_parts[1:]) if len(name_parts) > 1 else "",
            "full_name": name,
            "score": score,
            "total": total,
            "answers": result.get("answers", []),
            "student_number": student_number,
            "uncertain_questions": uncertain,
        }
        if "students" not in session:
            session["students"] = []
        session["students"].append(student_record)
        _save_session(user_id, session)
        context.user_data["auto_saved_count"] = context.user_data.get("auto_saved_count", 0) + 1

        await update.message.reply_text(
            f"Rasm #{idx}: {name} - {score}/{total} ({pct}%) [auto]"
            f"{uncertain_info}\n"
            "Yana rasm yuboring yoki /done bilan tugating."
        )
    else:
        # Store in unidentified list
        unidentified = context.user_data.get("unidentified_results", [])
        unidentified.append(result)
        context.user_data["unidentified_results"] = unidentified

        num_info = ""
        if student_number:
            num_info = f" (Raqam: {student_number}, ro'yxatda yo'q)"

        await update.message.reply_text(
            f"Rasm #{idx}: {score}/{total} ({pct}%) - Ism aniqlanmadi{num_info}, /done da kiritasiz"
            f"{uncertain_info}"
        )

    return BATCH_SCANNING


async def receive_batch_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive photo in batch scanning mode."""
    if not update.message.photo:
        await update.message.reply_text(
            "Iltimos, rasm yuboring. Matn emas.\n"
            "Tugallash uchun /done yuboring."
        )
        return BATCH_SCANNING

    # Download photo
    photo = update.message.photo[-1]
    file = await photo.get_file()

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        await file.download_to_drive(tmp.name)
        tmp_path = tmp.name

    return await _process_scan_image(tmp_path, update, context)


async def receive_batch_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive document (photo sent as file) in batch scanning mode."""
    document = update.message.document
    if not document:
        await update.message.reply_text(
            "Iltimos, rasm yuboring.\n"
            "Tugallash uchun /done yuboring."
        )
        return BATCH_SCANNING

    # Check file size before downloading (max 10MB)
    if document.file_size and document.file_size > 10 * 1024 * 1024:
        await update.message.reply_text(
            "Fayl hajmi juda katta (max 10MB). Kichikroq rasm yuboring."
        )
        return BATCH_SCANNING

    file_name = (document.file_name or "").lower()
    valid_extensions = (".jpg", ".jpeg", ".png")
    if not file_name.endswith(valid_extensions):
        await update.message.reply_text(
            "Faqat rasm fayllar qabul qilinadi (.jpg, .jpeg, .png).\n"
            "Qaytadan yuboring."
        )
        return BATCH_SCANNING

    file = await document.get_file()
    suffix = Path(file_name).suffix
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        await file.download_to_drive(tmp.name)
        tmp_path = tmp.name

    return await _process_scan_image(tmp_path, update, context)


# ============================================================
# Done and batch naming
# ============================================================


async def done_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle /done - finish batch scanning, start naming unidentified sheets."""
    auto_saved = context.user_data.get("auto_saved_count", 0)
    unidentified = context.user_data.get("unidentified_results", [])

    if auto_saved == 0 and not unidentified:
        await update.message.reply_text(
            "Hali birorta rasm yuborilmagan.\n"
            "Rasm yuboring yoki /cancel bilan bekor qiling."
        )
        return BATCH_SCANNING

    if not unidentified:
        # All were auto-saved from roster
        await update.message.reply_text(
            f"Barcha {auto_saved} ta natija avtomatik saqlandi! /results"
        )
        return ConversationHandler.END

    context.user_data["batch_naming_index"] = 0

    if auto_saved > 0:
        await update.message.reply_text(
            f"{auto_saved} ta avtomatik saqlandi. {len(unidentified)} ta ism kiritish kerak."
        )
    else:
        await update.message.reply_text(
            f"Jami {len(unidentified)} ta varaq skanerlandi.\n"
            f"Endi har biri uchun ism kiriting."
        )

    # Show first result for naming
    return await _ask_batch_name(update, context)


async def _ask_batch_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ask for the next student name in batch naming."""
    idx = context.user_data.get("batch_naming_index", 0)
    unidentified = context.user_data.get("unidentified_results", [])

    if idx >= len(unidentified):
        # All named
        user_id = update.effective_user.id
        session = _load_session(user_id)
        total_students = len(session.get("students", []))
        await update.message.reply_text(
            f"Barcha natijalar saqlandi!\n"
            f"Jami tekshirilgan: {total_students} ta\n\n"
            f"Yana skanerlash: /scan\n"
            f"Natijalar: /results\n"
            f"Statistika: /stats"
        )
        return ConversationHandler.END

    result = unidentified[idx]
    score = result["score"]
    total = result["total"]
    pct = round((score / total) * 100, 1) if total > 0 else 0

    num_info = ""
    if result.get("student_number"):
        num_info = f" (Raqami: {result['student_number']})"

    uncertain = result.get("uncertain_questions", [])
    uncertain_info = ""
    if uncertain:
        uncertain_info = f"\nNoaniq savollar: {', '.join(str(q) for q in uncertain)}"

    await update.message.reply_text(
        f"Rasm #{idx + 1} natijasi: {score}/{total} ({pct}%){num_info}"
        f"{uncertain_info}\n"
        f"O'quvchi ismini kiriting:"
    )
    return BATCH_NAMING


async def receive_batch_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive student name in batch naming mode."""
    text = update.message.text.strip()
    parts = text.split(maxsplit=1)
    name = parts[0] if len(parts) > 0 else text
    surname = parts[1] if len(parts) > 1 else ""

    idx = context.user_data.get("batch_naming_index", 0)
    unidentified = context.user_data.get("unidentified_results", [])
    result = unidentified[idx]

    user_id = update.effective_user.id
    session = _load_session(user_id)

    student_record = {
        "name": name,
        "surname": surname,
        "full_name": text,
        "score": result.get("score", 0),
        "total": result.get("total", 0),
        "answers": result.get("answers", []),
        "student_number": result.get("student_number"),
        "uncertain_questions": result.get("uncertain_questions", []),
    }
    if "students" not in session:
        session["students"] = []
    session["students"].append(student_record)
    _save_session(user_id, session)

    # Check if there are uncertain questions to resolve
    uncertain = result.get("uncertain_questions", [])
    if uncertain:
        context.user_data["uncertain_student_idx"] = len(session["students"]) - 1
        context.user_data["uncertain_questions"] = uncertain
        await update.message.reply_text(
            f"Saqlandi: {text} - {result['score']}/{result['total']}\n"
            f"Noaniq savollar: {', '.join(str(q) for q in uncertain)}\n"
            f"Javobini kiriting (masalan: 12A,25C) yoki /skip"
        )
        return AWAITING_UNCERTAIN_ANSWERS

    # Move to next
    context.user_data["batch_naming_index"] = idx + 1
    return await _ask_batch_name(update, context)


# ============================================================
# Uncertain answers handling
# ============================================================


async def receive_uncertain_answers(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive manual answers for uncertain questions."""
    text = update.message.text.strip().upper()

    user_id = update.effective_user.id
    session = _load_session(user_id)
    student_idx = context.user_data.get("uncertain_student_idx")
    num_options = session.get("num_options", 4)
    option_letters = "ABCDE"[:num_options]
    correct_letters = session.get("correct_letters", [])

    if student_idx is None or student_idx >= len(session.get("students", [])):
        await update.message.reply_text("Xatolik. /done bilan davom eting.")
        return await _continue_after_uncertain(update, context)

    student = session["students"][student_idx]
    answers = student.get("answers", [])

    # Parse input like "12A,25C"
    pairs = re.findall(r"(\d+)\s*([A-E])", text)
    if not pairs:
        await update.message.reply_text(
            "Noto'g'ri format. Masalan: 12A,25C\n"
            "Yoki /skip bilan o'tkazib yuboring."
        )
        return AWAITING_UNCERTAIN_ANSWERS

    updated = 0
    for q_str, letter in pairs:
        q_num = int(q_str)
        if q_num < 1 or q_num > len(answers):
            continue
        if letter not in option_letters:
            continue
        # Update answer at question index (0-based)
        answers[q_num - 1] = letter
        updated += 1

    # Recalculate score
    score = 0
    for i, ans in enumerate(answers):
        if i < len(correct_letters) and ans == correct_letters[i]:
            score += 1

    student["answers"] = answers
    student["score"] = score
    student["uncertain_questions"] = []
    session["students"][student_idx] = student
    _save_session(user_id, session)

    total = student.get("total", 0)
    pct = round((score / total) * 100, 1) if total > 0 else 0
    await update.message.reply_text(
        f"Yangilandi! {updated} ta javob kiritildi. Yangi ball: {score}/{total} ({pct}%)"
    )

    return await _continue_after_uncertain(update, context)


async def skip_uncertain_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Skip uncertain answers, keep as-is."""
    await update.message.reply_text("Noaniq savollar o'tkazib yuborildi.")
    return await _continue_after_uncertain(update, context)


async def _continue_after_uncertain(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Continue batch naming after uncertain answers are handled."""
    idx = context.user_data.get("batch_naming_index", 0)
    context.user_data["batch_naming_index"] = idx + 1
    return await _ask_batch_name(update, context)


# ============================================================
# Single scan mode (names_first)
# ============================================================


async def receive_scan_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive and process a photo of a filled answer sheet (single/names_first mode)."""
    if not update.message.photo:
        await update.message.reply_text(
            "Iltimos, rasm yuboring. Matn emas."
        )
        return AWAITING_SCAN_PHOTO

    user_id = update.effective_user.id
    session = _load_session(user_id)

    if len(session.get("students", [])) >= MAX_STUDENTS:
        await update.message.reply_text(
            f"Sessiya limiti ({MAX_STUDENTS} ta o'quvchi) tugadi.\n"
            f"/results bilan natijalarni oling."
        )
        return ConversationHandler.END

    # Download photo (get highest resolution)
    photo = update.message.photo[-1]
    file = await photo.get_file()

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        await file.download_to_drive(tmp.name)
        tmp_path = tmp.name

    try:
        result = scan_answer_sheet(
            tmp_path,
            session["num_questions"],
            session["num_options"],
            session["correct_answers"],
        )
    finally:
        os.unlink(tmp_path)

    if result["error"]:
        await update.message.reply_text(
            f"Xatolik: {result['error']}\n\n"
            "Qaytadan rasm yuboring yoki /cancel bilan bekor qiling."
        )
        return AWAITING_SCAN_PHOTO

    # Store temporary result
    context.user_data["last_scan_result"] = result

    # Show result summary
    total = result["total"]
    score = result["score"]
    percentage = round((score / total) * 100, 1) if total > 0 else 0
    answers_display = " ".join(result["answers"])

    num_info = ""
    if result.get("student_number"):
        num_info = f"O'quvchi raqami: {result['student_number']}\n"

    uncertain = result.get("uncertain_questions", [])
    uncertain_info = ""
    if uncertain:
        uncertain_info = f"Noaniq savollar: {', '.join(str(q) for q in uncertain)}\n"

    await update.message.reply_text(
        f"Natija: {score}/{total} ({percentage}%)\n"
        f"{num_info}"
        f"{uncertain_info}"
        f"Javoblar: {answers_display}\n\n"
        f"O'quvchining ism va familiyasini kiriting\n"
        f"(masalan: Ali Valiyev):"
    )
    return AWAITING_STUDENT_NAME


async def receive_student_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive student name and save the result (single mode)."""
    text = update.message.text.strip()
    parts = text.split(maxsplit=1)
    name = parts[0] if len(parts) > 0 else text
    surname = parts[1] if len(parts) > 1 else ""

    user_id = update.effective_user.id
    session = _load_session(user_id)
    result = context.user_data.get("last_scan_result", {})

    # Save student result
    student_record = {
        "name": name,
        "surname": surname,
        "full_name": text,
        "score": result.get("score", 0),
        "total": result.get("total", 0),
        "answers": result.get("answers", []),
        "student_number": result.get("student_number"),
        "uncertain_questions": result.get("uncertain_questions", []),
    }
    if "students" not in session:
        session["students"] = []
    session["students"].append(student_record)
    _save_session(user_id, session)

    total = result.get("total", 0)
    score = result.get("score", 0)
    pct = round((score / total) * 100, 1) if total > 0 else 0

    await update.message.reply_text(
        f"Saqlandi!\n"
        f"O'quvchi: {name} {surname}\n"
        f"Ball: {score}/{total} ({pct}%)\n\n"
        f"Jami tekshirilgan: {len(session['students'])} ta\n\n"
        f"Yana rasm yuboring yoki /results bilan natijalarni oling."
    )
    return AWAITING_SCAN_PHOTO


# ============================================================
# Edit command
# ============================================================


async def edit_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /edit - update a correct answer and recalculate all scores.
    Syntax: /edit 5 B
    """
    if not await _check_admin(update):
        return

    user_id = update.effective_user.id
    session = _load_session(user_id)

    if not session.get("correct_answers"):
        await update.message.reply_text(
            "Avval /new_test orqali test yarating."
        )
        return

    # Parse arguments
    text = update.message.text.strip()
    parts = text.split()
    # Expected: /edit 5 B
    if len(parts) != 3:
        await update.message.reply_text(
            "Noto'g'ri format.\nTo'g'ri: /edit 5 B\n"
            "(savol raqami va yangi javob)"
        )
        return

    try:
        q_num = int(parts[1])
    except ValueError:
        await update.message.reply_text(
            "Savol raqami son bo'lishi kerak.\nMasalan: /edit 5 B"
        )
        return

    new_answer = parts[2].upper()
    num_questions = session.get("num_questions", 0)
    num_options = session.get("num_options", 4)
    option_letters = "ABCDE"[:num_options]

    if q_num < 1 or q_num > num_questions:
        await update.message.reply_text(
            f"Savol raqami 1 dan {num_questions} gacha bo'lishi kerak."
        )
        return

    if new_answer not in option_letters:
        await update.message.reply_text(
            f"Javob faqat {option_letters} harflaridan biri bo'lishi kerak."
        )
        return

    # Update correct answers
    q_idx = q_num - 1
    new_answer_idx = option_letters.index(new_answer)
    session["correct_answers"][q_idx] = new_answer_idx
    session["correct_letters"][q_idx] = new_answer

    # Recalculate all student scores
    correct_letters = session["correct_letters"]
    students = session.get("students", [])
    for student in students:
        answers = student.get("answers", [])
        score = 0
        for i, ans in enumerate(answers):
            if i < len(correct_letters) and ans == correct_letters[i]:
                score += 1
        student["score"] = score

    session["students"] = students
    _save_session(user_id, session)

    await update.message.reply_text(
        f"{q_num}-savol javobi {new_answer} ga o'zgartirildi. "
        f"Barcha ballar qayta hisoblandi."
    )


# ============================================================
# Results and stats
# ============================================================


async def results_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle /results - generate and send Excel file."""
    if not await _check_admin(update):
        return ConversationHandler.END

    user_id = update.effective_user.id
    session = _load_session(user_id)

    students = session.get("students", [])
    if not students:
        await update.message.reply_text(
            "Hali hech qanday natija yo'q.\n"
            "Avval /scan orqali javob varaqalarini skanerlang."
        )
        return ConversationHandler.END

    # Generate Excel
    buf = generate_results_excel(students)
    num_students = len(students)

    await update.message.reply_document(
        document=buf,
        filename="test_natijalari.xlsx",
        caption=f"Natijalar tayyor! Jami: {num_students} ta o'quvchi.",
    )
    return ConversationHandler.END


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle /stats - show test statistics."""
    if not await _check_admin(update):
        return ConversationHandler.END

    user_id = update.effective_user.id
    session = _load_session(user_id)

    students = session.get("students", [])
    if not students:
        await update.message.reply_text(
            "Hali hech qanday natija yo'q.\n"
            "Avval /scan orqali javob varaqalarini skanerlang."
        )
        return ConversationHandler.END

    num_students = len(students)
    scores = [s.get("score", 0) for s in students]
    total = students[0].get("total", 1) if students else 1

    avg_score = sum(scores) / num_students if num_students > 0 else 0
    avg_pct = round((avg_score / total) * 100, 1) if total > 0 else 0
    max_score = max(scores)
    min_score = min(scores)
    max_pct = round((max_score / total) * 100, 1) if total > 0 else 0
    min_pct = round((min_score / total) * 100, 1) if total > 0 else 0

    # Find hardest question (most wrong answers)
    num_questions = session.get("num_questions", 0)
    correct_answers = session.get("correct_letters", [])
    wrong_counts = [0] * num_questions

    for student in students:
        answers = student.get("answers", [])
        for i in range(min(len(answers), num_questions)):
            if i < len(correct_answers) and answers[i] != correct_answers[i]:
                wrong_counts[i] += 1

    hardest_q = 0
    hardest_wrong = 0
    if wrong_counts:
        hardest_q = wrong_counts.index(max(wrong_counts)) + 1
        hardest_wrong = max(wrong_counts)
    hardest_pct = round((hardest_wrong / num_students) * 100, 1) if num_students > 0 else 0

    await update.message.reply_text(
        f"Statistika:\n\n"
        f"O'quvchilar soni: {num_students}\n"
        f"O'rtacha ball: {avg_score:.1f}/{total} ({avg_pct}%)\n"
        f"Eng yuqori: {max_score}/{total} ({max_pct}%)\n"
        f"Eng past: {min_score}/{total} ({min_pct}%)\n\n"
        f"Eng qiyin savol: #{hardest_q} ({hardest_wrong}/{num_students} xato, {hardest_pct}%)"
    )
    return ConversationHandler.END


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle /cancel - cancel current operation."""
    await update.message.reply_text("Bekor qilindi.")
    return ConversationHandler.END


# ============================================================
# Main application setup
# ============================================================


def main() -> None:
    """Run the bot."""
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN topilmadi! .env faylini tekshiring.")
        return

    # Build application
    app = Application.builder().token(BOT_TOKEN).build()

    # New test conversation
    new_test_conv = ConversationHandler(
        entry_points=[CommandHandler("new_test", new_test_command)],
        states={
            AWAITING_NUM_QUESTIONS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_num_questions)
            ],
            AWAITING_NUM_OPTIONS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_num_options)
            ],
            AWAITING_ANSWERS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_answers)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_command)],
    )

    # Roster conversation
    roster_conv = ConversationHandler(
        entry_points=[CommandHandler("roster", roster_command)],
        states={
            AWAITING_ROSTER: [
                MessageHandler(filters.Document.ALL, receive_roster_document),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_roster_text),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_command)],
    )

    # Scan conversation (supports batch and single modes, plus documents)
    scan_conv = ConversationHandler(
        entry_points=[CommandHandler("scan", scan_command)],
        states={
            BATCH_SCANNING: [
                MessageHandler(filters.PHOTO, receive_batch_photo),
                MessageHandler(filters.Document.ALL, receive_batch_document),
                CommandHandler("done", done_command),
                CommandHandler("names_first", names_first_command),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_batch_photo),
            ],
            BATCH_NAMING: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_batch_name),
            ],
            AWAITING_UNCERTAIN_ANSWERS: [
                CommandHandler("skip", skip_uncertain_command),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_uncertain_answers),
            ],
            AWAITING_SCAN_PHOTO: [
                MessageHandler(filters.PHOTO, receive_scan_photo),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_scan_photo),
            ],
            AWAITING_STUDENT_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_student_name)
            ],
        },
        fallbacks=[
            CommandHandler("results", results_command),
            CommandHandler("stats", stats_command),
            CommandHandler("cancel", cancel_command),
        ],
    )

    # Add handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(new_test_conv)
    app.add_handler(roster_conv)
    app.add_handler(scan_conv)
    app.add_handler(CommandHandler("edit", edit_command))
    app.add_handler(CommandHandler("results", results_command))
    app.add_handler(CommandHandler("stats", stats_command))

    # Run
    logger.info("Bot ishga tushdi...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
