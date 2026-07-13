"""
main.py — 玄関モニタリングシステム メインコントローラー

全モジュールを統括してシステムを起動します。
Ctrl+C または SIGTERM で安全に終了します。

起動方法:
    cd /path/to/LineBot
    source venv/bin/activate
    python main.py

バックグラウンド起動（systemd使用の場合はdoorbell.serviceを参照）:
    nohup python main.py > doorbell.log 2>&1 &
"""

import logging
import logging.handlers
import os
import signal
import sys
import time
import threading
from datetime import datetime
from typing import Optional

# ── ロガー初期設定（他モジュールより先に実施）──────────────────────────
import config

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        # RotatingFileHandler: 最大10MB × 3ファイル（SD容量保護のためローテーション）
        logging.handlers.RotatingFileHandler(
            config.LOG_FILE,
            maxBytes=config.LOG_MAX_BYTES,
            backupCount=config.LOG_BACKUP_COUNT,
            encoding="utf-8",
        ),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("main")

# ── モジュールインポート ─────────────────────────────────────────────
from database import db_manager
from sensors.pir_sensor import PIRSensor
from sensors.mailbox_sensor import MailboxSensor
from camera.camera_module import CameraModule
from camera.visitor_tracker import VisitorTracker
from detection.yolo_detector import YOLODetector
from detection.classifier import VisitorClassifier
from presence.bluetooth_checker import BluetoothPresenceChecker
from notification.line_bot import send_visitor_notification
from scheduler.daily_report import DailyReportScheduler
from storage.google_drive import DriveUploader


class DoorbellSystem:
    """
    玄関モニタリングシステムのメインクラス。
    全モジュールのライフサイクルを管理します。
    """

    def __init__(self):
        # コンポーネント
        self._camera: Optional[CameraModule] = None
        self._pir: Optional[PIRSensor] = None
        self._mailbox: Optional[MailboxSensor] = None
        self._tracker: Optional[VisitorTracker] = None
        self._detector: Optional[YOLODetector] = None
        self._classifier: Optional[VisitorClassifier] = None
        self._presence: Optional[NetworkPresenceChecker] = None
        self._scheduler: Optional[DailyReportScheduler] = None
        self._drive_uploader: Optional[DriveUploader] = None

        # 状態
        self._running = False
        self._pending_delivery = False   # 郵便受け投函フラグ
        self._delivery_lock = threading.Lock()

    # ----------------------------------------------------------------
    # コールバック
    # ----------------------------------------------------------------

    def _on_pir_motion(self, active: bool):
        """PIRセンサー検知コールバック。"""
        status = "動き検知" if active else "動き終了"
        logger.info(f"PIR: {status}")
        if self._tracker:
            self._tracker.notify_pir_state(active)

    def _on_mailbox_delivery(self, timestamp: float):
        """郵便受け投函コールバック。"""
        logger.info("郵便受け: 投函検知！")
        with self._delivery_lock:
            self._pending_delivery = True
        from database import db_manager as db
        db.insert_mailbox_event()

    def _on_visitor_detected(
        self, duration_sec: float, frames: list, session_dir: str
    ):
        """
        訪問者確定コールバック。
        YOLOで検出・分類し、データベースに保存、必要に応じてLINE通知します。
        """
        logger.info(f"訪問者確定処理開始: 滞在={duration_sec:.1f}秒")

        # ── 1. 物体検知 ─────────────────────────────────────────
        best_result = None
        detections_for_classifier = []
        if self._detector and self._detector.is_loaded and frames:
            best_result = self._detector.detect_from_frames(frames)
            # 分類器用に全フレームの検出結果を収集
            for frame in frames:
                det = self._detector.detect_best_person(frame)
                detections_for_classifier.append(det)

        # ── 2. 訪問者分類 ───────────────────────────────────────
        category = "other"
        confidence = 0.0
        if self._classifier and frames:
            category, confidence = self._classifier.classify_from_frames(
                frames, detections_for_classifier
            )

        # ── 3. 代表画像の保存 ───────────────────────────────────
        image_path = None
        if best_result and self._camera:
            representative_frame = best_result["frame"]
            image_path = self._camera.save_frame(
                frame=representative_frame,
                subdirectory=session_dir,
                filename="representative.jpg",
            )

        # ── 4. 郵便受け投函フラグを確認・リセット ───────────────
        with self._delivery_lock:
            has_delivery = self._pending_delivery
            self._pending_delivery = False

        # ── 5. 在宅状態を確認 ───────────────────────────────────
        is_home = self._presence.is_home if self._presence else None
        if is_home is None:
            is_home = True  # 判定不能な場合は在宅とみなし通知を省略

        # ── 6. データベースに保存 ───────────────────────────
        visitor_id = db_manager.insert_visitor(
            duration_sec=duration_sec,
            category=category,
            confidence=confidence,
            image_path=image_path,
            has_delivery=has_delivery,
            user_was_home=is_home,
        )

        # 郵便受けイベントと紐付け
        if has_delivery:
            db_manager.update_visitor_delivery(visitor_id, True)

        # ── 7. 不在時のみLINE通知 ───────────────────────────
        if not is_home:
            logger.info("不在中のため LINE 通知を送信します")
            visitor_record = {
                "id": visitor_id,
                "detected_at": datetime.now().isoformat(),
                "duration_sec": duration_sec,
                "category": category,
                "confidence": confidence,
                "has_delivery": has_delivery,
                "image_path": image_path,
            }
            success = send_visitor_notification(
                visitor=visitor_record,
                image_path=image_path,
            )
            if success:
                db_manager.mark_visitor_notified(visitor_id)
        else:
            logger.info("在宅中のため LINE 通知をスキップ")

        # ── 8. Google Drive へ非同期アップロード ────────────
        if image_path and self._drive_uploader:
            self._drive_uploader.enqueue(
                local_path=image_path,
                visitor_id=visitor_id,
            )

    def _on_presence_change(self, is_home: bool):
        """在宅状態変化コールバック。"""
        status = "在宅" if is_home else "不在"
        logger.info(f"在宅状態: {status}")
        db_manager.insert_presence(is_home)

    # ----------------------------------------------------------------
    # 起動・停止
    # ----------------------------------------------------------------

    def start(self):
        """全モジュールを起動します。"""
        logger.info("=" * 50)
        logger.info("玄関モニタリングシステム 起動中...")
        logger.info("=" * 50)

        # データベース初期化
        os.makedirs(config.DATA_DIR, exist_ok=True)
        os.makedirs(config.IMAGE_DIR, exist_ok=True)
        os.makedirs(config.MODEL_DIR, exist_ok=True)
        db_manager.initialize_db()

        # カメラ起動
        self._camera = CameraModule()
        if not self._camera.start():
            logger.critical("カメラの起動に失敗しました。接続を確認してください。")
            sys.exit(1)

        # YOLOモデルロード
        self._detector = YOLODetector()
        try:
            self._detector.load()
        except Exception as e:
            logger.warning(f"YOLOモデルロード失敗 (物体検知なしで続行): {e}")
            self._detector = None

        # 訪問者分類器
        self._classifier = VisitorClassifier()

        # 訪問者トラッカー
        self._tracker = VisitorTracker(
            camera=self._camera,
            on_visitor_detected=self._on_visitor_detected,
        )
        self._tracker.start()

        # PIRセンサー
        self._pir = PIRSensor(
            gpio_pin=config.PIR_GPIO_PIN,
            on_motion_callback=self._on_pir_motion,
            debounce_sec=config.PIR_DEBOUNCE_SEC,
        )
        self._pir.start()

        # 郵便受けセンサー
        self._mailbox = MailboxSensor(
            gpio_pin=config.MAILBOX_GPIO_PIN,
            on_delivery_callback=self._on_mailbox_delivery,
        )
        self._mailbox.start()

        # 在宅チェッカー（Bluetooth のみ）
        self._presence = BluetoothPresenceChecker(
            on_change_callback=self._on_presence_change,
        )
        logger.info("在宅判定: Bluetooth モード")
        self._presence.start()

        # 日次レポートスケジューラー
        self._scheduler = DailyReportScheduler()
        self._scheduler.start()

        # Google Drive アップローダー
        self._drive_uploader = DriveUploader()
        self._drive_uploader.start()

        self._running = True
        logger.info("✅ 全モジュール起動完了。監視中...")
        logger.info(f"   PIR GPIO: {config.PIR_GPIO_PIN}")
        logger.info(f"   郵便受け GPIO: {config.MAILBOX_GPIO_PIN}")
        logger.info(f"   在宅チェック対象: {config.HOME_DEVICE_IPS}")
        logger.info(f"   日次レポート時刻: {config.DAILY_REPORT_TIME}")
        logger.info("   停止: Ctrl+C")

    def stop(self):
        """全モジュールを安全に停止します。"""
        if not self._running:
            return
        self._running = False
        logger.info("システム停止中...")

        for component in [
            self._pir, self._mailbox, self._tracker,
            self._presence, self._scheduler, self._drive_uploader,
        ]:
            if component:
                try:
                    component.stop()
                except Exception as e:
                    logger.error(f"停止エラー ({component.__class__.__name__}): {e}")

        if self._camera:
            self._camera.stop()

        logger.info("システム停止完了")

    def run(self):
        """メインループ。Ctrl+C または SIGTERM で終了します。"""
        self.start()

        def signal_handler(signum, frame):
            logger.info(f"シグナル受信 ({signum}): 停止します...")
            self.stop()
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # メインスレッドはここで待機
        try:
            while self._running:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()


def main():
    """エントリーポイント。"""
    system = DoorbellSystem()
    system.run()


if __name__ == "__main__":
    main()
