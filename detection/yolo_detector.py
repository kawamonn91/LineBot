"""
detection/yolo_detector.py — YOLOv8人物検出モジュール
ultralytics YOLOv8nを使って画像から人物を検出します。
"""

import logging
import os
import time
from typing import Optional
import numpy as np

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

logger = logging.getLogger(__name__)


class YOLODetector:
    """
    YOLOv8nによる人物検出クラス。
    モデルは初回起動時に自動ダウンロードされます（約6MB）。

    使用方法:
        detector = YOLODetector()
        detector.load()
        persons = detector.detect_persons(frame)
        # persons: [{"bbox": [x1,y1,x2,y2], "confidence": 0.85}, ...]
    """

    def __init__(
        self,
        model_path: str = None,
        confidence_threshold: float = None,
        inference_width: int = None,
    ):
        self.model_path = model_path or config.YOLO_MODEL_PATH
        self.confidence_threshold = confidence_threshold or config.YOLO_CONFIDENCE_THRESHOLD
        self.inference_width = inference_width or config.YOLO_INFERENCE_WIDTH
        self._model = None

    def load(self):
        """YOLOv8モデルをロードします（初回は自動ダウンロード）。"""
        try:
            from ultralytics import YOLO
            os.makedirs(os.path.dirname(self.model_path), exist_ok=True)
            logger.info(f"YOLOv8モデルをロード中: {self.model_path}")
            t0 = time.time()
            self._model = YOLO(self.model_path)
            logger.info(f"YOLOv8モデルロード完了 ({time.time() - t0:.1f}秒)")
        except ImportError:
            logger.error(
                "ultralytics がインストールされていません。"
                "`pip install ultralytics` を実行してください。"
            )
            raise
        except Exception as e:
            logger.error(f"YOLOv8モデルロードエラー: {e}")
            raise

    def detect_persons(self, frame: np.ndarray) -> list[dict]:
        """
        フレームから人物を検出します。

        Args:
            frame: BGR形式のOpenCVフレーム

        Returns:
            検出された人物のリスト。各要素は:
            {
                "bbox": [x1, y1, x2, y2],  # ピクセル座標
                "confidence": float,         # 信頼スコア (0.0-1.0)
                "bbox_normalized": [x1n, y1n, x2n, y2n],  # 正規化座標
            }
        """
        if self._model is None:
            logger.warning("モデル未ロード。load()を先に呼び出してください。")
            return []

        try:
            # 推論サイズにリサイズ（速度最適化）
            results = self._model.predict(
                source=frame,
                imgsz=self.inference_width,
                conf=self.confidence_threshold,
                classes=[config.YOLO_PERSON_CLASS_ID],  # personクラスのみ
                verbose=False,
            )

            persons = []
            h, w = frame.shape[:2]

            for result in results:
                for box in result.boxes:
                    x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                    conf = float(box.conf[0])

                    # 人物領域をクロップ
                    person_region = frame[
                        max(0, y1):min(h, y2),
                        max(0, x1):min(w, x2)
                    ]

                    persons.append({
                        "bbox": [x1, y1, x2, y2],
                        "confidence": conf,
                        "bbox_normalized": [x1/w, y1/h, x2/w, y2/h],
                        "region": person_region,
                    })

            logger.debug(f"人物検出: {len(persons)}人")
            return persons

        except Exception as e:
            logger.error(f"YOLO推論エラー: {e}")
            return []

    def detect_best_person(self, frame: np.ndarray) -> Optional[dict]:
        """
        フレームから最も信頼度の高い人物を1名検出します。

        Returns:
            最も信頼度の高い人物の検出情報。検出なしの場合はNone。
        """
        persons = self.detect_persons(frame)
        if not persons:
            return None
        return max(persons, key=lambda p: p["confidence"])

    def detect_from_frames(self, frames: list[np.ndarray]) -> Optional[dict]:
        """
        複数フレームから最も信頼度の高い検出結果を返します。
        訪問者セッション中に蓄積したフレームに使用します。

        Args:
            frames: フレームのリスト

        Returns:
            最も良い検出結果 (frame, detection) のタプル。なければNone。
        """
        best_result = None
        best_confidence = 0.0

        for frame in frames:
            person = self.detect_best_person(frame)
            if person and person["confidence"] > best_confidence:
                best_confidence = person["confidence"]
                best_result = {"frame": frame, "detection": person}

        return best_result

    @property
    def is_loaded(self) -> bool:
        """モデルがロード済みかどうかを返します。"""
        return self._model is not None
