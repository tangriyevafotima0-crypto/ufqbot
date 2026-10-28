# Davomat jurnali

O'quvchilar ro'yxati va darslarga davomatni belgilash uchun Excel jurnali.

## Fayllar

- **`Davomat_jurnali.xlsx`** — tayyor jurnal (Excel/Google Sheets'da ishlatish uchun).
- **`jurnal_yaratish.py`** — jurnalni qaytadan generatsiya qiluvchi skript.

## Tuzilishi

### 1-list — "O'quvchilar"
| № | F.I.SH. | Telefon raqami | Izoh |
|---|---------|----------------|------|

O'quvchilar ismini shu listga yozasiz.

### 2-list — "Davomat"
| № | F.I.SH. | 1-dars | 2-dars | ... | 30-dars | Jami + | Jami - | Jami 0 | Davomat % |
|---|---------|--------|--------|-----|---------|--------|--------|--------|-----------|

- **Sana qatori** (har bir darsning tagidagi 3-qator) — bo'sh, sanani o'zingiz kiritasiz.
- **Ismlar** 1-listdan avtomatik tortib olinadi.
- Kataklarga faqat `+`, `-`, `0` kiritiladi (boshqasi xato beradi).

## Belgilar

| Belgi | Ma'nosi | Rang |
|-------|---------|------|
| `+` | qatnashdi | yashil |
| `-` | qatnashmadi | qizil |
| `0` | sababli / kech qoldi | sariq |

Har bir o'quvchining `+`, `-`, `0` soni va umumiy **davomat foizi** avtomatik hisoblanadi.

## Qayta generatsiya qilish

O'quvchilar yoki darslar sonini o'zgartirish uchun `jurnal_yaratish.py` faylidagi `OQUVCHILAR_SONI` va `DARSLAR_SONI` qiymatlarini o'zgartiring:

```bash
pip install openpyxl
python3 jurnal_yaratish.py
```
