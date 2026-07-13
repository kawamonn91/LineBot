"""
camera/camera_module.py — USBカメラ制御モジュール
OpenCVを使ってUSBカメラからフレームを取得します。
"""

import cv2
import logging
import os
import time
import threading
from datetime import datetime
from typing import Optional
import numpy as np

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

logger = logging.getLogger(__name__)


class CameraModule:
    """
    USBカメラ制御クラス。
    スレッドセーフなフレーム取得と画像保存機能を提供します。

    使用方法:
        cam = CameraModule()
        cam.start()
        frame = cam.get_frame()
        path = cam.save_frame(frame)
        cam.stop()
    """

    def __init__(
        self,
        camera_index: int | str = None,
        width: int = None,
        height: int = None,
        fps: int = None,
    ):
        self.camera_index = camera_index or config.CAMERA_INDEX
        self.width = width or config.CAMERA_WIDTH
        self.height = height or config.CAMERA_HEIGHT
        self.fps = fps or config.CAMERA_FPS

        self._cap: Optional[cv2.VideoCapture] = None
        self._lock = threading.Lock()
        self._latest_frame: Optional[np.ndarray] = None
        self._running = False
        self._capture_thread: Optional[threading.Thread] = None

    def start(self) -> bool:
        """カメラを起動してフレーム取得ループを開始します。"""
        if self._running:
            return True

        # 文字列パス（/dev/v4l/by-id/... など）はシンボリックリンクを解決する
        open_target = self.camera_index
        if isinstance(open_target, str):
            open_target = os.path.realpath(open_target)
            logger.debug(f"カメラパス解決: {self.camera_index} → {open_target}")

        self._cap = cv2.VideoCapture(open_target)
        if not self._cap.isOpened():
            logger.error(
                f"カメラを開けませんでした ({open_target})。"
                "接続を確認してください。"
            )
            return False

        # カメラパラメータ設定（エラーが出やすいためコメントアウトまたは緩める）
        # 一部のUSBカメラは解像度を強制設定すると内部でストリームが壊れ、映像が取得できなくなります。
        # 今回はカメラのデフォルト解像度をそのまま使用します。
        # self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        # self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        # self._cap.set(cv2.CAP_PROP_FPS, self.fps)

        self._running = True
        self._capture_thread = threading.Thread(
            target=self._capture_loop, name="CameraThread", daemon=True
        )
        self._capture_thread.start()
        logger.info(
            f"カメラ起動: {self.camera_index} "
            f"{self.width}x{self.height} @ {self.fps}fps"
        )
        return True

    def stop(self):
        """カメラを停止してリソースを解放します。"""
        self._running = False
        if self._capture_thread:
            self._capture_thread.join(timeout=3)
        if self._cap:
            self._cap.release()
            self._cap = None
        logger.info("カメラ停止")

    def _capture_loop(self):
        """バックグラウンドでフレームを継続的に取得するループ。"""
        while self._running:
            if self._cap and self._cap.isOpened():
                ret, frame = self._cap.read()
                if ret:
                    with self._lock:
                        self._latest_frame = frame
                else:
                    logger.warning("フレーム取得失敗")
                    time.sleep(0.5)
            time.sleep(1.0 / self.fps)

    def get_frame(self) -> Optional[np.ndarray]:
        """最新のフレームを返します。未取得の場合はNoneを返します。"""
        with self._lock:
            if self._latest_frame is not None:
                return self._latest_frame.copy()
        return None

    def save_frame(
        self,
        frame: np.ndarray,
        subdirectory: str = "",
        filename: str = None,
    ) -> Optional[str]:
        """
        フレームをJPEG画像として保存します。

        Args:
            frame: 保存するフレーム
            subdirectory: IMAGE_DIR 以下のサブディレクトリ名
            filename: ファイル名（省略時は日時から自動生成）

        Returns:
            保存したファイルの絶対パス。失敗時はNone。
        """
        try:
            save_dir = os.path.join(config.IMAGE_DIR, subdirectory)
            os.makedirs(save_dir, exist_ok=True)

            if filename is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                filename = f"visitor_{timestamp}.jpg"

            path = os.path.join(save_dir, filename)
            # JPEG品質85で保存（容量と品質のバランス）
            cv2.imwrite(path, frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            logger.debug(f"画像保存: {path}")
            return path

        except Exception as e:
            logger.error(f"画像保存エラー: {e}")
            return None

    def capture_burst(
        self, count: int = 3, interval_sec: float = 0.5
    ) -> list[np.ndarray]:
        """
        複数フレームを連続取得して返します（訪問者代表画像の取得に使用）。

        Args:
            count: 取得フレーム数
            interval_sec: フレーム間隔（秒）

        Returns:
            フレームリスト
        """
        frames = []
        for _ in range(count):
            frame = self.get_frame()
            if frame is not None:
                frames.append(frame)
            time.sleep(interval_sec)
        return frames

    @property
    def is_running(self) -> bool:
        """カメラが動作中かどうかを返します。"""
        return self._running
