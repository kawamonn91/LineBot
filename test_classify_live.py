"""
test_classify_live.py — カメラ撮影 → 訪問者属性判別 テスト

実際のカメラで撮影し、YOLO人物検出 + 属性分類（VisitorClassifier）を実行します。

使用方法:
    cd ~/LineBot
    source venv/bin/activate
    python test_classify_live.py
"""

import logging
import os
import sys
import time

import cv2

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from camera.camera_module import CameraModule
from detection.yolo_detector import YOLODetector
from detection.classifier import VisitorClassifier
from database.models import CATEGORY_DISPLAY_NAMES


def main():
    print("=" * 55)
    print("  カメラ撮影 → 属性判別テスト")
    print("=" * 55)

    # ── 1. カメラ起動 ──────────────────────────────────────
    print(f"\n[1/4] カメラ起動 (index={config.CAMERA_INDEX})...")
    cam = CameraModule()
    if not cam.start():
        print("❌ カメラを開けませんでした。")
        print("   └ config.py の CAMERA_INDEX を確認してください。")
        sys.exit(1)
    print("   ✅ カメラ起動成功")

    # ── 2. フレーム取得（3秒待って自動露出を安定させる）────
    print("\n[2/4] フレーム取得中（3秒待機）...")
    time.sleep(3)
    frame = cam.get_frame()
    cam.stop()

    if frame is None:
        print("❌ フレームを取得できませんでした。")
        sys.exit(1)
    h, w = frame.shape[:2]
    print(f"   ✅ フレーム取得成功: {w}x{h} px")

    # 取得画像を保存
    os.makedirs(config.IMAGE_DIR, exist_ok=True)
    save_path = os.path.join(config.IMAGE_DIR, "classify_test_capture.jpg")
    cv2.imwrite(save_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    print(f"   📁 保存: {save_path}")

    # ── 3. YOLO 人物検出 ───────────────────────────────────
    print("\n[3/4] YOLO 人物検出...")
    detector = YOLODetector()
    try:
        detector.load()
    except Exception as e:
        print(f"   ⚠️  YOLOロード失敗: {e}")
        print("   └ フレーム全体で属性判別を続行します")
        detector = None

    persons = []
    best_detection = None
    if detector:
        persons = detector.detect_persons(frame)
        if persons:
            best_detection = max(persons, key=lambda p: p["confidence"])
            print(f"   ✅ 人物検出: {len(persons)} 人")
            for i, p in enumerate(persons, 1):
                x1, y1, x2, y2 = p["bbox"]
                print(f"      [{i}] bbox=({x1},{y1})-({x2},{y2})  信頼度={p['confidence']:.3f}")

            # 検出領域を赤枠で画像に描画して保存
            debug_frame = frame.copy()
            for p in persons:
                x1, y1, x2, y2 = p["bbox"]
                cv2.rectangle(debug_frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
            debug_path = os.path.join(config.IMAGE_DIR, "classify_test_yolo.jpg")
            cv2.imwrite(debug_path, debug_frame)
            print(f"   📁 YOLO検出結果画像: {debug_path}")
        else:
            print("   ⚠️  人物が検出されませんでした。")
            print("   └ フレーム全体で属性判別を続行します")

    # ── 4. 属性分類 ────────────────────────────────────────
    print("\n[4/4] 属性分類...")
    clf = VisitorClassifier()
    mode = "SVM" if clf.using_svm else "色ヒストグラム（フォールバック）"
    print(f"   分類モード: {mode}")

    # 検出された人物領域 or フレーム全体で分類
    if best_detection and "region" in best_detection:
        region = best_detection["region"]
        region_desc = "YOLO検出領域"
    else:
        region = frame
        region_desc = "フレーム全体"

    category, score = clf.classify(region)
    display = CATEGORY_DISPLAY_NAMES.get(category, category)

    print(f"\n{'='*55}")
    print(f"  判別結果 ({region_desc}使用)")
    print(f"{'='*55}")
    print(f"  カテゴリ : {display}")
    print(f"  スコア   : {score:.4f}  (閾値: {config.CLASSIFIER_SCORE_THRESHOLD})")
    if score < config.CLASSIFIER_SCORE_THRESHOLD:
        print("  ⚠️  スコアが閾値未満 → 「その他」として記録されます")

    print(f"\n  保存画像: {save_path}")
    if persons:
        print(f"  YOLO枠:  {debug_path}")
    print("=" * 55)


if __name__ == "__main__":
    main()
