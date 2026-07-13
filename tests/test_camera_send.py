"""
test_camera_send.py — カメラ撮影 → LINE送信 統合テスト

使用方法:
    cd /home/toya/LineBot
    source venv/bin/activate
    python test_camera_send.py
"""

import logging
import os
import sys
import time

# ロギング設定
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("test_camera_send")

# パス設定
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from camera.camera_module import CameraModule
from notification.line_bot import _upload_image, _push_messages


def main():
    print("=" * 50)
    print("カメラ撮影 → LINE送信 テスト")
    print("=" * 50)

    # ── 1. 設定確認 ──────────────────────────────
    print("\n[1/5] 設定確認...")
    token = config.LINE_CHANNEL_ACCESS_TOKEN
    user_id = config.LINE_USER_ID
    if not token or token == "YOUR_CHANNEL_ACCESS_TOKEN_HERE":
        print("❌ LINE_CHANNEL_ACCESS_TOKEN が未設定です。.env を確認してください。")
        sys.exit(1)
    if not user_id:
        print("❌ LINE_USER_ID が未設定です。.env を確認してください。")
        sys.exit(1)
    print(f"   ✅ TOKEN: {token[:20]}...（末尾省略）")
    print(f"   ✅ USER_ID: {user_id}")

    # ── 2. カメラ起動 ──────────────────────────────
    print(f"\n[2/5] カメラ起動 (index={config.CAMERA_INDEX})...")
    cam = CameraModule()
    if not cam.start():
        print("❌ カメラを開けませんでした。接続を確認してください。")
        sys.exit(1)
    print("   ✅ カメラ起動成功")

    # ── 3. フレーム安定待ち & 撮影 ───────────────
    print("\n[3/5] フレーム取得中（3秒待機）...")
    time.sleep(3)  # カメラの自動露出が安定するまで待機

    frame = cam.get_frame()
    cam.stop()

    if frame is None:
        print("❌ フレームを取得できませんでした。")
        sys.exit(1)
    print(f"   ✅ フレーム取得成功: {frame.shape[1]}x{frame.shape[0]} px")

    # ── 4. 画像保存 ────────────────────────────────
    print("\n[4/5] テスト画像を保存中...")
    os.makedirs(config.IMAGE_DIR, exist_ok=True)
    save_path = os.path.join(config.IMAGE_DIR, "test_capture.jpg")

    import cv2
    success = cv2.imwrite(save_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not success:
        print(f"❌ 画像の保存に失敗しました: {save_path}")
        sys.exit(1)
    size_kb = os.path.getsize(save_path) / 1024
    print(f"   ✅ 保存完了: {save_path} ({size_kb:.1f} KB)")

    # ── 5. LINE にアップロード & 送信 ──────────────
    print("\n[5/5] LINE にアップロード & 送信中...")
    image_url = _upload_image(save_path)

    if image_url:
        print(f"   ✅ アップロード成功: {image_url}")

        messages = [
            {
                "type": "text",
                "text": (
                    "📷 カメラテスト送信\n"
                    "━━━━━━━━━━━━━━\n"
                    "玄関カメラから撮影した画像です。\n"
                    "LINE画像送信機能が正常に動作しています ✅"
                ),
            },
            {
                "type": "image",
                "originalContentUrl": image_url,
                "previewImageUrl": image_url,
            },
        ]
        result = _push_messages(messages)

        if result:
            print("\n✅ テスト成功！LINEに画像が送信されました。")
        else:
            print("\n❌ メッセージ送信に失敗しました。ログを確認してください。")
            sys.exit(1)
    else:
        print("\n❌ 画像アップロードに失敗しました。ログを確認してください。")
        sys.exit(1)

    print("=" * 50)


if __name__ == "__main__":
    main()
