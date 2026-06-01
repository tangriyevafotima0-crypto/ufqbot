#!/bin/bash
# ============================================================
# UFQ UNIFIED SYSTEM - DEPLOY SCRIPT
# Team Bot + Event Bot (Bitta umumiy ma'lumotlar bazasi)
# ============================================================
set -e

echo "================================================="
echo "   UFQ UNIFIED SYSTEM - DEPLOY SCRIPT            "
echo "   Team Bot + Event Bot (Shared Database)        "
echo "================================================="
echo ""

# ============================================================
# O'zgaruvchilar
# ============================================================
INSTALL_DIR="/home/ubuntu/UFQ_SYSTEM"
BACKUP_DIR="/home/ubuntu/ufq_db_backup"
DB_FILE="$INSTALL_DIR/shared/ufq_system.db"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ============================================================
# [1] Sozlamalar - foydalanuvchidan so'rash
# ============================================================
echo "Iltimos, quyidagi ma'lumotlarni kiriting:"
echo ""
read -p "Team Bot Token: " TEAM_BOT_TOKEN
read -p "Event Bot Token: " EVENT_BOT_TOKEN
read -p "Admin Telegram ID: " ADMIN_ID
read -p "Team Bot Username (masalan: UFQ_JAMOA_BOT - @ belgisiz): " TEAM_BOT_USERNAME
read -p "Event Bot Username (masalan: UFQ_EVENT_BOT - @ belgisiz): " EVENT_BOT_USERNAME
read -p "Kanal IDlari [default: -1003754712535,-1003157594758]: " CHANNELS
CHANNELS=${CHANNELS:--1003754712535,-1003157594758}

if [ -z "$TEAM_BOT_TOKEN" ] || [ -z "$EVENT_BOT_TOKEN" ] || [ -z "$ADMIN_ID" ]; then
    echo "XATOLIK: TEAM_BOT_TOKEN, EVENT_BOT_TOKEN va ADMIN_ID majburiy!"
    exit 1
fi

if [ -z "$EVENT_BOT_USERNAME" ]; then
    echo "XATOLIK: EVENT_BOT_USERNAME majburiy! QR kod skanerlash uchun kerak."
    exit 1
fi

echo ">>> Sozlamalar:"
echo "   Admin ID: $ADMIN_ID"
echo "   Team Bot Username: $TEAM_BOT_USERNAME"
echo "   Event Bot Username: $EVENT_BOT_USERNAME"
echo ""

# ============================================================
# [1/8] Eski xizmatlarni to'xtatish
# ============================================================
echo ">>> [1/8] Eski xizmatlar to'xtatilmoqda..."
sudo systemctl stop ufq-bot 2>/dev/null || true
sudo systemctl stop ufq-event-bot 2>/dev/null || true
sudo systemctl stop ufq-team-bot 2>/dev/null || true
sudo systemctl disable ufq-bot 2>/dev/null || true
sudo systemctl disable ufq-event-bot 2>/dev/null || true
sudo systemctl disable ufq-team-bot 2>/dev/null || true
sudo rm -f /etc/systemd/system/ufq-bot.service
sudo rm -f /etc/systemd/system/ufq-event-bot.service
sudo rm -f /etc/systemd/system/ufq-team-bot.service

# ============================================================
# [2/8] Bazani zaxiralash
# ============================================================
echo ">>> [2/8] Mavjud ma'lumotlar bazasi zaxiralanmoqda..."
mkdir -p "$BACKUP_DIR"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

if [ -f "/home/ubuntu/UFQ_BOT_V9_FINAL/ufq_jamoa.db" ]; then
    cp "/home/ubuntu/UFQ_BOT_V9_FINAL/ufq_jamoa.db" "$BACKUP_DIR/ufq_jamoa_$TIMESTAMP.db"
    echo "   Zaxira: ufq_jamoa.db"
fi
if [ -f "$DB_FILE" ]; then
    cp "$DB_FILE" "$BACKUP_DIR/ufq_system_$TIMESTAMP.db"
    echo "   Zaxira: ufq_system.db"
fi
if [ -f "/home/ubuntu/UFQ_EVENT_BOT_FINAL/ufq_events.db" ]; then
    cp "/home/ubuntu/UFQ_EVENT_BOT_FINAL/ufq_events.db" "$BACKUP_DIR/ufq_events_$TIMESTAMP.db"
    echo "   Zaxira: ufq_events.db"
fi

# ============================================================
# [3/8] Eski fayllarni tozalash
# ============================================================
echo ">>> [3/8] Eski fayllar tozalanmoqda..."
sudo rm -rf /home/ubuntu/UFQ_BOT_V9_FINAL
sudo rm -rf /home/ubuntu/UFQ_EVENT_BOT_FINAL

# Agar script INSTALL_DIR ichida bo'lmasa, INSTALL_DIR ni tozalash
if [ "$SCRIPT_DIR" != "$INSTALL_DIR" ]; then
    sudo rm -rf "$INSTALL_DIR"
fi

# ============================================================
# [4/8] Fayllarni joylashtirish
# ============================================================
echo ">>> [4/8] Yangi tuzilma yaratilmoqda..."
mkdir -p "$INSTALL_DIR/shared"

if [ "$SCRIPT_DIR" != "$INSTALL_DIR" ]; then
    # Script boshqa joyda (masalan unzip qilingan papkada) - ko'chirish kerak
    cp -r "$SCRIPT_DIR/team_bot" "$INSTALL_DIR/"
    cp -r "$SCRIPT_DIR/event_bot" "$INSTALL_DIR/"
    cp "$SCRIPT_DIR/SYSTEM_README.md" "$INSTALL_DIR/" 2>/dev/null || true
    cp "$SCRIPT_DIR/deploy.sh" "$INSTALL_DIR/" 2>/dev/null || true
    echo "   Fayllar ko'chirildi: $SCRIPT_DIR -> $INSTALL_DIR"
else
    echo "   Fayllar allaqachon to'g'ri joyda."
fi

# Bazani tiklash
if [ -f "$BACKUP_DIR/ufq_system_$TIMESTAMP.db" ]; then
    cp "$BACKUP_DIR/ufq_system_$TIMESTAMP.db" "$DB_FILE"
    echo "   Baza tiklandi: ufq_system.db"
elif [ -f "$BACKUP_DIR/ufq_jamoa_$TIMESTAMP.db" ]; then
    cp "$BACKUP_DIR/ufq_jamoa_$TIMESTAMP.db" "$DB_FILE"
    echo "   Baza tiklandi: ufq_jamoa.db -> ufq_system.db"
fi

# ============================================================
# [5/8] .env fayllar yaratish
# ============================================================
echo ">>> [5/8] .env fayllar yaratilmoqda..."
cat > "$INSTALL_DIR/team_bot/.env" << EOF
BOT_TOKEN=$TEAM_BOT_TOKEN
ADMIN_ID=$ADMIN_ID
DB_PATH=$DB_FILE
EOF

cat > "$INSTALL_DIR/event_bot/.env" << EOF
BOT_TOKEN=$EVENT_BOT_TOKEN
SUPER_ADMIN_ID=$ADMIN_ID
CHANNELS=$CHANNELS
BOT_USERNAME=$EVENT_BOT_USERNAME
DB_PATH=$DB_FILE
EOF

# ============================================================
# [6/8] Python muhiti
# ============================================================
echo ">>> [6/8] Python muhiti va paketlar o'rnatilmoqda..."
sudo apt-get update -y -qq
sudo apt-get install -y -qq python3-venv python3-pip redis-server

sudo systemctl enable redis-server
sudo systemctl start redis-server

echo "   Team Bot paketlari..."
rm -rf "$INSTALL_DIR/team_bot/venv"
python3 -m venv "$INSTALL_DIR/team_bot/venv"
"$INSTALL_DIR/team_bot/venv/bin/pip" install --upgrade pip -q
"$INSTALL_DIR/team_bot/venv/bin/pip" install -r "$INSTALL_DIR/team_bot/requirements.txt" -q

echo "   Event Bot paketlari..."
rm -rf "$INSTALL_DIR/event_bot/venv"
python3 -m venv "$INSTALL_DIR/event_bot/venv"
"$INSTALL_DIR/event_bot/venv/bin/pip" install --upgrade pip -q
"$INSTALL_DIR/event_bot/venv/bin/pip" install -r "$INSTALL_DIR/event_bot/requirements.txt" -q

# ============================================================
# [7/8] Systemd xizmatlari
# ============================================================
echo ">>> [7/8] Systemd xizmatlari sozlanmoqda..."
cat << EOF | sudo tee /etc/systemd/system/ufq-team-bot.service > /dev/null
[Unit]
Description=UFQ Team Bot
After=network.target redis-server.service

[Service]
User=ubuntu
WorkingDirectory=$INSTALL_DIR/team_bot
ExecStart=$INSTALL_DIR/team_bot/venv/bin/python -m bot.main
Restart=always
RestartSec=3
Environment=DB_PATH=$DB_FILE

[Install]
WantedBy=multi-user.target
EOF

cat << EOF | sudo tee /etc/systemd/system/ufq-event-bot.service > /dev/null
[Unit]
Description=UFQ Event Bot
After=network.target

[Service]
User=ubuntu
WorkingDirectory=$INSTALL_DIR/event_bot
ExecStart=$INSTALL_DIR/event_bot/venv/bin/python -m bot.main
Restart=always
RestartSec=3
Environment=DB_PATH=$DB_FILE

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable ufq-team-bot
sudo systemctl enable ufq-event-bot
sudo systemctl restart ufq-team-bot
sudo systemctl restart ufq-event-bot

# ============================================================
# [8/8] Tekshirish
# ============================================================
echo ">>> [8/8] Tizim tekshirilmoqda..."
sleep 4

TEAM_OK=false
EVENT_OK=false

if sudo systemctl is-active --quiet ufq-team-bot; then TEAM_OK=true; fi
if sudo systemctl is-active --quiet ufq-event-bot; then EVENT_OK=true; fi

# Fayl egaligini to'g'rilash
sudo chown -R ubuntu:ubuntu "$INSTALL_DIR"

echo ""
echo "========================================================="
if [ "$TEAM_OK" = true ] && [ "$EVENT_OK" = true ]; then
    echo " ✅ MUVAFFAQIYAT! Ikkala bot ham ishga tushdi!"
elif [ "$TEAM_OK" = true ]; then
    echo " ⚠️  Team Bot OK, Event Bot XATOLIK!"
    sudo journalctl -u ufq-event-bot -n 10 --no-pager
elif [ "$EVENT_OK" = true ]; then
    echo " ⚠️  Event Bot OK, Team Bot XATOLIK!"
    sudo journalctl -u ufq-team-bot -n 10 --no-pager
else
    echo " ❌ XATOLIK! Ikkala bot ham ishga tushmadi!"
    echo ""
    echo " Team Bot:"
    sudo journalctl -u ufq-team-bot -n 10 --no-pager
    echo ""
    echo " Event Bot:"
    sudo journalctl -u ufq-event-bot -n 10 --no-pager
fi
echo ""
echo " O'rnatish: $INSTALL_DIR"
echo " Baza: $DB_FILE"
echo "========================================================="
echo ""
echo " Foydali buyruqlar:"
echo "   sudo systemctl status ufq-team-bot"
echo "   sudo systemctl status ufq-event-bot"
echo "   sudo journalctl -u ufq-team-bot -f"
echo "   sudo journalctl -u ufq-event-bot -f"
echo "========================================================="
