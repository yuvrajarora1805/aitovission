#!/usr/bin/env bash
# Quick automated setup script for BMU Sketch-to-Art Kiosk on Debian/Ubuntu/Kali Linux

set -e

echo "=== BMU Sketch-to-Art Kiosk Setup ==="

# 1. System packages
echo "[1/3] Installing system packages (ffmpeg, fonts)..."
if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update -y
    sudo apt-get install -y ffmpeg fonts-dejavu-core python3-pip
elif command -v dnf >/dev/null 2>&1; then
    sudo dnf install -y ffmpeg dejavu-sans-fonts python3-pip
elif command -v pacman >/dev/null 2>&1; then
    sudo pacman -Sy --noconfirm ffmpeg ttf-dejavu python-pip
fi

# 2. Python requirements
echo "[2/3] Installing Python requirements..."
pip3 install -r requirements.txt --break-system-packages 2>/dev/null || pip3 install -r requirements.txt

# 3. Create outputs directory
echo "[3/3] Preparing output directories..."
mkdir -p outputs

echo "=== Setup complete! ==="
echo "To run the bridge: python3 comfy_bridge.py"
