import sys
import os
import datetime

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from notification.line_bot import send_visitor_notification
import config

def test_image_send():
    image_path = os.path.join(config.IMAGE_DIR, "test", "test_capture.jpg")
    
    if not os.path.exists(image_path):
        print(f"❌ 画像が見つかりません: {image_path}")
        print("先に test_camera.py を実行して写真を撮影してください。")
        sys.exit(1)
        
    print(f"画像 ({image_path}) をLINEに送信中...")
    
    # ダミーの訪問者データ
    dummy_visitor = {
        "category": "other",
        "duration_sec": 10,
        "has_delivery": False,
        "detected_at": datetime.datetime.now().isoformat()
    }
    
    result = send_visitor_notification(dummy_visitor, image_path=image_path)
    
    if result:
        print("✅ 画像付きメッセージの送信に成功しました！LINEを確認してください。")
    else:
        print("❌ 送信に失敗しました。")

if __name__ == '__main__':
    test_image_send()
