"""
database/db_manager.py — SQLiteデータベース操作
訪問者・郵便受け・在宅ログの読み書きを担当します。
"""

import sqlite3
import logging
from datetime import datetime, date
from contextlib import contextmanager
from typing import Optional, List, Dict, Any

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from database.models import ALL_CREATE_STATEMENTS

logger = logging.getLogger(__name__)


@contextmanager
def get_connection():
    """SQLite接続のコンテキストマネージャー（自動コミット・クローズ）"""
    conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row  # 辞書形式でアクセス可能
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"DB操作エラー: {e}")
        raise
    finally:
        conn.close()


def initialize_db():
    """データベースとテーブルを初期化します。"""
    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
    with get_connection() as conn:
        cursor = conn.cursor()
        for stmt in ALL_CREATE_STATEMENTS:
            cursor.execute(stmt)
    logger.info(f"データベース初期化完了: {config.DB_PATH}")


# ============================================================
# 訪問者テーブル操作
# ============================================================

def insert_visitor(
    duration_sec: float,
    category: str,
    confidence: float,
    image_path: Optional[str] = None,
    has_delivery: bool = False,
    user_was_home: bool = False,
) -> int:
    """訪問者レコードを挿入し、IDを返します。"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO visitors
                (duration_sec, category, confidence, image_path, has_delivery, user_was_home)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (duration_sec, category, confidence, image_path, has_delivery, user_was_home),
        )
        visitor_id = cursor.lastrowid
    logger.info(
        f"訪問者記録 ID={visitor_id} カテゴリ={category} 滞在={duration_sec:.1f}s"
    )
    return visitor_id


def mark_visitor_notified(visitor_id: int):
    """訪問者の通知済みフラグを立てます。"""
    with get_connection() as conn:
        conn.execute(
            "UPDATE visitors SET notified=1 WHERE id=?", (visitor_id,)
        )


def update_visitor_delivery(visitor_id: int, has_delivery: bool):
    """訪問者の配達物フラグを更新します。"""
    with get_connection() as conn:
        conn.execute(
            "UPDATE visitors SET has_delivery=? WHERE id=?",
            (int(has_delivery), visitor_id),
        )


def get_todays_visitors() -> List[Dict[str, Any]]:
    """本日の訪問者一覧を取得します。"""
    today = date.today().isoformat()
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT * FROM visitors
            WHERE date(detected_at) = ?
            ORDER BY detected_at ASC
            """,
            (today,),
        )
        return [dict(row) for row in cursor.fetchall()]


def get_unnotified_visitors() -> List[Dict[str, Any]]:
    """未通知の訪問者一覧を取得します。"""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM visitors WHERE notified=0 ORDER BY detected_at ASC"
        )
        return [dict(row) for row in cursor.fetchall()]


# ============================================================
# 郵便受けテーブル操作
# ============================================================

def insert_mailbox_event(visitor_id: Optional[int] = None):
    """郵便受けへの投函イベントを記録します。"""
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO mailbox_events (visitor_id) VALUES (?)", (visitor_id,)
        )
    logger.info("郵便受けイベント記録")


def get_todays_mailbox_events() -> List[Dict[str, Any]]:
    """本日の郵便受けイベント一覧を取得します。"""
    today = date.today().isoformat()
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT * FROM mailbox_events
            WHERE date(detected_at) = ?
            ORDER BY detected_at ASC
            """,
            (today,),
        )
        return [dict(row) for row in cursor.fetchall()]


# ============================================================
# 在宅ログ操作
# ============================================================

def insert_presence(is_home: bool):
    """在宅判定結果をログに記録します。"""
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO presence_log (is_home) VALUES (?)", (int(is_home),)
        )


def get_latest_presence() -> Optional[bool]:
    """最新の在宅状態を返します。"""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT is_home FROM presence_log ORDER BY checked_at DESC LIMIT 1"
        )
        row = cursor.fetchone()
        return bool(row["is_home"]) if row else None


def get_todays_presence_summary() -> Dict[str, int]:
    """本日の在宅時間帯の集計を返します（在宅回数・不在回数）。"""
    today = date.today().isoformat()
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT is_home, COUNT(*) as cnt
            FROM presence_log
            WHERE date(checked_at) = ?
            GROUP BY is_home
            """,
            (today,),
        )
        result = {"home_count": 0, "away_count": 0}
        for row in cursor.fetchall():
            if row["is_home"]:
                result["home_count"] = row["cnt"]
            else:
                result["away_count"] = row["cnt"]
        return result
