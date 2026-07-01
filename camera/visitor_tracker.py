"""
camera/visitor_tracker.py — 訪問者滞在時間計測・記録
PIRセンサーのアクティブ状態を監視して3秒以上の滞在を訪問者として記録します。
"""

import logging
import time
import threading
import os
from datetime import datetime
from typing import Optional, Callable
import numpy as np

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from camera.camera_module import CameraModule

logger = logging.getLogger(__name__)


class VisitorTracker:
    """
    PIRセンサーのアクティブ状態を監視し、
    3秒以上の滞在を「訪問者」として記録するクラス。

    コールバック関数で検知イベントを通知します。
    """

    def __init__(
        self,
        camera: CameraModule,
        on_visitor_detected: Callable[[float, list, str], None],
        stay_threshold_sec: float = None,
        end_timeout_sec: float = None,
        capture_interval_sec: float = None,
    ):
        """
        Args:
            camera: CameraModuleインスタンス
            on_visitor_detected: 訪問者確定時のコールバック
                引数: (duration_sec: float, frames: list[ndarray], session_dir: str)
            stay_threshold_sec: 訪問者と判定する最低滞在時間（秒）
            end_timeout_sec: PIR非検知後に訪問終了とする待機時間（秒）
            capture_interval_sec: 滞在中のキャプチャ間隔（秒）
        """
        self.camera = camera
        self.on_visitor_detected = on_visitor_detected
        self.stay_threshold = stay_threshold_sec or config.VISITOR_STAY_THRESHOLD_SEC
        self.end_timeout = end_timeout_sec or config.VISITOR_END_TIMEOUT_SEC
        self.capture_interval = capture_interval_sec or config.CAPTURE_INTERVAL_SEC

        self._active = False           # PIRがアクティブかどうか
        self._session_start: Optional[float] = None
        self._last_active_time: Optional[float] = None
        self._captured_frames: list = []
        self._session_dir: str = ""
        self._lock = threading.Lock()
        self._running = False
        self._monitor_thread: Optional[threading.Thread] = None

    def start(self):
        """訪問者トラッカーを開始します。"""
        self._running = True
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop, name="VisitorTrackerThread", daemon=True
        )
        self._monitor_thread.start()
        logger.info("訪問者トラッカー開始")

    def stop(self):
        """訪問者トラッカーを停止します。"""
        self._running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
        logger.info("訪問者トラッカー停止")

    def notify_pir_state(self, active: bool):
        """
        PIRセンサーの状態変化を通知します。
        PIRSensor のコールバックから呼び出されます。

        Args:
            active: True=動き検知中, False=非検知
        """
        with self._lock:
            now = time.time()
            if active:
                if not self._active:
                    # 新しいセッション開始
                    self._start_session(now)
                self._active = True
                self._last_active_time = now
            else:
                # PIR非検知: タイムアウト判定はmonitor_loopで行う
                self._last_active_time = now if self._last_active_time is None else self._last_active_time

    def _start_session(self, now: float):
        """新しい訪問セッションを開始します。"""
        self._session_start = now
        self._captured_frames = []
        timestamp = datetime.fromtimestamp(now).strftime("%Y%m%d_%H%M%S")
        self._session_dir = timestamp
        logger.info(f"訪問セッション開始: {timestamp}")

    def _monitor_loop(self):
        """
        定期的に状態を確認し:
        - PIR非検知が end_timeout 秒続いた場合、訪問終了処理を行う
        - 訪問中はフレームをキャプチャする
        """
        last_capture_time = 0.0

        while self._running:
            try:
                with self._lock:
                    active = self._active
                    session_start = self._session_start
                    last_active = self._last_active_time

                now = time.time()

                if active and session_start is not None:
                    # 訪問中: フレームを定期的にキャプチャ
                    if now - last_capture_time >= self.capture_interval:
                        frame = self.camera.get_frame()
                        if frame is not None:
                            with self._lock:
                                self._captured_frames.append(frame.copy())
                        last_capture_time = now

                    # PIR非検知が end_timeout 秒続いたかチェック
                    if last_active is not None and (now - last_active) >= self.end_timeout:
                        self._finalize_session()

                elif not active and session_start is not None and last_active is not None:
                    # セッション中だがPIR非アクティブ → タイムアウト待ち
                    if (now - last_active) >= self.end_timeout:
                        self._finalize_session()

                time.sleep(0.2)

            except Exception as e:
                logger.error(f"訪問者トラッカーエラー: {e}")
                time.sleep(1)

    def _finalize_session(self):
        """訪問セッションを終了し、条件を満たせばコールバックを呼び出します。"""
        with self._lock:
            if self._session_start is None:
                return

            now = time.time()
            duration = now - self._session_start
            frames = list(self._captured_frames)
            session_dir = self._session_dir

            # セッションリセット
            self._active = False
            self._session_start = None
            self._last_active_time = None
            self._captured_frames = []
            self._session_dir = ""

        logger.info(f"訪問セッション終了: 滞在時間={duration:.1f}秒")

        if duration >= self.stay_threshold:
            logger.info(f"訪問者確定: {duration:.1f}秒滞在 フレーム数={len(frames)}")
            try:
                self.on_visitor_detected(duration, frames, session_dir)
            except Exception as e:
                logger.error(f"訪問者コールバックエラー: {e}")
        else:
            logger.info(f"短時間通過（{duration:.1f}秒）: 訪問者記録なし")
