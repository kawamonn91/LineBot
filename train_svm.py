"""
train_svm.py — 訪問者分類モデルの学習スクリプト（改良版）

【使用方法】
1. data/training/ の下の各カテゴリフォルダ（postal, yamato, sagawa, resident, other など）に
   それぞれの訪問者の画像を数枚〜数十枚配置します。
2. このスクリプトを実行すると、画像から特徴（色＋テクスチャ）を抽出し、
   SVM分類器を学習してモデルファイルを生成します。

実行コマンド:
    source venv/bin/activate
    python train_svm.py

【改良点】
- データ拡張: 水平反転・明度変化・軽微な回転で実効データ数を増加
- 学習/検証分割 (8:2) で汎化性能を確認
- 交差検証 (5-fold) でスコアの安定性を確認
"""

import os
import cv2
import numpy as np
import logging
from glob import glob

try:
    from sklearn.svm import SVC
    from sklearn.metrics import classification_report, confusion_matrix
    from sklearn.model_selection import train_test_split, cross_val_score
    from sklearn.preprocessing import LabelEncoder
    import joblib
except ImportError:
    print("❌ scikit-learn がインストールされていません。")
    print("   pip install scikit-learn を実行してください。")
    exit(1)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# 設定
TRAIN_DIR    = os.path.join(os.path.dirname(__file__), "data", "training")
MODEL_OUT    = os.path.join(os.path.dirname(__file__), "data", "models", "classifier_svm.pkl")
IMAGE_SIZE   = (64, 128)   # 特徴抽出用リサイズ (幅, 高さ)
AUGMENT      = True        # データ拡張を使用するか
TEST_SIZE    = 0.2         # 検証データ割合
CV_FOLDS     = 5           # 交差検証 fold 数（データが少なければ3に下げる）
RANDOM_SEED  = 42


# ────────────────────────────────────────────────────────────
# 特徴量抽出
# ────────────────────────────────────────────────────────────

def extract_features(img: np.ndarray) -> np.ndarray | None:
    """
    BGR画像から 色(HSV ヒストグラム) + テクスチャ(HOG) の特徴量を抽出する。
    上半身 (画像上部60%) のみを対象とすることで制服色に集中する。
    """
    if img is None or img.size == 0:
        return None

    # ① サイズ正規化
    img_resized = cv2.resize(img, IMAGE_SIZE)

    # ② 上半身（上部60%）を切り出して制服色に集中
    h = img_resized.shape[0]
    upper = img_resized[: int(h * 0.6), :]

    # ③ HSVヒストグラム特徴量 (上半身)
    hsv = cv2.cvtColor(upper, cv2.COLOR_BGR2HSV)
    hist_h = cv2.calcHist([hsv], [0], None, [16], [0, 180]).flatten()
    hist_s = cv2.calcHist([hsv], [1], None, [8],  [0, 256]).flatten()
    hist_v = cv2.calcHist([hsv], [2], None, [8],  [0, 256]).flatten()

    # ④ HOG（輪郭・テクスチャ）特徴量 (全体)
    gray = cv2.cvtColor(img_resized, cv2.COLOR_BGR2GRAY)
    hog = cv2.HOGDescriptor(IMAGE_SIZE, (16, 16), (8, 8), (8, 8), 9)
    hog_feat = hog.compute(gray).flatten()

    # ⑤ 結合して L2 正規化
    feat = np.concatenate([hist_h, hist_s, hist_v, hog_feat])
    norm = np.linalg.norm(feat)
    return feat / (norm + 1e-9)


def extract_features_from_path(img_path: str) -> np.ndarray | None:
    img = cv2.imread(img_path)
    return extract_features(img)


# ────────────────────────────────────────────────────────────
# データ拡張
# ────────────────────────────────────────────────────────────

def augment_image(img: np.ndarray) -> list[np.ndarray]:
    """
    1枚の画像から複数の拡張画像を生成する。
    Returns: 元画像を含む拡張画像のリスト
    """
    results = [img]

    # 水平反転
    results.append(cv2.flip(img, 1))

    # 明度を上げる (+30)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.int32)
    hsv[:, :, 2] = np.clip(hsv[:, :, 2] + 30, 0, 255)
    results.append(cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR))

    # 明度を下げる (-30)
    hsv2 = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.int32)
    hsv2[:, :, 2] = np.clip(hsv2[:, :, 2] - 30, 0, 255)
    results.append(cv2.cvtColor(hsv2.astype(np.uint8), cv2.COLOR_HSV2BGR))

    # 軽微な回転 (+5°)
    center = (img.shape[1] // 2, img.shape[0] // 2)
    M = cv2.getRotationMatrix2D(center, 5, 1.0)
    results.append(cv2.warpAffine(img, M, (img.shape[1], img.shape[0])))

    # 軽微な回転 (-5°)
    M2 = cv2.getRotationMatrix2D(center, -5, 1.0)
    results.append(cv2.warpAffine(img, M2, (img.shape[1], img.shape[0])))

    return results


# ────────────────────────────────────────────────────────────
# メイン学習処理
# ────────────────────────────────────────────────────────────

def load_dataset() -> tuple[list, list]:
    """
    data/training/ からカテゴリ別に画像を読み込み、
    (features, labels) のペアを返す。
    """
    if not os.path.exists(TRAIN_DIR):
        logger.error(f"学習用フォルダが見つかりません: {TRAIN_DIR}")
        return [], []

    classes = [
        d for d in os.listdir(TRAIN_DIR)
        if os.path.isdir(os.path.join(TRAIN_DIR, d))
    ]
    if not classes:
        logger.error("カテゴリフォルダが見つかりません")
        return [], []

    X, y = [], []
    total_original = 0

    logger.info("=" * 50)
    logger.info("データ読み込み・特徴量抽出")
    logger.info("=" * 50)

    for label in sorted(classes):
        img_paths = (
            glob(os.path.join(TRAIN_DIR, label, "*.jpg"))
            + glob(os.path.join(TRAIN_DIR, label, "*.png"))
            + glob(os.path.join(TRAIN_DIR, label, "*.jpeg"))
        )
        if not img_paths:
            logger.warning(f"  [{label}] 画像なし → スキップ")
            continue

        count_before = len(X)
        for path in img_paths:
            img = cv2.imread(path)
            if img is None:
                logger.warning(f"    読み込み失敗: {path}")
                continue

            images_to_process = augment_image(img) if AUGMENT else [img]
            for aug_img in images_to_process:
                feat = extract_features(aug_img)
                if feat is not None:
                    X.append(feat)
                    y.append(label)

        added = len(X) - count_before
        aug_ratio = added // len(img_paths) if img_paths else 1
        logger.info(
            f"  [{label}] 元画像: {len(img_paths)}枚 → "
            f"拡張後: {added}枚 (×{aug_ratio})"
        )
        total_original += len(img_paths)

    logger.info(f"\n合計: 元画像 {total_original}枚 → 拡張後 {len(X)}枚")
    return X, y


def main():
    # ── データ読み込み ────────────────────────────────────────
    X, y = load_dataset()
    if len(X) == 0:
        logger.error("学習可能な画像がありませんでした。")
        return

    X = np.array(X)
    y = np.array(y)
    classes = sorted(set(y))
    logger.info(f"クラス: {classes}")

    # ── 学習/検証 分割 ────────────────────────────────────────
    # データが少ない場合は stratify をサポートできないことがある
    try:
        X_train, X_val, y_train, y_val = train_test_split(
            X, y, test_size=TEST_SIZE, random_state=RANDOM_SEED, stratify=y
        )
    except ValueError:
        logger.warning("stratify に失敗（データが少ない）。シンプル分割に切り替え。")
        X_train, X_val, y_train, y_val = train_test_split(
            X, y, test_size=TEST_SIZE, random_state=RANDOM_SEED
        )

    logger.info(f"\n学習データ: {len(X_train)}件 / 検証データ: {len(X_val)}件")

    # ── SVM 学習 ─────────────────────────────────────────────
    logger.info("\nSVM学習中...")
    clf = SVC(kernel="rbf", probability=True, C=10, gamma="scale", random_state=RANDOM_SEED)
    clf.fit(X_train, y_train)

    # ── 交差検証 ─────────────────────────────────────────────
    n_folds = min(CV_FOLDS, min(np.bincount(LabelEncoder().fit_transform(y_train))))
    n_folds = max(2, n_folds)  # 最低2fold
    logger.info(f"\n交差検証 ({n_folds}-fold) 実行中...")
    cv_scores = cross_val_score(clf, X_train, y_train, cv=n_folds, scoring="f1_macro")
    logger.info(f"CV F1スコア: {cv_scores.round(3)}")
    logger.info(f"CV平均: {cv_scores.mean():.3f} ± {cv_scores.std():.3f}")

    # ── 検証データで評価 ─────────────────────────────────────
    logger.info("\n" + "=" * 50)
    logger.info("検証データでの評価結果")
    logger.info("=" * 50)
    y_pred = clf.predict(X_val)
    print(classification_report(y_val, y_pred, zero_division=0))

    # 混同行列
    cm = confusion_matrix(y_val, y_pred, labels=classes)
    logger.info("混同行列:")
    logger.info(f"  クラス順: {classes}")
    for i, row in enumerate(cm):
        logger.info(f"  {classes[i]:12s}: {row}")

    # ── 全データで再学習してモデル保存 ───────────────────────
    logger.info("\n全データで最終モデルを学習中...")
    clf_final = SVC(kernel="rbf", probability=True, C=10, gamma="scale", random_state=RANDOM_SEED)
    clf_final.fit(X, y)

    os.makedirs(os.path.dirname(MODEL_OUT), exist_ok=True)
    joblib.dump(clf_final, MODEL_OUT)
    logger.info(f"\n✅ 学習完了。モデルを保存しました: {MODEL_OUT}")
    logger.info("   新しい画像を追加したら、再度このスクリプトを実行してください。")
    logger.info(f"   学習クラス: {clf_final.classes_}")


if __name__ == "__main__":
    main()
