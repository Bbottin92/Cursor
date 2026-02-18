#!/bin/bash
# Self-Healing System - Quick Setup Script
# Run as root: sudo bash setup.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=============================================="
echo "Self-Healing System - Quick Setup"
echo "=============================================="

# Check root
if [ "$EUID" -ne 0 ]; then
    echo "ERROR: Please run as root (sudo bash setup.sh)"
    exit 1
fi

# Check Python 3
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 is required but not installed."
    echo "Install with: apt install python3"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "Python version: $PYTHON_VERSION"

# Create directories
echo ""
echo "[1/5] Creating system directories..."
mkdir -p /opt/self-healing-system
mkdir -p /etc/self-healing
mkdir -p /var/lib/self-healing
mkdir -p /var/log/self-healing
mkdir -p /var/run/self-healing

# Copy files
echo "[2/5] Installing files..."
cp -r "$PROJECT_DIR"/* /opt/self-healing-system/
chmod +x /opt/self-healing-system/main.py
chmod +x /opt/self-healing-system/scripts/boot_recovery.py

# Install systemd services
echo "[3/5] Installing systemd services..."
cp "$PROJECT_DIR/scripts/self-healing-daemon.service" /etc/systemd/system/
cp "$PROJECT_DIR/scripts/self-healing-watchdog.service" /etc/systemd/system/
cp "$PROJECT_DIR/scripts/self-healing-boot.service" /etc/systemd/system/
chmod 644 /etc/systemd/system/self-healing-*.service

# Generate config if not exists
echo "[4/5] Configuring..."
if [ ! -f /etc/self-healing/config.json ]; then
    cd /opt/self-healing-system
    python3 -c "
import sys
sys.path.insert(0, '.')
from config.settings import Settings
s = Settings()
s.save('/etc/self-healing/config.json')
print('  Default configuration generated')
"
else
    echo "  Configuration already exists, preserved."
fi

# Enable and start
echo "[5/5] Enabling and starting services..."
systemctl daemon-reload
systemctl enable self-healing-daemon self-healing-watchdog self-healing-boot
systemctl start self-healing-daemon
sleep 2
systemctl start self-healing-watchdog

echo ""
echo "=============================================="
echo "Installation complete!"
echo ""
echo "Status check:"
systemctl is-active self-healing-daemon || true
systemctl is-active self-healing-watchdog || true
echo ""
echo "API endpoint: http://localhost:7847/api/health"
echo "Logs: journalctl -u self-healing-daemon -f"
echo "Status: python3 /opt/self-healing-system/main.py --mode status"
echo "=============================================="
