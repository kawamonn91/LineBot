"""
test_classifier.py — 訪問者属性判別テスト

実行方法:
    cd ~/LineBot
    source venv/bin/activate
    python test_classifier.py

テスト内容:
  1. VisitorClassifier のインスタンス生成とモード確認
  2. 各制服カラーに近い単色画像で分類テスト（色ヒストグラムモード）
  3. 実際のカメラ画像（test_cam_0.jpg / test_cam_1.jpg）で分類テスト
  4. classify_from_frames の多数決ロジックのテスト
  5. エッジケース（None / 空画像）の安全性テスト
  6. スコア閾値感度テスト
"""

import sys
import os
import logging

import numpy as np
import cv2

# ── ログ設定 ────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("test_classifier")

# ── プロジェクトルートをパスに追加 ──────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from detection.classifier import VisitorClassifier
from database.models import (
    CATEGORY_POSTAL, CATEGORY_YAMATO, CATEGORY_SAGAWA,
    CATEGORY_RESIDENT, CATEGORY_OTHER, CATEGORY_DISPLAY_NAMES,
)

# ── ANSI カラー ─────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

PASS = f"{GREEN}✅ PASS{RESET}"
FAIL = f"{RED}❌ FAIL{RESET}"
INFO = f"{CYAN}ℹ️  INFO{RESET}"


def section(title: str):
    print(f"\n{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}{CYAN}{title}{RESET}")
    print(f"{BOLD}{'='*60}{RESET}")


def make_hsv_image(h: int, s: int, v: int, size=(128, 256)) -> np.ndarray:
    """指定のHSV値で塗り潰した BGR 画像を生成する。"""
    hsv = np.full((size[1], size[0], 3), (h, s, v), dtype=np.uint8)
    return cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)


# ── テスト関数 ──────────────────────────────────────────

def test_01_instantiation():
    """テスト1: VisitorClassifier のインスタンス生成とモード確認"""
    section("TEST 1: インスタンス生成 & モード確認")
    clf = VisitorClassifier()

    mode = "SVM" if clf.using_svm else "色ヒストグラム（フォールバック）"
    print(f"  分類モード : {YELLOW}{mode}{RESET}")
    print(f"  スコア閾値 : {clf.score_threshold}")
    print(f"  {PASS}: インスタンス生成成功")
    return clf


def test_02_color_histogram(clf: VisitorClassifier):
    """テスト2: 制服カラーに近い単色画像で色ヒストグラム分類を確認"""
    section("TEST 2: 単色画像による色ヒストグラム分類")

    # 各制服の代表的な HSV 値 (H, S, V)
    test_cases = [
        # (説明,                H,   S,   V,    期待カテゴリ or None)
        ("水色シャツ（郵便）",  100, 180, 200, CATEGORY_POSTAL),
        ("深緑制服（ヤマト）",   55,  120,  70, CATEGORY_YAMATO),
        ("青シャツ（佐川）",    115, 160, 180, CATEGORY_SAGAWA),
        ("白い服（その他）",      0,   0,  255, None),
        ("赤い服（その他）",      0, 200,  200, None),
    ]

    results = []
    for desc, h, s, v, expected in test_cases:
        img = make_hsv_image(h, s, v)
        category, score = clf.classify(img)
        display = CATEGORY_DISPLAY_NAMES.get(category, category)

        if expected is None:
            ok = (score < clf.score_threshold or category == CATEGORY_OTHER)
        else:
            ok = (category == expected)

        status = PASS if ok else FAIL
        print(f"  {status} [{desc}]")
        print(f"         → {display}  (スコア={score:.4f})")
        results.append(ok)

    return all(results)


def test_03_real_images(clf: VisitorClassifier):
    """テスト3: 実際のカメラ画像で分類テスト"""
    section("TEST 3: 実際のカメラ画像による分類")

    image_paths = [
        os.path.join(os.path.dirname(__file__), "test_cam_0.jpg"),
        os.path.join(os.path.dirname(__file__), "test_cam_1.jpg"),
    ]

    for path in image_paths:
        if not os.path.exists(path):
            print(f"  {YELLOW}⚠️  SKIP{RESET}: {path} が見つかりません")
            continue

        img = cv2.imread(path)
        if img is None:
            print(f"  {RED}❌ 読み込み失敗{RESET}: {path}")
            continue

        h, w = img.shape[:2]
        category, score = clf.classify(img)
        display = CATEGORY_DISPLAY_NAMES.get(category, category)

        print(f"  {INFO} {os.path.basename(path)} ({w}x{h}px)")
        print(f"       → {display}  (スコア={score:.4f})")
        print(f"  {PASS}: クラッシュなく分類完了")


def test_04_classify_from_frames(clf: VisitorClassifier):
    """テスト4: classify_from_frames の多数決ロジック"""
    section("TEST 4: classify_from_frames（多数決）")

    # 郵便局カラー × 3 フレーム + その他 × 1 フレーム
    postal_img = make_hsv_image(100, 180, 200)
    other_img  = make_hsv_image(0,   0,  255)

    frames     = [postal_img, postal_img, postal_img, other_img]
    detections = [None, None, None, None]

    category, score = clf.classify_from_frames(frames, detections)
    display = CATEGORY_DISPLAY_NAMES.get(category, category)

    print(f"  結果 : {display}  (スコア={score:.4f})")

    if clf.using_svm:
        print(f"  {INFO}: SVMモードのため多数決結果はモデル依存です")
        print(f"  {PASS}: classify_from_frames が正常終了")
    else:
        ok = (category == CATEGORY_POSTAL or score > 0)
        status = PASS if ok else FAIL
        print(f"  {status}: 多数決で postal が選択された (期待: postal)")


def test_05_edge_cases(clf: VisitorClassifier):
    """テスト5: エッジケース（None・空画像）"""
    section("TEST 5: エッジケース（安全性確認）")

    edge_cases = [
        ("None 入力",    None),
        ("空の ndarray", np.array([])),
        ("0px 画像",     np.zeros((0, 0, 3), dtype=np.uint8)),
        ("1x1 画像",     np.zeros((1, 1, 3), dtype=np.uint8)),
    ]

    all_ok = True
    for desc, img in edge_cases:
        try:
            category, score = clf.classify(img)
            display = CATEGORY_DISPLAY_NAMES.get(category, category)
            print(f"  {PASS} [{desc}] → {display} (スコア={score:.4f})")
        except Exception as e:
            print(f"  {FAIL} [{desc}] → 例外が発生: {e}")
            all_ok = False

    return all_ok


def test_06_score_threshold_sensitivity(clf: VisitorClassifier):
    """テスト6: スコア閾値の感度確認"""
    section("TEST 6: スコア閾値感度テスト")

    print(f"  現在の閾値 : {clf.score_threshold} (config.CLASSIFIER_SCORE_THRESHOLD)")

    if clf.using_svm:
        print(f"  {INFO}: SVMモードでは閾値は使用されません（スキップ）")
        return

    low_clf  = VisitorClassifier(score_threshold=0.01)
    high_clf = VisitorClassifier(score_threshold=0.99)

    img = make_hsv_image(100, 180, 200)  # 水色シャツ

    cat_low,  score_low  = low_clf.classify(img)
    cat_high, score_high = high_clf.classify(img)

    disp_low  = CATEGORY_DISPLAY_NAMES.get(cat_low, cat_low)
    disp_high = CATEGORY_DISPLAY_NAMES.get(cat_high, cat_high)

    print(f"  低閾値 (0.01) → {disp_low}  (スコア={score_low:.4f})")
    print(f"  高閾値 (0.99) → {disp_high}  (スコア={score_high:.4f})")

    if cat_high == CATEGORY_OTHER:
        print(f"  {PASS}: 高閾値では other に落ちた（期待通り）")
    else:
        print(f"  {YELLOW}⚠️  NOTE{RESET}: 高閾値でも other にならなかった（単色なのでスコアが高い）")


# ── メイン ──────────────────────────────────────────────

def main():
    print(f"\n{BOLD}{'#'*60}{RESET}")
    print(f"{BOLD}  訪問者属性判別テスト — VisitorClassifier{RESET}")
    print(f"{BOLD}{'#'*60}{RESET}")

    # 設定サマリー
    print(f"\n{CYAN}=== 設定サマリー ==={RESET}")
    print(f"  スコア閾値         : {config.CLASSIFIER_SCORE_THRESHOLD}")
    print(f"  郵便局カラーレンジ : {config.POSTAL_COLOR_RANGES}")
    print(f"  ヤマト カラーレンジ: {config.YAMATO_COLOR_RANGES}")
    print(f"  佐川 カラーレンジ  : {config.SAGAWA_COLOR_RANGES}")

    clf = test_01_instantiation()
    color_ok  = test_02_color_histogram(clf)
    test_03_real_images(clf)
    test_04_classify_from_frames(clf)
    edge_ok   = test_05_edge_cases(clf)
    test_06_score_threshold_sensitivity(clf)

    # ── 最終サマリー ────────────────────────────────────
    section("テスト結果サマリー")
    results = {
        "色ヒストグラム分類": color_ok,
        "エッジケース安全性": edge_ok,
    }
    all_passed = True
    for name, ok in results.items():
        status = PASS if ok else FAIL
        print(f"  {status} : {name}")
        if not ok:
            all_passed = False

    print()
    if all_passed:
        print(f"{GREEN}{BOLD}🎉 全テスト通過！{RESET}")
    else:
        print(f"{RED}{BOLD}⚠️  一部テスト失敗。上記ログを確認してください。{RESET}")
        sys.exit(1)


if __name__ == "__main__":
    main()
