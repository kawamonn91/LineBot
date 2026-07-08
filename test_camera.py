import sys
import os
import time

# 上の階層のモジュールを読み込めるようにする
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from camera.camera_module import CameraModule
import config

def test_camera():
    print(f"カメラのテストを開始します... (使用カメラインデックス: {config.CAMERA_INDEX})")
    
    # カメラの初期化
    cam = CameraModule()
    
    # カメラ起動
    if not cam.start():
        print("❌ カメラの起動に失敗しました。接続や権限を確認してください。")
        sys.exit(1)
        
    print("✅ カメラが起動しました。ウォーミングアップのため2秒待機します...")
    time.sleep(2)
    
    # フレーム取得
    frame = cam.get_frame()
    if frame is None:
        print("❌ 画像の取得に失敗しました。")
    else:
        # 画像保存
        save_path = cam.save_frame(frame, subdirectory="test", filename="test_capture.jpg")
        if save_path:
            print(f"✅ 画像の取得と保存に成功しました！")
            print(f"   保存先: {save_path}")
        else:
            print("❌ 画像の保存に失敗しました。")
            
    # カメラ停止
    cam.stop()
    print("テストを終了します。")

if __name__ == '__main__':
    test_camera()
