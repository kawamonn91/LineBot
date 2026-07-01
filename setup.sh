#!/bin/bash
# setup.sh — 玄関モニタリングシステム 環境構築スクリプト
# Raspberry Pi 5 上で実行してください
#
# 使用方法:
#   chmod +x setup.sh
#   ./setup.sh

set -e  # エラー時に停止

echo "=============================================="
echo " 玄関モニタリングシステム セットアップ開始"
echo "=============================================="

# ── システムパッケージのアップデート ──────────────────────────────────
echo ""
echo ">>> システムパッケージ更新中..."
sudo apt-get update -y
sudo apt-get upgrade -y

# ── 必要なシステムパッケージのインストール ─────────────────────────────
echo ""
echo ">>> システム依存パッケージインストール中..."
sudo apt-get install -y \
    python3-pip \
    python3-venv \
    python3-opencv \
    libopencv-dev \
    net-tools \
    arp-scan \
    libatlas-base-dev \
    libhdf5-dev \
    git

# ── Python仮想環境の作成 ────────────────────────────────────────────
echo ""
echo ">>> Python仮想環境を作成中..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "仮想環境 'venv' を作成しました"
else
    echo "既存の仮想環境を使用します"
fi

# ── 仮想環境を有効化してライブラリインストール ──────────────────────────
echo ""
echo ">>> Pythonライブラリインストール中..."
source venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt

# ── データディレクトリの作成 ─────────────────────────────────────────
echo ""
echo ">>> データディレクトリを作成中..."
mkdir -p data/images
mkdir -p data/models

# ── RPi.GPIO の権限設定 ──────────────────────────────────────────────
echo ""
echo ">>> GPIO権限設定..."
if getent group gpio > /dev/null 2>&1; then
    sudo usermod -aG gpio "$USER"
    echo "ユーザー '$USER' を gpio グループに追加しました"
fi

# ── config.py の設定確認 ─────────────────────────────────────────────
echo ""
echo "=============================================="
echo " セットアップ完了！"
echo "=============================================="
echo ""
echo "【次のステップ】"
echo "1. config.py を編集して以下を設定してください:"
echo "   - LINE_CHANNEL_ACCESS_TOKEN"
echo "   - LINE_USER_ID"
echo "   - HOME_DEVICE_IPS (スマートフォンの固定IPアドレス)"
echo ""
echo "2. LINE接続テスト:"
echo "   source venv/bin/activate"
echo "   python -m notification.line_bot --test"
echo ""
echo "3. 在宅判定テスト:"
echo "   python -m presence.network_checker --debug"
echo ""
echo "4. システム起動:"
echo "   python main.py"
echo ""
echo "5. 自動起動設定 (systemd):"
echo "   sudo cp systemd/doorbell.service /etc/systemd/system/"
echo "   sudo systemctl enable doorbell"
echo "   sudo systemctl start doorbell"
echo ""
