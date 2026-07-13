"""
config.py — システム設定ファイル
すべての設定値をここで一元管理します。
機密情報（LINEトークン・IPアドレス等）は .env ファイルで管理してください。
"""

import os
from pathlib import Path

# .env ファイルを自動ロード（python-dotenv）
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=Path(__file__).parent / ".env")
except ImportError:
    pass  # dotenv が未インストールの場合は環境変数から直接読む

# ============================================================
# LINE Messaging API 設定
# LINE Developers コンソールから取得してください
# ============================================================
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_USER_ID = os.getenv("LINE_USER_ID", "")  # 通知先ユーザーID (Uxxxxxxxxxx...)

# ============================================================
# GPIO ピン設定 (BCM番号)
# DKRK100600 スターターキット + Raspberry Pi 5
# ============================================================
PIR_GPIO_PIN = 17       # HC-SR501 PIRセンサー出力ピン
MAILBOX_GPIO_PIN = 27   # SW-520D チルトスイッチ出力ピン（郵便受け）

# ============================================================
# USBカメラ設定
# ============================================================
CAMERA_INDEX = 0                # USBカメラのデバイスインデックス (BUFFALO BSWHD06M → /dev/video0)
CAMERA_WIDTH = 1280             # 撮影解像度 幅
CAMERA_HEIGHT = 720             # 撮影解像度 高さ
CAMERA_FPS = 10                 # フレームレート（処理軽量化のため低めに設定）
YOLO_INFERENCE_WIDTH = 640      # YOLOv8推論時のリサイズ幅

# ============================================================
# 訪問者検知パラメータ
# ============================================================
VISITOR_STAY_THRESHOLD_SEC = 3.0    # 訪問者として記録する最低滞在時間（秒）
VISITOR_END_TIMEOUT_SEC = 5.0       # PIR非検知後、訪問終了と判定するまでの時間（秒）
PIR_DEBOUNCE_SEC = 2.0              # PIRセンサーのデバウンス時間（秒）
CAPTURE_INTERVAL_SEC = 1.0          # 訪問中のフレームキャプチャ間隔（秒）

# ============================================================
# 在宅判定設定
# ============================================================
# スマートフォンのIPアドレスリスト
# .env の HOME_DEVICE_IPS にカンマ区切りで設定してください
# 例: HOME_DEVICE_IPS=192.168.1.100,192.168.1.101
_home_ips_raw = os.getenv("HOME_DEVICE_IPS", "")
HOME_DEVICE_IPS = [ip.strip() for ip in _home_ips_raw.split(",") if ip.strip()]
PRESENCE_CHECK_INTERVAL_SEC = 30    # 在宅チェック間隔（秒）
PRESENCE_ARP_TIMEOUT_SEC = 2        # ARPスキャンのタイムアウト（秒）

# Bluetooth 在宅判定（Wi-Fi非依存の代替手段）
# .env の HOME_BT_ADDRESSES にスマホの Bluetooth アドレスをカンマ区切りで設定
# 例: HOME_BT_ADDRESSES=AA:BB:CC:DD:EE:FF
_home_bt_raw = os.getenv("HOME_BT_ADDRESSES", "")
HOME_BT_ADDRESSES = [addr.strip() for addr in _home_bt_raw.split(",") if addr.strip()]
# True: Bluetooth checker を使用 / False: Wi-Fi (network) checker を使用
PRESENCE_USE_BLUETOOTH = os.getenv("PRESENCE_USE_BLUETOOTH", "false").lower() == "true"

# ============================================================
# データベース・ファイルパス
# ============================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "visitors.db")
IMAGE_DIR = os.path.join(DATA_DIR, "images")
MODEL_DIR = os.path.join(DATA_DIR, "models")
YOLO_MODEL_PATH = os.path.join(MODEL_DIR, "yolov8n.pt")  # 自動ダウンロード

# ============================================================
# YOLOv8 検知設定
# ============================================================
YOLO_CONFIDENCE_THRESHOLD = 0.5    # 検出信頼度の閾値
YOLO_PERSON_CLASS_ID = 0           # YOLOv8の "person" クラスID

# ============================================================
# 訪問者分類 — 色ヒストグラムベース設定
# HSV色空間で制服の色範囲を定義
# ※ 実際の制服画像を確認して設定した値
# ============================================================
# 郵便局（日本郵便）: 水色〜青系のシャツ + 紺ズボン
# (上半身の水色/青系の比率で判定)
POSTAL_COLOR_RANGES = [
    {"lower": [85, 50, 100],  "upper": [115, 255, 255]},  # 水色〜青（シャツ）
    {"lower": [100, 50, 50],  "upper": [130, 180, 150]},  # 濃紺（ズボン）
]
# ヤマト運輸: 深緑（ダークグリーン）の制服 + 黄色ライン
YAMATO_COLOR_RANGES = [
    {"lower": [35, 40, 20],   "upper": [85, 255, 130]},   # 深緑（メイン）
    {"lower": [20, 100, 150], "upper": [35, 255, 255]},   # 黄色ライン
]
# 佐川急便: 青系の制服（ネイビー〜ブルー）
# ※ 白ボーダーは「低彩度＝明るい色全般」にも一致してしまうため除外
SAGAWA_COLOR_RANGES = [
    {"lower": [100, 100, 60],  "upper": [125, 255, 255]},  # 青〜ネイビー（彩度を高くして絞り込む）
]
# 分類スコア閾値（この値以上で分類確定）
CLASSIFIER_SCORE_THRESHOLD = 0.12

# ============================================================
# スケジューラー設定
# ============================================================
DAILY_REPORT_TIME = "19:00"    # 日次レポート送信時刻

# ============================================================
# ログ設定
# ============================================================
LOG_LEVEL = "INFO"   # DEBUG / INFO / WARNING / ERROR
LOG_FILE = os.path.join(BASE_DIR, "doorbell.log")
# RotatingFileHandler設定（SD容量保護）
LOG_MAX_BYTES = 10 * 1024 * 1024   # 10MBごとにローテーション
LOG_BACKUP_COUNT = 3                # 最大30MB保持（doorbell.log + .1 + .2 + .3）

# ============================================================
# Google Drive 設定
# ============================================================
# サービスアカウントのJSONキーファイルのパス
# 例: /home/pi/linebot-service-account.json
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv(
    "GOOGLE_SERVICE_ACCOUNT_JSON",
    os.path.join(BASE_DIR, "service_account.json"),
)
# 画像アップロード先のGoogle DriveフォルダID
# フォルダを開き、URLに含まれる「1AbcXyz...」の文字列を設定
GOOGLE_DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")
# Google Drive内のサブフォルダ名（年月ごとにサブフォルダを作成する場合等）
GOOGLE_DRIVE_SUBFOLDER = os.getenv("GOOGLE_DRIVE_SUBFOLDER", "visitors")
# ローカルに画像を保持する日数（Driveアップロード成功後に削除）
IMAGE_LOCAL_RETENTION_DAYS = int(os.getenv("IMAGE_LOCAL_RETENTION_DAYS", "3"))
# Driveアップロードの最大リトライ回数
DRIVE_UPLOAD_MAX_RETRIES = 5
# Drive機能を有効にするか（Falseにするとローカル保存のみ）
DRIVE_UPLOAD_ENABLED = os.getenv("DRIVE_UPLOAD_ENABLED", "true").lower() == "true"
