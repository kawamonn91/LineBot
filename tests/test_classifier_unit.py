"""
tests/test_classifier_unit.py — VisitorClassifier 単体テスト

カメラ・GPU・SVMモデルなどのハードウェア依存なしに実行できます。

実行方法:
    cd ~/LineBot
    source venv/bin/activate
    pytest tests/test_classifier_unit.py -v
"""

import sys
import os
import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from detection.classifier import VisitorClassifier
from database.models import (
    CATEGORY_POSTAL, CATEGORY_YAMATO, CATEGORY_SAGAWA,
    CATEGORY_RESIDENT, CATEGORY_OTHER,
)


# ── ヘルパー ────────────────────────────────────────────────────────────

def make_hsv_image(h: int, s: int, v: int, size=(128, 256)) -> np.ndarray:
    """指定HSV値で均一に塗りつぶしたBGR画像を返す。"""
    import cv2
    hsv = np.full((size[1], size[0], 3), (h, s, v), dtype=np.uint8)
    return cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)


@pytest.fixture
def clf():
    """色ヒストグラムモードの VisitorClassifier（SVMなし）。"""
    return VisitorClassifier()


# ── テストクラス ────────────────────────────────────────────────────────

class TestClassifierInstantiation:
    """インスタンス生成のテスト"""

    def test_default_threshold(self, clf):
        import config
        assert clf.score_threshold == config.CLASSIFIER_SCORE_THRESHOLD

    def test_custom_threshold(self):
        clf = VisitorClassifier(score_threshold=0.5)
        assert clf.score_threshold == 0.5

    def test_no_svm_without_model_file(self, clf):
        # SVMモデルファイルがなければ色ヒストグラムモードになる
        assert clf.using_svm is False


class TestColorHistogramClassification:
    """色ヒストグラム分類のテスト（カメラ不要）"""

    def test_postal_color(self, clf):
        """水色画像は郵便局と判定される"""
        img = make_hsv_image(h=100, s=180, v=200)  # 水色シャツ
        category, score = clf.classify(img)
        assert category == CATEGORY_POSTAL
        assert score > 0

    def test_yamato_color(self, clf):
        """深緑画像はヤマト運輸と判定される"""
        img = make_hsv_image(h=55, s=120, v=70)  # 深緑
        category, score = clf.classify(img)
        assert category == CATEGORY_YAMATO
        assert score > 0

    def test_score_above_threshold_is_not_other(self, clf):
        """スコアが閾値以上ならotherにならない"""
        img = make_hsv_image(h=100, s=180, v=200)
        category, score = clf.classify(img)
        if score >= clf.score_threshold:
            assert category != CATEGORY_OTHER

    def test_score_below_threshold_is_other(self):
        """閾値を超高く設定するとotherになる"""
        clf_high = VisitorClassifier(score_threshold=0.999)
        img = make_hsv_image(h=0, s=50, v=128)  # スコアが低い色
        category, score = clf_high.classify(img)
        # スコアが閾値未満ならother
        if score < 0.999:
            assert category == CATEGORY_OTHER

    def test_returns_tuple_of_str_and_float(self, clf):
        """戻り値の型が (str, float) であること"""
        img = make_hsv_image(h=100, s=180, v=200)
        result = clf.classify(img)
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], str)
        assert isinstance(result[1], float)

    def test_score_is_normalized(self, clf):
        """スコアは 0.0〜1.0 の範囲内"""
        for h in [0, 55, 100, 115]:
            img = make_hsv_image(h=h, s=150, v=150)
            _, score = clf.classify(img)
            assert 0.0 <= score <= 1.0


class TestEdgeCases:
    """境界値・異常入力のテスト"""

    def test_none_input_returns_other(self, clf):
        category, score = clf.classify(None)
        assert category == CATEGORY_OTHER
        assert score == 0.0

    def test_empty_array_returns_other(self, clf):
        category, score = clf.classify(np.array([]))
        assert category == CATEGORY_OTHER
        assert score == 0.0

    def test_zero_size_image_returns_other(self, clf):
        category, score = clf.classify(np.zeros((0, 0, 3), dtype=np.uint8))
        assert category == CATEGORY_OTHER
        assert score == 0.0

    def test_tiny_1x1_image_does_not_crash(self, clf):
        """1x1 画像でも例外が発生しないこと"""
        category, score = clf.classify(np.zeros((1, 1, 3), dtype=np.uint8))
        assert isinstance(category, str)
        assert isinstance(score, float)


class TestClassifyFromFrames:
    """複数フレーム多数決テスト"""

    def test_majority_wins(self, clf):
        """3:1 の多数決で多い方が選ばれる"""
        postal_img = make_hsv_image(h=100, s=180, v=200)
        other_img  = make_hsv_image(h=0,   s=0,   v=100)

        frames     = [postal_img, postal_img, postal_img, other_img]
        detections = [None, None, None, None]

        category, score = clf.classify_from_frames(frames, detections)
        # 色ヒストグラムモードでは postal が多いので postal になるはず
        assert category == CATEGORY_POSTAL

    def test_empty_frames_returns_other(self, clf):
        """フレームが空でも例外が発生しないこと"""
        category, score = clf.classify_from_frames([], [])
        assert isinstance(category, str)
        assert isinstance(score, float)

    def test_detection_region_is_used_when_provided(self, clf):
        """detection に region がある場合はそちらを使う"""
        postal_img = make_hsv_image(h=100, s=180, v=200)
        # detection に region を渡す
        detection = {"region": postal_img, "bbox": [0, 0, 128, 256], "confidence": 0.9}
        category, score = clf.classify_from_frames([postal_img], [detection])
        assert category == CATEGORY_POSTAL

    def test_returns_tuple(self, clf):
        frames = [make_hsv_image(100, 180, 200)]
        result = clf.classify_from_frames(frames, [None])
        assert isinstance(result, tuple) and len(result) == 2


class TestVisitorTrackerWithMock:
    """VisitorTracker のロジックをカメラモックでテスト"""

    def test_short_stay_does_not_trigger_callback(self):
        """stay_threshold未満の滞在は訪問者コールバックが呼ばれない"""
        from unittest.mock import MagicMock
        from camera.visitor_tracker import VisitorTracker

        mock_camera = MagicMock()
        mock_camera.get_frame.return_value = make_hsv_image(100, 180, 200)

        called = []
        def on_detected(duration, frames, session_dir):
            called.append(duration)

        tracker = VisitorTracker(
            camera=mock_camera,
            on_visitor_detected=on_detected,
            stay_threshold_sec=3.0,
            end_timeout_sec=1.0,
            capture_interval_sec=0.5,
        )
        tracker.start()

        # PIR が0.5秒だけアクティブ（閾値3秒未満）
        tracker.notify_pir_state(True)
        import time; time.sleep(0.5)
        tracker.notify_pir_state(False)
        time.sleep(2.0)  # タイムアウト待ち

        tracker.stop()
        assert len(called) == 0, "短時間滞在では訪問者と判定されないはず"

    def test_long_stay_triggers_callback(self):
        """stay_threshold以上の滞在は訪問者コールバックが呼ばれる

        VisitorTracker の動作:
          notify_pir_state(True)  → セッション開始、_active=True、_last_active_time 更新
          monitor_loop が (now - _last_active_time) >= end_timeout を検知して finalize
          → stay_threshold を超えていれば on_visitor_detected が呼ばれる
        """
        import threading
        from unittest.mock import MagicMock
        from camera.visitor_tracker import VisitorTracker
        import time

        mock_camera = MagicMock()
        mock_camera.get_frame.return_value = make_hsv_image(100, 180, 200)

        event = threading.Event()
        called = []

        def on_detected(duration, frames, session_dir):
            called.append(duration)
            event.set()

        tracker = VisitorTracker(
            camera=mock_camera,
            on_visitor_detected=on_detected,
            stay_threshold_sec=1.0,
            end_timeout_sec=0.5,
            capture_interval_sec=0.3,
        )
        tracker.start()

        # PIRをTrueにしてセッション開始、更新を止めることでend_timeoutが経過する
        tracker.notify_pir_state(True)
        time.sleep(1.5)   # stay_threshold(1.0秒)を超える
        # ここから更新しない → end_timeout(0.5秒)後にmonitor_loopがfinalize

        fired = event.wait(timeout=5.0)   # 最大5秒待つ
        tracker.stop()

        assert fired, "タイムアウト: コールバックが5秒以内に呼ばれませんでした"
        assert len(called) == 1, "コールバックが1回呼ばれるはず"
        assert called[0] >= 1.0
