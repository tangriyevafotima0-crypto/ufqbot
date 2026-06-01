import io
import hashlib
import random
import string
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import qrcode
from bot.config import BOT_USERNAME


def generate_pin():
    """6 xonali unikal PIN generatsiya qilish"""
    return ''.join(random.choices(string.digits, k=6))


def generate_security_hash(user_id: int, event_id: int, pin: str, timestamp: str):
    """Xavfsizlik hash yaratish"""
    data = f"{user_id}:{event_id}:{pin}:{timestamp}"
    return hashlib.sha256(data.encode()).hexdigest()[:16]


def generate_qr_data(ticket_id: int, pin: str):
    """QR kod uchun deep link yaratish"""
    return f"https://t.me/{BOT_USERNAME}?start=checkin_{ticket_id}_{pin}"


def get_status_badge(points: int):
    """Ball asosida status belgisini qaytarish"""
    if points >= 121:
        return "[PLATINUM]"
    elif points >= 51:
        return "[OLTIN]"
    elif points >= 16:
        return "[KUMUSH]"
    else:
        return "[BRONZA]"


async def generate_ticket_image(
    user_full_name: str,
    user_points: int,
    event_title: str,
    event_date: str,
    club_name: str,
    pin: str,
    qr_data: str
) -> io.BytesIO:
    """E-Chipta rasmi generatsiya qilish"""
    width, height = 800, 450

    bg_color = (15, 23, 42)
    accent_color = (56, 189, 248)
    text_color = (255, 255, 255)

    img = Image.new('RGB', (width, height), bg_color)
    draw = ImageDraw.Draw(img)

    for i in range(5):
        y = 50 + i * 80
        draw.line([(0, y), (width, y)], fill=(30, 41, 59), width=1)

    # Shriftlarni yuklash
    try:
        title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
        regular_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
        small_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
    except (IOError, OSError):
        try:
            title_font = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 28)
            regular_font = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", 20)
            small_font = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", 14)
        except (IOError, OSError):
            title_font = ImageFont.load_default()
            regular_font = ImageFont.load_default()
            small_font = ImageFont.load_default()

    draw.text((40, 30), "UFQ COMMUNITY", font=title_font, fill=accent_color)
    draw.text((40, 55), "TADBIR CHIPTA", font=regular_font, fill=text_color)

    draw.line([(40, 90), (width - 40, 90)], fill=accent_color, width=2)

    y_offset = 120
    draw.text((40, y_offset), f"Tadbir: {event_title}", font=regular_font, fill=text_color)
    draw.text((40, y_offset + 35), f"Sana:   {event_date}", font=regular_font, fill=text_color)
    draw.text((40, y_offset + 70), f"Ism:    {user_full_name}", font=regular_font, fill=text_color)

    status_badge = get_status_badge(user_points)
    draw.text((40, y_offset + 105), f"Status: {status_badge} ({user_points} ball)", font=regular_font, fill=accent_color)
    draw.text((40, y_offset + 140), f"Klub:   {club_name}", font=regular_font, fill=text_color)

    draw.text((40, y_offset + 185), f"PIN:    {' '.join(pin)}", font=title_font, fill=accent_color)

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=4,
        border=2,
    )
    qr.add_data(qr_data)
    qr.make(fit=True)

    qr_img = qr.make_image(fill_color="black", back_color="white")
    qr_img = qr_img.resize((180, 180))

    img.paste(qr_img, (width - 220, 120))

    draw.text((width - 220, 310), "QR SCANNER", font=small_font, fill=text_color)

    draw.line([(40, height - 50), (width - 40, height - 50)], fill=accent_color, width=1)
    draw.text(
        (width // 2 - 100, height - 35),
        f"(c) {datetime.now().year} UFQ Events",
        font=small_font,
        fill=text_color
    )

    output = io.BytesIO()
    img.save(output, format='PNG')
    output.seek(0)

    return output
