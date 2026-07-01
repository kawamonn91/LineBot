"""
scheduler/daily_report.py — 日次レポートスケジューラー
毎日19時に本日の訪問者データをLINEに送信します。
"""

import logging
import threading
import time
from datetime import datetime
from typing import Optional

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

logger = logging.getLogger(__name__)


class DailyReportScheduler:
    """
    毎日指定時刻に日次レポートを送信するスケジューラー。

    使用方法:
        scheduler = DailyReportScheduler()
        scheduler.start()
        # メインループで待機
        scheduler.stop()
    """

    def __init__(self, report_time: str = None):
        """
        Args:
            report_time: レポート送信時刻 "HH:MM" 形式 (例: "19:00")
        """
        self.report_time = report_time or config.DAILY_REPORT_TIME
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_sent_date: Optional[str] = None

    def start(self):
        """スケジューラーを開始します。"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._scheduler_loop, name="DailyReportScheduler", daemon=True
        )
        self._thread.start()
        logger.info(f"日次レポートスケジューラー開始: 送信時刻={self.report_time}")

    def stop(self):
        """スケジューラーを停止します。"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("日次レポートスケジューラー停止")

    def _scheduler_loop(self):
        """毎分、現在時刻を確認してレポート送信タイミングかチェックします。"""
        while self._running:
            try:
                now = datetime.now()
                current_time_str = now.strftime("%H:%M")
                current_date_str = now.strftime("%Y-%m-%d")

                # 指定時刻 かつ 今日まだ送っていない場合に送信
                if (
                    current_time_str == self.report_time
                    and self._last_sent_date != current_date_str
                ):
                    logger.info(f"日次レポート送信開始: {now}")
                    self._send_report()
                    self._last_sent_date = current_date_str

                # 次の00秒まで待機（1分間隔でチェック）
                sleep_sec = 60 - now.second
                time.sleep(sleep_sec)

            except Exception as e:
                logger.error(f"スケジューラーエラー: {e}")
                time.sleep(60)

    def _send_report(self):
        """日次レポートを取得して送信します。"""
        try:
            from database import db_manager
            from notification import line_bot

            visitors = db_manager.get_todays_visitors()
            mailbox_events = db_manager.get_todays_mailbox_events()
            presence_summary = db_manager.get_todays_presence_summary()

            success = line_bot.send_daily_report(
                visitors=visitors,
                mailbox_events=mailbox_events,
                presence_summary=presence_summary,
            )

            if success:
                logger.info("日次レポート送信完了")
            else:
                logger.error("日次レポート送信失敗")

        except Exception as e:
            logger.error(f"日次レポート生成エラー: {e}")

    def send_now(self):
        """
        即座にレポートを送信します（テスト・手動実行用）。
        """
        logger.info("手動レポート送信")
        self._send_report()


# コマンドライン実行時の手動送信
if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.DEBUG)

    if "--send-now" in sys.argv:
        print("日次レポートを今すぐ送信中...")
        scheduler = DailyReportScheduler()
        scheduler.send_now()
    else:
        print("使用方法: python -m scheduler.daily_report --send-now")
