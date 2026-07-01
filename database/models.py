"""
database/models.py — データモデル定義
SQLiteテーブルのスキーマと定数を定義します。
"""

# 訪問者カテゴリ定数
CATEGORY_POSTAL = "postal"       # 郵便局（日本郵便）
CATEGORY_YAMATO = "yamato"       # ヤマト運輸
CATEGORY_SAGAWA = "sagawa"       # 佐川急便
CATEGORY_RESIDENT = "resident"   # 住人
CATEGORY_OTHER = "other"         # その他

CATEGORY_DISPLAY_NAMES = {
    CATEGORY_POSTAL:   "📮 郵便局（日本郵便）",
    CATEGORY_YAMATO:   "🚚 ヤマト運輸",
    CATEGORY_SAGAWA:   "📦 佐川急便",
    CATEGORY_RESIDENT: "🏠 住人",
    CATEGORY_OTHER:    "👤 その他",
}

# SQLite テーブル作成SQL
CREATE_VISITORS_TABLE = """
CREATE TABLE IF NOT EXISTS visitors (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    detected_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
    duration_sec    REAL     NOT NULL,
    category        TEXT     NOT NULL DEFAULT 'other',
    confidence      REAL     NOT NULL DEFAULT 0.0,
    image_path      TEXT,
    has_delivery    BOOLEAN  DEFAULT 0,
    user_was_home   BOOLEAN  DEFAULT 0,
    notified        BOOLEAN  DEFAULT 0
);
"""

CREATE_MAILBOX_TABLE = """
CREATE TABLE IF NOT EXISTS mailbox_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    detected_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
    visitor_id      INTEGER,
    FOREIGN KEY (visitor_id) REFERENCES visitors(id)
);
"""

CREATE_PRESENCE_TABLE = """
CREATE TABLE IF NOT EXISTS presence_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    checked_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    is_home         BOOLEAN  NOT NULL
);
"""

ALL_CREATE_STATEMENTS = [
    CREATE_VISITORS_TABLE,
    CREATE_MAILBOX_TABLE,
    CREATE_PRESENCE_TABLE,
]
