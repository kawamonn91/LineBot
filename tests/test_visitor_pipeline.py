"""
test_visitor_pipeline.py — 訪問者検知パイプライン 本番コードテスト

main.py の DoorbellSystem._on_visitor_detected() を
実際のカメラ映像を使って直接呼び出します。

PIRセンサー・GPIO は不要です。
YOLO検出 → 属性分類 → DB保存 → LINE通知（不在時のみ）まで
本番と同じコードパスを通ります。

使用方法:
    cd ~/LineBot
    source venv/bin/activate
    python test_visitor_pipeline.py [--frames N] [--duration SEC]
"""

import argparse
import logging
import logging.handlers
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config

# main.py と同じログ設定
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("test_pipeline")


def main():
    parser = argparse.ArgumentParser(description="訪問者検知パイプライン テスト")
    parser.add_argument("--frames", type=int, default=5,
                        help="撮影フレーム数（デフォルト: 5）")
    parser.add_argument("--duration", type=float, default=4.0,
                        help="想定滞在時間（秒）（デフォルト: 4.0）")
    args = parser.parse_args()

    print("=" * 60)
    print("  訪問者検知パイプライン テスト（本番コード使用）")
    print("=" * 60)
    print(f"  撮影フレーム数 : {args.frames}")
    print(f"  想定滞在時間  : {args.duration}秒")
    print()

    # ── 1. DB 初期化 ─────────────────────────────────────────
    print("[1/5] データベース初期化...")
    from database import db_manager
    os.makedirs(config.DATA_DIR, exist_ok=True)
    os.makedirs(config.IMAGE_DIR, exist_ok=True)
    os.makedirs(config.MODEL_DIR, exist_ok=True)
    db_manager.initialize_db()
    print("   ✅ DB 初期化完了")

    # ── 2. カメラ起動 & フレーム収集 ─────────────────────────
    print(f"\n[2/5] カメラ起動 (index={config.CAMERA_INDEX})...")
    from camera.camera_module import CameraModule
    cam = CameraModule()
    if not cam.start():
        print("❌ カメラを開けませんでした。")
        sys.exit(1)
    print("   ✅ カメラ起動成功")

    print(f"\n[3/5] {args.frames}フレーム撮影中（1秒間隔）...")
    time.sleep(2)  # 自動露出安定待ち
    frames = []
    for i in range(args.frames):
        frame = cam.get_frame()
        if frame is not None:
            frames.append(frame.copy())
            print(f"   フレーム {i+1}/{args.frames} 取得: {frame.shape[1]}x{frame.shape[0]}px")
        time.sleep(1.0)
    cam.stop()

    if not frames:
        print("❌ フレームを取得できませんでした。")
        sys.exit(1)
    print(f"   ✅ {len(frames)}フレーム取得完了")

    # ── 3. YOLO + 分類器 を main.py と同じ方法で初期化 ────────
    print("\n[4/5] YOLO & 分類器 初期化...")
    from detection.yolo_detector import YOLODetector
    from detection.classifier import VisitorClassifier

    detector = YOLODetector()
    try:
        detector.load()
        print("   ✅ YOLOモデルロード完了")
    except Exception as e:
        logger.warning(f"YOLOロード失敗: {e} → 物体検知なしで続行")
        detector = None

    classifier = VisitorClassifier()
    mode = "SVM" if classifier.using_svm else "色ヒストグラム"
    print(f"   ✅ 分類器準備完了 (モード: {mode})")

    # ── 4. _on_visitor_detected と同じ処理を実行 ─────────────
    print("\n[5/5] 本番パイプライン実行中...")
    print("      （main.py の _on_visitor_detected と同じ処理）")

    # --- YOLO 検出 ---
    best_result = None
    detections_for_classifier = []
    if detector and detector.is_loaded:
        best_result = detector.detect_from_frames(frames)
        for frame in frames:
            det = detector.detect_best_person(frame)
            detections_for_classifier.append(det)

    detected_count = sum(1 for d in detections_for_classifier if d is not None)
    print(f"   YOLO 検出: {detected_count}/{len(frames)} フレームで人物検出")
    if best_result:
        p = best_result["detection"]
        print(f"   最良検出: bbox={p['bbox']} 信頼度={p['confidence']:.3f}")

    # --- 属性分類 ---
    category, confidence = classifier.classify_from_frames(frames, detections_for_classifier)
    from database.models import CATEGORY_DISPLAY_NAMES
    display = CATEGORY_DISPLAY_NAMES.get(category, category)

    # --- 代表画像保存 ---
    image_path = None
    if best_result:
        import cv2
        from datetime import datetime
        session_dir = datetime.now().strftime("%Y%m%d_%H%M%S") + "_test"
        session_path = os.path.join(config.IMAGE_DIR, session_dir)
        os.makedirs(session_path, exist_ok=True)
        image_path = os.path.join(session_path, "representative.jpg")
        cv2.imwrite(image_path, best_result["frame"])
        print(f"   代表画像保存: {image_path}")

    # --- DB 保存 ---
    visitor_id = db_manager.insert_visitor(
        duration_sec=args.duration,
        category=category,
        confidence=confidence,
        image_path=image_path,
        has_delivery=False,
        user_was_home=True,   # テストなので在宅扱い（LINE通知スキップ）
    )
    print(f"   DB保存完了: visitor_id={visitor_id}")

    # ── 結果表示 ─────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  ✅ パイプライン完了")
    print(f"{'='*60}")
    print(f"  カテゴリ  : {display}")
    print(f"  信頼スコア: {confidence:.4f}  (閾値: {config.CLASSIFIER_SCORE_THRESHOLD})")
    print(f"  滞在時間  : {args.duration}秒")
    print(f"  フレーム数: {len(frames)}")
    print(f"  DB 保存   : visitor_id={visitor_id}")
    if image_path:
        print(f"  代表画像  : {image_path}")
    print()
    print("  ※ user_was_home=True のため LINE 通知はスキップしています")
    print("  ※ 不在時の LINE 通知もテストしたい場合:")
    print("     python -m notification.line_bot --test  でトークン確認後、")
    print("     スクリプト内の user_was_home=True を False に変更して再実行")
    print("=" * 60)

    # DB の最新レコードを確認
    print("\n📊 DB 最新5件:")
    import sqlite3
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, detected_at, duration_sec, category, confidence FROM visitors "
        "ORDER BY id DESC LIMIT 5"
    ).fetchall()
    conn.close()
    for r in rows:
        cat_disp = CATEGORY_DISPLAY_NAMES.get(r["category"], r["category"])
        print(f"   id={r['id']}  {r['detected_at']}  {r['duration_sec']:.1f}秒  "
              f"{cat_disp}  score={r['confidence']:.3f}")


if __name__ == "__main__":
    main()
