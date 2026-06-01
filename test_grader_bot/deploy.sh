#!/bin/bash
# ============================================================
# TEST GRADER BOT - DEPLOY SCRIPT
# Test tekshiruvchi bot uchun o'rnatish skripti
# ============================================================
set -e

echo "================================================="
echo "   TEST GRADER BOT - DEPLOY SCRIPT               "
echo "================================================="
echo ""

# ============================================================
# O'zgaruvchilar
# ============================================================
INSTALL_DIR="/home/ubuntu/TEST_GRADER_BOT"
SERVICE_NAME="ufq-test-grader-bot"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ============================================================
# [1] Sozlamalar
# ============================================================
echo "Iltimos, quyidagi ma'lumotlarni kiriting:"
echo ""
read -p "Bot Token: " BOT_TOKEN
read -p "Admin Telegram ID: " ADMIN_ID

if [ -z "$BOT_TOKEN" ] || [ -z "$ADMIN_ID" ]; then
    echo "XATOLIK: BOT_TOKEN va ADMIN_ID majburiy!"
    exit 1
fi

echo ""
echo ">>> Sozlamalar:"
echo "   Admin ID: $ADMIN_ID"
echo "   O'rnatish: $INSTALL_DIR"
echo ""

# ============================================================
# [2] Eski xizmatni to'xtatish
# ============================================================
echo ">>> [1/6] Eski xizmat to'xtatilmoqda..."
sudo systemctl stop "$SERVICE_NAME" 2>/dev/null || true
sudo systemctl disable "$SERVICE_NAME" 2>/dev/null || true

# ============================================================
# [3] Fayllarni joylashtirish
# ============================================================
echo ">>> [2/6] Fayllar joylashtirilmoqda..."
mkdir -p "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR/data"

cp "$SCRIPT_DIR/config.py" "$INSTALL_DIR/"
cp "$SCRIPT_DIR/bot.py" "$INSTALL_DIR/"
cp "$SCRIPT_DIR/sheet_generator.py" "$INSTALL_DIR/"
cp "$SCRIPT_DIR/omr_scanner.py" "$INSTALL_DIR/"
cp "$SCRIPT_DIR/excel_export.py" "$INSTALL_DIR/"
cp "$SCRIPT_DIR/requirements.txt" "$INSTALL_DIR/"

echo "   Fayllar ko'chirildi."

# ============================================================
# [4] .env fayl yaratish
# ============================================================
echo ">>> [3/6] .env fayl yaratilmoqda..."
cat > "$INSTALL_DIR/.env" << EOF
BOT_TOKEN=$BOT_TOKEN
ADMIN_ID=$ADMIN_ID
EOF
chmod 600 "$INSTALL_DIR/.env"

# ============================================================
# [5] Python muhiti
# ============================================================
echo ">>> [4/6] Python muhiti o'rnatilmoqda..."
sudo apt-get update -y -qq
sudo apt-get install -y -qq python3-venv python3-pip

rm -rf "$INSTALL_DIR/venv"
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip -q
"$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt" -q

echo "   Paketlar o'rnatildi."

# ============================================================
# [6] Systemd xizmati
# ============================================================
echo ">>> [5/6] Systemd xizmati sozlanmoqda..."
cat << EOF | sudo tee /etc/systemd/system/${SERVICE_NAME}.service > /dev/null
[Unit]
Description=UFQ Test Grader Bot
After=network.target

[Service]
User=ubuntu
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/python bot.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"

# ============================================================
# [7] Tekshirish
# ============================================================
echo ">>> [6/6] Tekshirilmoqda..."
sleep 3

if sudo systemctl is-active --quiet "$SERVICE_NAME"; then
    echo ""
    echo "========================================================="
    echo " MUVAFFAQIYAT! Bot ishga tushdi!"
    echo ""
    echo " O'rnatish: $INSTALL_DIR"
    echo "========================================================="
else
    echo ""
    echo "========================================================="
    echo " XATOLIK! Bot ishga tushmadi!"
    echo ""
    sudo journalctl -u "$SERVICE_NAME" -n 15 --no-pager
    echo "========================================================="
fi

echo ""
echo " Foydali buyruqlar:"
echo "   sudo systemctl status $SERVICE_NAME"
echo "   sudo journalctl -u $SERVICE_NAME -f"
echo "   sudo systemctl restart $SERVICE_NAME"
echo "========================================================="
