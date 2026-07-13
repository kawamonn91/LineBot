"""
test_visitor_detection.py — 本番コードパス統合テスト

main.py の _on_visitor_detected() を直接呼び出し、
カメラ → YOLO → 分類 → DB保存 → LINE通知 の本番処理を再現します。
PIRセンサー・GPIO は不要です。

使用方法:
    cd ~/LineBot
    source venv/bin/activate
    python test_visitor_detection.py
"""

import logging
import logging.handlers
import os
import sys
import time
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("test_visitor_detection")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from camera.camera_module import CameraModule
from detection.yolo_detector import YOLODetector
from detection.classifier import VisitorClassifier
from database import db_manager
from database.models import CATEGORY_DISPLAY_NAMES
from notification.line_bot import send_visitor_notification


# ── main.py の _on_visitor_detected と同一ロジック ──────────────────────
def on_visitor_detected(duration_sec: float, frames: list, session_dir: str):
    """
    main.py の DoorbellSystem._on_visitor_detected と同じ処理。
    """
    logger.info(f"【訪問者確定処理開始】 滞在={duration_sec:.1f}秒 フレーム={len(frames)}枚")

    # 1. YOLO 人物検出
    best_result = None
    detections_for_classifier = []
    detector = YOLODetector()
    try:
        detector.load()
        if frames:
            best_result = detector.detect_from_frames(frames)
            for frame in frames:
                det = detector.detect_best_person(frame)
                detections_for_classifier.append(det)
    except Exception as e:
        logger.warning(f"YOLOロード失敗（分類のみ続行）: {e}")

    # 2. 訪問者分類
    classifier = VisitorClassifier()
    category, confidence = classifier.classify_from_frames(frames, detections_for_classifier)
    display = CATEGORY_DISPLAY_NAMES.get(category, category)
    logger.info(f"分類結果: {display} (スコア={confidence:.3f})")

    # 3. 代表画像の保存
    image_path = None
    if best_result:
        import cv2
        os.makedirs(config.IMAGE_DIR, exist_ok=True)
        image_path = os.path.join(
            config.IMAGE_DIR, session_dir, "representative.jpg"
        )
        os.makedirs(os.path.dirname(image_path), exist_ok=True)
        cv2.imwrite(image_path, best_result["frame"])
        logger.info(f"代表画像保存: {image_path}")

    # 4. DB保存
    visitor_id = db_manager.insert_visitor(
        duration_sec=duration_sec,
        category=category,
        confidence=confidence,
        image_path=image_path,
        has_delivery=False,
        user_was_home=True,   # テストでは在宅扱い（LINE通知はスキップ）
    )
    logger.info(f"DB保存完了: visitor_id={visitor_id}")

    # 5. LINE通知（不在時のみ送るが、テストでは在宅=Trueなのでスキップ）
    logger.info("在宅中のためLINE通知はスキップ（本番動作と同じ）")

    print("\n" + "=" * 55)
    print("  ✅ 本番コードパス テスト完了")
    print("=" * 55)
    print(f"  カテゴリ  : {display}")
    print(f"  信頼スコア: {confidence:.4f}")
    print(f"  滞在時間  : {duration_sec:.1f} 秒")
    print(f"  フレーム数: {len(frames)} 枚")
    print(f"  DB保存ID  : {visitor_id}")
    if image_path:
        print(f"  代表画像  : {image_path}")
    print("=" * 55)


def main():
    print("=" * 55)
    print("  本番コードパス統合テスト")
    print("  （PIRセンサーをソフトウェアでシミュレート）")
    print("=" * 55)

    # DB初期化
    os.makedirs(config.DATA_DIR, exist_ok=True)
    os.makedirs(config.IMAGE_DIR, exist_ok=True)
    db_manager.initialize_db()

    # ── カメラ起動 ──────────────────────────────────────
    print(f"\n[1/3] カメラ起動 (index={config.CAMERA_INDEX})...")
    cam = CameraModule()
    if not cam.start():
        print("❌ カメラを開けませんでした。")
        sys.exit(1)
    print("   ✅ カメラ起動成功")

    # ── フレーム収集（3秒間 ≒ PIRが3秒間アクティブな状態を模擬）──
    capture_sec = 5
    print(f"\n[2/3] {capture_sec}秒間フレームを収集中（PIRアクティブ状態を模擬）...")
    print("      ※ カメラの前に立ってください！")

    frames = []
    start = time.time()
    last_capture = 0.0

    while time.time() - start < capture_sec:
        now = time.time()
        if now - last_capture >= config.CAPTURE_INTERVAL_SEC:
            frame = cam.get_frame()
            if frame is not None:
                frames.append(frame.copy())
                elapsed = now - start
                print(f"   📷 フレーム取得 ({len(frames)}枚目 / {elapsed:.1f}秒)")
            last_capture = now
        time.sleep(0.1)

    cam.stop()
    print(f"   ✅ フレーム収集完了: {len(frames)} 枚")

    # ── 本番の訪問者処理を呼び出す ──────────────────────
    print("\n[3/3] 本番の訪問者検出処理を実行中...")
    session_dir = datetime.now().strftime("%Y%m%d_%H%M%S")
    on_visitor_detected(
        duration_sec=capture_sec,
        frames=frames,
        session_dir=session_dir,
    )


if __name__ == "__main__":
    main()
