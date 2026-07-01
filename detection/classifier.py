"""
detection/classifier.py — 訪問者分類モジュール

【分類ロジック（優先順位）】
1. SVMモデル (data/models/classifier_svm.pkl) が存在する場合 → SVM で分類
2. pkl が存在しない場合 → 色ヒストグラムベースの分類にフォールバック

【SVMモデルの学習方法】
  Google Colab: train_on_colab.ipynb を実行
  ローカル:     python train_svm.py を実行
  → 生成された classifier_svm.pkl を data/models/ に配置して main.py を再起動

【精度について】
色ベース分類は照明環境・カメラ品質・制服の見え方に影響されます。
SVMモデルを学習させることで精度が向上します。
"""

import cv2
import logging
import numpy as np
import os
from typing import Optional

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from database.models import (
    CATEGORY_POSTAL, CATEGORY_YAMATO, CATEGORY_SAGAWA,
    CATEGORY_RESIDENT, CATEGORY_OTHER
)

logger = logging.getLogger(__name__)

# SVMモデルのパス
SVM_MODEL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "models", "classifier_svm.pkl"
)


class VisitorClassifier:
    """
    訪問者分類クラス。

    SVMモデル (classifier_svm.pkl) が存在する場合はSVMで分類。
    存在しない場合は色ヒストグラムベースの分類にフォールバック。

    使用方法:
        classifier = VisitorClassifier()
        category, confidence = classifier.classify(person_region)
    """

    # 各カテゴリの色範囲定義を config.py から動的に生成
    # (config.py が唯一の真実のソース)
    COLOR_PROFILES = {
        CATEGORY_POSTAL: [
            {"lower": np.array(r["lower"]), "upper": np.array(r["upper"])}
            for r in config.POSTAL_COLOR_RANGES
        ],
        CATEGORY_YAMATO: [
            {"lower": np.array(r["lower"]), "upper": np.array(r["upper"])}
            for r in config.YAMATO_COLOR_RANGES
        ],
        CATEGORY_SAGAWA: [
            {"lower": np.array(r["lower"]), "upper": np.array(r["upper"])}
            for r in config.SAGAWA_COLOR_RANGES
        ],
    }

    # 特徴抽出パラメータ（train_svm.py と統一する）
    _IMAGE_SIZE = (64, 128)  # (幅, 高さ)

    def __init__(self, score_threshold: float = None):
        """
        Args:
            score_threshold: 色ヒストグラム分類の閾値（SVM使用時は無関係）
        """
        self.score_threshold = score_threshold or config.CLASSIFIER_SCORE_THRESHOLD
        self._svm = None
        self._svm_loaded = False
        self._try_load_svm()

    # ----------------------------------------------------------------
    # SVM モデル
    # ----------------------------------------------------------------

    def _try_load_svm(self):
        """SVMモデルをロードする。失敗しても続行（色ヒストグラムにフォールバック）。"""
        if not os.path.exists(SVM_MODEL_PATH):
            logger.info(
                f"SVMモデルが見つかりません ({SVM_MODEL_PATH})。"
                "色ヒストグラム分類モードで動作します。"
            )
            return
        try:
            import joblib
            self._svm = joblib.load(SVM_MODEL_PATH)
            self._svm_loaded = True
            logger.info(
                f"✅ SVMモデルをロードしました: {SVM_MODEL_PATH} "
                f"(クラス: {list(self._svm.classes_)})"
            )
        except Exception as e:
            logger.warning(f"SVMモデルのロードに失敗しました: {e}。色ヒストグラムにフォールバック。")

    @property
    def using_svm(self) -> bool:
        """SVMモデルを使用中かどうか。"""
        return self._svm_loaded

    def _extract_features(self, img: np.ndarray) -> Optional[np.ndarray]:
        """
        BGR画像から HOG + HSVヒストグラム特徴量を抽出する。
        train_svm.py / train_on_colab.ipynb と同じロジックを使用する。
        """
        if img is None or img.size == 0:
            return None
        try:
            img_resized = cv2.resize(img, self._IMAGE_SIZE)

            # 上半身（上部60%）に集中して制服色を捉える
            h = img_resized.shape[0]
            upper = img_resized[: int(h * 0.6), :]

            hsv = cv2.cvtColor(upper, cv2.COLOR_BGR2HSV)
            hist_h = cv2.calcHist([hsv], [0], None, [16], [0, 180]).flatten()
            hist_s = cv2.calcHist([hsv], [1], None, [8],  [0, 256]).flatten()
            hist_v = cv2.calcHist([hsv], [2], None, [8],  [0, 256]).flatten()

            gray = cv2.cvtColor(img_resized, cv2.COLOR_BGR2GRAY)
            hog = cv2.HOGDescriptor(self._IMAGE_SIZE, (16, 16), (8, 8), (8, 8), 9)
            hog_feat = hog.compute(gray).flatten()

            feat = np.concatenate([hist_h, hist_s, hist_v, hog_feat])
            norm = np.linalg.norm(feat)
            return feat / (norm + 1e-9)
        except Exception as e:
            logger.debug(f"特徴量抽出エラー: {e}")
            return None

    # ----------------------------------------------------------------
    # SVM ベースの分類
    # ----------------------------------------------------------------

    def _classify_with_svm(self, person_region: np.ndarray) -> tuple[str, float]:
        """SVM モデルで分類する。"""
        feat = self._extract_features(person_region)
        if feat is None:
            return CATEGORY_OTHER, 0.0
        try:
            feat_2d = feat.reshape(1, -1)
            category = self._svm.predict(feat_2d)[0]
            proba = self._svm.predict_proba(feat_2d)[0]
            confidence = float(max(proba))
            logger.debug(f"SVM分類結果: {category} (信頼度={confidence:.3f})")
            return category, confidence
        except Exception as e:
            logger.warning(f"SVM推論エラー: {e}")
            return CATEGORY_OTHER, 0.0

    # ----------------------------------------------------------------
    # 色ヒストグラムベースの分類（フォールバック）
    # ----------------------------------------------------------------

    def classify(self, person_region: np.ndarray) -> tuple[str, float]:
        """
        人物画像領域を分類します。
        SVMモデルが利用可能ならSVMを、なければ色ヒストグラムを使用します。

        Args:
            person_region: BGR形式の人物切り抜き画像

        Returns:
            (カテゴリ文字列, 信頼スコア 0.0-1.0)
        """
        if person_region is None or person_region.size == 0:
            return CATEGORY_OTHER, 0.0

        if self._svm_loaded:
            return self._classify_with_svm(person_region)

        # フォールバック: 色ヒストグラム分類
        return self._classify_with_color_histogram(person_region)

    def _classify_with_color_histogram(
        self, person_region: np.ndarray
    ) -> tuple[str, float]:
        """色ヒストグラムベースで分類する（SVMがない場合のフォールバック）。"""
        # 上半身（画像上部60%）に絞って制服色を分析
        h = person_region.shape[0]
        upper_body = person_region[: int(h * 0.6), :]

        if upper_body.size == 0:
            return CATEGORY_OTHER, 0.0

        hsv = cv2.cvtColor(upper_body, cv2.COLOR_BGR2HSV)
        total_pixels = upper_body.shape[0] * upper_body.shape[1]

        if total_pixels == 0:
            return CATEGORY_OTHER, 0.0

        scores: dict[str, float] = {}
        for category, ranges in self.COLOR_PROFILES.items():
            mask = np.zeros(hsv.shape[:2], dtype=np.uint8)
            for color_range in ranges:
                m = cv2.inRange(hsv, color_range["lower"], color_range["upper"])
                mask = cv2.bitwise_or(mask, m)
            matched_pixels = cv2.countNonZero(mask)
            scores[category] = matched_pixels / total_pixels

        logger.debug(f"色ヒストグラム分類スコア: {scores}")

        best_category = max(scores, key=scores.get)
        best_score = scores[best_category]

        if best_score < self.score_threshold:
            return CATEGORY_OTHER, best_score

        return best_category, best_score

    # ----------------------------------------------------------------
    # 複数フレームの統合
    # ----------------------------------------------------------------

    def classify_from_frames(
        self, frames: list[np.ndarray], detections: list[Optional[dict]]
    ) -> tuple[str, float]:
        """
        複数フレームの分類結果を多数決で統合します。

        Args:
            frames: フレームリスト
            detections: 各フレームのYOLO検出結果リスト（Noneの場合はフレーム全体を使用）

        Returns:
            (カテゴリ文字列, 平均信頼スコア)
        """
        votes: dict[str, list[float]] = {
            CATEGORY_POSTAL: [],
            CATEGORY_YAMATO: [],
            CATEGORY_SAGAWA: [],
            CATEGORY_RESIDENT: [],
            CATEGORY_OTHER: [],
        }

        for frame, detection in zip(frames, detections):
            if detection and "region" in detection:
                region = detection["region"]
            else:
                region = frame  # 検出なしの場合はフレーム全体

            category, score = self.classify(region)
            votes[category].append(score)

        # 各カテゴリの平均スコアで決定
        avg_scores = {
            cat: (sum(v) / len(v) if v else 0.0)
            for cat, v in votes.items()
        }

        best_category = max(avg_scores, key=avg_scores.get)
        best_score = avg_scores[best_category]

        mode = "SVM" if self._svm_loaded else "色ヒストグラム"
        logger.info(
            f"訪問者分類結果 [{mode}]: {best_category} (スコア={best_score:.3f})"
        )
        return best_category, best_score
