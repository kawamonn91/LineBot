"""
notification/line_bot.py — LINE Messaging API 通知モジュール
訪問者通知と日次レポートをLINEにプッシュ送信します。

【事前準備】
1. LINE Developers (https://developers.line.biz/) でプロバイダー・チャンネルを作成
2. Messaging API チャンネルのアクセストークンを発行
3. LINEアプリで Bot を友達追加
4. Webhook で自分のUser IDを確認（または LINE Notify の "me" エンドポイントで取得）
5. config.py に LINE_CHANNEL_ACCESS_TOKEN と LINE_USER_ID を設定
"""

import logging
import os
import requests
from datetime import datetime
from typing import Optional

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from database.models import CATEGORY_DISPLAY_NAMES

logger = logging.getLogger(__name__)

LINE_API_BASE = "https://api.line.me/v2/bot"
LINE_PUSH_URL = f"{LINE_API_BASE}/message/push"
IMGUR_UPLOAD_URL = "https://api.imgur.com/3/image"


def _get_headers() -> dict:
    """LINE API 共通ヘッダーを返します。"""
    return {
        "Authorization": f"Bearer {config.LINE_CHANNEL_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }


def _push_messages(messages: list[dict]) -> bool:
    """
    LINE Messaging API でメッセージをプッシュ送信します。

    Args:
        messages: LINEメッセージオブジェクトのリスト（最大5件）

    Returns:
        成功したらTrue
    """
    if not config.LINE_CHANNEL_ACCESS_TOKEN or config.LINE_CHANNEL_ACCESS_TOKEN == "YOUR_CHANNEL_ACCESS_TOKEN_HERE":
        logger.error("LINE_CHANNEL_ACCESS_TOKEN が設定されていません。config.pyを確認してください。")
        return False

    payload = {
        "to": config.LINE_USER_ID,
        "messages": messages[:5],  # LINE制限: 最大5メッセージ
    }

    try:
        response = requests.post(
            LINE_PUSH_URL,
            headers=_get_headers(),
            json=payload,
            timeout=10,
        )
        if response.status_code == 200:
            logger.info("LINE送信成功")
            return True
        else:
            logger.error(
                f"LINE送信失敗: status={response.status_code} body={response.text}"
            )
            return False
    except requests.exceptions.RequestException as e:
        logger.error(f"LINE送信ネットワークエラー: {e}")
        return False


def _upload_image(image_path: str) -> Optional[str]:
    """
    画像を imgur に匿名アップロードし、HTTPS公開 URL を返します。

    imgur の匿名アップロード API (登録不要) を使用します。
    取得した URL を LINE Messaging API の《URL方式》画像メッセージで使用します。

    Args:
        image_path: アップロードするローカル画像ファイルのパス (JPEG/PNG)

    Returns:
        成功時は HTTPS 公開 URL 文字列、失敗時は None
    """
    if not os.path.exists(image_path):
        logger.error(f"画像ファイルが存在しません: {image_path}")
        return None

    try:
        import cv2
        import numpy as np

        img = cv2.imread(image_path)
        if img is None:
            logger.error(f"画像の読み込みに失敗しました: {image_path}")
            return None

        # LINE 画像メッセージの制限: 10MB 未満、長辺 4096px 以下
        # imgur の制限: 20MB 未満
        # 大きすぎる場合はリサイズする
        h, w = img.shape[:2]
        max_dim = 1920
        if w > max_dim or h > max_dim:
            scale = max_dim / max(w, h)
            img = cv2.resize(img, (int(w * scale), int(h * scale)))
            logger.debug(f"画像をリサイズ: {w}x{h} → {img.shape[1]}x{img.shape[0]}")

        # JPEGエンコードしてバイト列に変換
        _, buffer = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])
        image_bytes = buffer.tobytes()

    except Exception as e:
        logger.error(f"画像の事前処理エラー: {e}")
        # フォールバック: ファイルをそのまま読み込む
        try:
            with open(image_path, "rb") as f:
                image_bytes = f.read()
        except OSError as e2:
            logger.error(f"画像ファイルの読み込みエラー: {e2}")
            return None

    headers = {
        "Authorization": "Client-ID 546c25a59c58ad7",  # imgur 匿名公開 Client-ID
    }

    try:
        import base64
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")

        response = requests.post(
            IMGUR_UPLOAD_URL,
            headers=headers,
            data={"image": image_b64, "type": "base64"},
            timeout=30,
        )

        if response.status_code == 200:
            data = response.json()
            url = data.get("data", {}).get("link", "")
            if url:
                # imgurの http リンクを https に強制変換 (LINE API 要件)
                url = url.replace("http://", "https://")
                logger.info(f"画像アップロード成功: {url}")
                return url
            else:
                logger.error(f"imgur URLがレスポンスに含まれていません: {data}")
                return None
        else:
            logger.error(
                f"画像アップロード失敗: status={response.status_code} body={response.text}"
            )
            return None

    except requests.exceptions.RequestException as e:
        logger.error(f"画像アップロードネットワークエラー: {e}")
        return None


def send_visitor_notification(
    visitor: dict,
    image_path: Optional[str] = None,
) -> bool:
    """
    不在時訪問者通知を送信します。

    Args:
        visitor: 訪問者レコード (dbから取得した辞書)
        image_path: 代表画像のパス (オプション)

    Returns:
        送信成功したらTrue
    """
    category = visitor.get("category", "other")
    category_display = CATEGORY_DISPLAY_NAMES.get(category, "👤 不明")
    duration = visitor.get("duration_sec", 0)
    has_delivery = visitor.get("has_delivery", False)
    detected_at = visitor.get("detected_at", "")

    # 時刻を日本語形式にフォーマット
    try:
        dt = datetime.fromisoformat(str(detected_at))
        time_str = dt.strftime("%H:%M")
    except Exception:
        time_str = str(detected_at)

    # メッセージ本文構築
    delivery_text = "📬 郵便物・荷物あり" if has_delivery else "📭 配達物なし"

    text = (
        f"🔔 【不在時訪問のお知らせ】\n"
        f"━━━━━━━━━━━━━━\n"
        f"⏰ 時刻: {time_str}\n"
        f"👤 分類: {category_display}\n"
        f"⏱ 滞在時間: {duration:.0f}秒\n"
        f"{delivery_text}\n"
        f"━━━━━━━━━━━━━━\n"
        f"玄関カメラが訪問者を記録しました。"
    )

    messages = [{"type": "text", "text": text}]

    # 画像パスがあれば imgur 経由で画像メッセージを追加
    if image_path and os.path.exists(image_path):
        image_url = _upload_image(image_path)
        if image_url:
            # URL方式の画像メッセージ
            messages.append({
                "type": "image",
                "originalContentUrl": image_url,
                "previewImageUrl": image_url,
            })
            logger.info(f"画像メッセージを追加しました: {image_url}")
        else:
            # アップロード失敗時はファイル名をテキストで補足
            messages.append({
                "type": "text",
                "text": f"📷 画像はRaspiに保存済み:\n{os.path.basename(image_path)}"
            })
            logger.warning("画像アップロード失敗のため、ファイル名テキストで代替します")

    return _push_messages(messages)


def send_daily_report(
    visitors: list[dict],
    mailbox_events: list[dict],
    presence_summary: dict,
) -> bool:
    """
    毎日19時の日次レポートを送信します。

    Args:
        visitors: 本日の訪問者リスト
        mailbox_events: 本日の郵便受けイベントリスト
        presence_summary: 在宅サマリー {"home_count": int, "away_count": int}

    Returns:
        送信成功したらTrue
    """
    today = datetime.now().strftime("%Y年%m月%d日")
    visitor_count = len(visitors)
    delivery_count = len(mailbox_events)

    # 訪問者サマリー作成
    if visitor_count == 0:
        visitor_summary = "（なし）"
    else:
        lines = []
        for v in visitors:
            try:
                dt = datetime.fromisoformat(str(v.get("detected_at", "")))
                t = dt.strftime("%H:%M")
            except Exception:
                t = "不明"

            cat = v.get("category", "other")
            cat_display = CATEGORY_DISPLAY_NAMES.get(cat, "👤 不明")
            dur = v.get("duration_sec", 0)
            delivery_mark = "📬" if v.get("has_delivery") else ""
            lines.append(f"  {t} {cat_display} ({dur:.0f}秒) {delivery_mark}")

        visitor_summary = "\n".join(lines)

    # 在宅情報
    home_pct = 0
    total = presence_summary.get("home_count", 0) + presence_summary.get("away_count", 0)
    if total > 0:
        home_pct = int(presence_summary.get("home_count", 0) / total * 100)

    text = (
        f"📊 【{today} 日次レポート】\n"
        f"━━━━━━━━━━━━━━\n"
        f"👥 本日の訪問者: {visitor_count}件\n"
        f"📬 郵便物・荷物: {delivery_count}件\n"
        f"🏠 在宅率: 約{home_pct}%\n"
        f"━━━━━━━━━━━━━━\n"
        f"【訪問者詳細】\n"
        f"{visitor_summary}\n"
        f"━━━━━━━━━━━━━━\n"
        f"玄関モニタリングシステム"
    )

    messages = [{"type": "text", "text": text}]
    return _push_messages(messages)


def send_test_message() -> bool:
    """
    LINE接続テスト用メッセージを送信します。

    使用方法:
        python -m notification.line_bot --test
    """
    text = (
        "✅ LINE Bot 接続テスト\n"
        "玄関モニタリングシステムが正常に動作しています。\n"
        f"テスト日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    return _push_messages([{"type": "text", "text": text}])


# コマンドライン実行時のテスト機能
if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.DEBUG)

    if "--test" in sys.argv:
        print("LINEテストメッセージを送信中...")
        result = send_test_message()
        print("✅ 送信成功" if result else "❌ 送信失敗")
    else:
        print("使用方法: python -m notification.line_bot --test")
