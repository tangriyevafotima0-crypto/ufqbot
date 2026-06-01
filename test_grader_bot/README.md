# Test Tekshiruvchi Bot

Telegram bot orqali test va imtihon natijalarini avtomatik tekshirish tizimi.

## Bot nima qiladi?

1. **Javob varaqasi yaratadi** - Chop etishga tayyor A4 formatdagi javob varaqasi
2. **Rasmdan javoblarni o'qiydi** - OMR (Optical Mark Recognition) texnologiyasi orqali
3. **Natijalarni hisoblaydi** - Har bir o'quvchining ballini avtomatik hisoblaydi
4. **Excel fayl tayyorlaydi** - Barcha natijalarni Excel jadvalida beradi

## O'rnatish

### Talablar

- Python 3.10+
- Linux server (Ubuntu 20.04+)

### Qadamlar

1. Repositoriyani klonlang:
```bash
git clone <repo-url>
cd test_grader_bot
```

2. Deploy skriptini ishga tushiring:
```bash
chmod +x deploy.sh
./deploy.sh
```

3. Bot token va Admin ID kiriting (skript so'raydi)

### Qo'lda o'rnatish

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# .env fayl yarating
echo "BOT_TOKEN=your_bot_token_here" > .env
echo "ADMIN_ID=your_telegram_id" >> .env

# Ishga tushiring
python bot.py
```

## Bot buyruqlari

| Buyruq | Vazifasi |
|--------|----------|
| `/start` | Botni boshlash, yordam |
| `/new_test` | Yangi test yaratish |
| `/scan` | Javob varaqasini skanerlash |
| `/results` | Natijalarni Excel olish |
| `/cancel` | Joriy amalni bekor qilish |

## Foydalanish tartibi

### 1. Test yaratish (`/new_test`)

1. Savollar sonini kiriting (1-100)
2. Variantlar sonini kiriting (2-5)
3. To'g'ri javoblarni ketma-ket yozing (masalan: `ABCDABCADB`)
4. Bot javob varaqasini rasm sifatida yuboradi

### 2. Varaqani chop etish

- Olingan rasmni A4 formatda chop eting
- Har bir o'quvchiga bitta varaq bering
- O'quvchi javobini qora ruchka/marker bilan to'ldiradi

### 3. Tekshirish (`/scan`)

1. `/scan` buyrug'ini yuboring
2. To'ldirilgan varaqaning rasmini yuboring
3. Bot natijani ko'rsatadi
4. O'quvchining ismini kiriting
5. Keyingi varaq rasmini yuboring yoki `/results` bilan tugating

### 4. Natijalar (`/results`)

- Excel fayl yuklab olinadi
- Jadvalda: tartib raqami, ism, familiya, ball, foiz

## Rasmga olish bo'yicha maslahatlar

Aniq natija olish uchun quyidagilarga e'tibor bering:

1. **Yorug'lik** - Yaxshi yorug'likda suratga oling, soya tushmasin
2. **Tekislik** - Varaqni tekis joyga qo'ying, burmalamasin
3. **Burchaklar** - 4 ta burchakdagi qora kvadratlar ko'rinsin
4. **Masofa** - Varaq rasmning 80% dan ko'proq joyni egallashi kerak
5. **Fokus** - Rasm tiniq bo'lsin, xiralashmasin
6. **To'ldirish** - O'quvchilar doirani to'liq bo'yashi kerak (faqat belgi qo'yish emas)

## Texnik ma'lumotlar

- **OMR texnologiyasi** - OpenCV kutubxonasi orqali bubble detection
- **Xotira** - 120 MB dan kam RAM ishlatadi
- **Saqlanish** - Ma'lumotlar JSON faylda saqlanadi (`data/` papka)
- **Format** - A4, 300 DPI, PNG rasm

## Muammolarni hal qilish

| Muammo | Yechim |
|--------|--------|
| Javoblar noto'g'ri aniqlandi | Yaxshiroq rasmga oling, yorug'likni oshiring |
| Burchaklar topilmadi | 4 ta qora kvadrat ko'rinishiga ishonch hosil qiling |
| Bot javob bermaydi | `sudo systemctl status ufq-test-grader-bot` bilan tekshiring |

## Litsenziya

Ichki foydalanish uchun.
