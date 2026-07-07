"""
storage/google_drive.py — Google Drive アップロードモジュール

サービスアカウント認証を使って画像をGoogle Driveにアップロードします。
アップロードはバックグラウンドスレッドで非同期に実行され、
失敗した場合はリトライキューに残して再試行します。

【事前準備】
1. Google Cloud Console でプロジェクトを作成
2. Google Drive API を有効化
3. サービスアカウントを作成し、JSONキーをダウンロード
4. JSONキーをRaspiに配置（例: /home/pi/LineBot/service_account.json）
5. Google Driveでフォルダを作成し、サービスアカウントのメールアドレスと共有
6. .env に GOOGLE_DRIVE_FOLDER_ID を設定
"""

import logging
import os
import queue
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

logger = logging.getLogger(__name__)


@dataclass
class UploadTask:
    """アップロードタスクのデータクラス。"""
    local_path: str
    visitor_id: Optional[int] = None
    retries: int = 0
    created_at: float = field(default_factory=time.time)
    _next_retry_at: float = 0.0


class DriveUploader:
    """
    Google Driveへの非同期アップロードクラス。

    画像をバックグラウンドでGoogle Driveにアップロードし、
    成功後にローカルファイルを削除します。
    失敗した場合は最大 config.DRIVE_UPLOAD_MAX_RETRIES 回再試行します。

    使用方法:
        uploader = DriveUploader()
        uploader.start()
        uploader.enqueue(local_path="/path/to/image.jpg", visitor_id=123)
        uploader.stop()
    """

    def __init__(self):
        self._queue: queue.Queue = queue.Queue()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._service = None  # Google Drive API サービスオブジェクト
        self._folder_cache: dict = {}  # フォルダ名 → フォルダID のキャッシュ
        self._enabled = config.DRIVE_UPLOAD_ENABLED

    # ----------------------------------------------------------------
    # 公開メソッド
    # ----------------------------------------------------------------

    def start(self):
        """アップロードワーカースレッドを開始します。"""
        if not self._enabled:
            logger.info("Google Drive アップロードは無効化されています (DRIVE_UPLOAD_ENABLED=false)")
            return

        if self._running:
            return

        # サービスアカウントのJSONが存在するか確認
        if not os.path.exists(config.GOOGLE_SERVICE_ACCOUNT_JSON):
            logger.warning(
                f"サービスアカウントJSONが見つかりません: {config.GOOGLE_SERVICE_ACCOUNT_JSON}\n"
                "Google Drive アップロードを無効化します。\n"
                "設定手順は README を参照してください。"
            )
            self._enabled = False
            return

        if not config.GOOGLE_DRIVE_FOLDER_ID:
            logger.warning(
                "GOOGLE_DRIVE_FOLDER_ID が設定されていません。\n"
                ".env に GOOGLE_DRIVE_FOLDER_ID=<フォルダID> を追加してください。"
            )
            self._enabled = False
            return

        try:
            self._service = self._build_service()
        except Exception as e:
            logger.error(f"Google Drive API 初期化失敗: {e}\nアップロードを無効化します。")
            self._enabled = False
            return

        self._running = True
        self._thread = threading.Thread(
            target=self._worker_loop,
            name="DriveUploaderThread",
            daemon=True,
        )
        self._thread.start()
        logger.info("Google Drive アップローダー起動")

    def stop(self):
        """ワーカースレッドを停止します。キューに残っているタスクは完了を待ちません。"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Google Drive アップローダー停止")

    def enqueue(self, local_path: str, visitor_id: Optional[int] = None):
        """
        アップロードタスクをキューに追加します。

        Args:
            local_path: アップロードするローカル画像のパス
            visitor_id: DBの訪問者ID（アップロード後にURLを更新するために使用）
        """
        if not self._enabled:
            return
        if not os.path.exists(local_path):
            logger.warning(f"アップロード対象ファイルが存在しません: {local_path}")
            return
        task = UploadTask(local_path=local_path, visitor_id=visitor_id)
        self._queue.put(task)
        logger.debug(f"Drive アップロードキューに追加: {local_path}")

    # ----------------------------------------------------------------
    # 内部処理
    # ----------------------------------------------------------------

    def _build_service(self):
        """Google Drive API サービスを構築します。"""
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build
        except ImportError:
            raise ImportError(
                "Google API ライブラリが未インストールです。\n"
                "pip install google-api-python-client google-auth を実行してください。"
            )

        scopes = ["https://www.googleapis.com/auth/drive"]
        credentials = service_account.Credentials.from_service_account_file(
            config.GOOGLE_SERVICE_ACCOUNT_JSON,
            scopes=scopes,
        )
        service = build("drive", "v3", credentials=credentials)
        logger.info("Google Drive API 認証成功")
        return service

    def _worker_loop(self):
        """バックグラウンドでアップロードキューを処理するループ。"""
        retry_tasks: list = []  # リトライ待ちのタスク

        while self._running:
            # リトライタスクを優先的に処理
            now = time.time()
            due_retries = [t for t in retry_tasks if now >= t._next_retry_at]
            for task in due_retries:
                retry_tasks.remove(task)
                self._process_task(task, retry_tasks)

            # 新しいタスクを取得（最大1秒待機）
            try:
                task = self._queue.get(timeout=1.0)
                self._process_task(task, retry_tasks)
                self._queue.task_done()
            except queue.Empty:
                pass

    def _process_task(self, task: UploadTask, retry_tasks: list):
        """単一タスクのアップロードを処理します。"""
        if not os.path.exists(task.local_path):
            logger.warning(f"アップロード対象が見つかりません（削除済み？）: {task.local_path}")
            return

        try:
            drive_url, file_id = self._upload_file(task.local_path)
            logger.info(f"Drive アップロード成功: {os.path.basename(task.local_path)} → {drive_url}")

            # DBを更新
            if task.visitor_id is not None:
                try:
                    from database import db_manager
                    db_manager.update_visitor_drive_url(
                        visitor_id=task.visitor_id,
                        drive_url=drive_url,
                        drive_file_id=file_id,
                    )
                except Exception as e:
                    logger.error(f"Drive URL DB更新失敗: {e}")

            # ローカルファイルを削除
            self._delete_local_file(task.local_path)

        except Exception as e:
            task.retries += 1
            if task.retries <= config.DRIVE_UPLOAD_MAX_RETRIES:
                # 指数バックオフ: 1分 → 2分 → 4分 → ... (最大1時間)
                wait_sec = min(60 * (2 ** (task.retries - 1)), 3600)
                task._next_retry_at = time.time() + wait_sec
                retry_tasks.append(task)
                logger.warning(
                    f"Drive アップロード失敗 ({task.retries}/{config.DRIVE_UPLOAD_MAX_RETRIES}回目): "
                    f"{os.path.basename(task.local_path)} — {e}\n"
                    f"{wait_sec}秒後にリトライします。"
                )
            else:
                logger.error(
                    f"Drive アップロード最大リトライ超過: {task.local_path}\n"
                    "ローカルファイルはそのまま保持します。"
                )

    def _get_or_create_subfolder(self, subfolder_name: str, parent_folder_id: str) -> str:
        """
        指定した親フォルダ内にサブフォルダを取得または作成します。

        Args:
            subfolder_name: サブフォルダ名（例: "2026-07"）
            parent_folder_id: 親フォルダのGoogle Drive ID

        Returns:
            サブフォルダのGoogle Drive ID
        """
        cache_key = f"{parent_folder_id}/{subfolder_name}"
        if cache_key in self._folder_cache:
            return self._folder_cache[cache_key]

        # 既存フォルダを検索
        query = (
            f"name='{subfolder_name}' and "
            f"'{parent_folder_id}' in parents and "
            "mimeType='application/vnd.google-apps.folder' and "
            "trashed=false"
        )
        results = self._service.files().list(q=query, fields="files(id)").execute()
        files = results.get("files", [])

        if files:
            folder_id = files[0]["id"]
        else:
            # フォルダ新規作成
            meta = {
                "name": subfolder_name,
                "mimeType": "application/vnd.google-apps.folder",
                "parents": [parent_folder_id],
            }
            folder = self._service.files().create(body=meta, fields="id").execute()
            folder_id = folder["id"]
            logger.info(f"Drive サブフォルダ作成: {subfolder_name} (id={folder_id})")

        self._folder_cache[cache_key] = folder_id
        return folder_id

    def _upload_file(self, local_path: str) -> tuple:
        """
        ファイルをGoogle Driveにアップロードします。

        Returns:
            (共有URL, ファイルID) のタプル
        """
        from googleapiclient.http import MediaFileUpload

        # 年月でサブフォルダを分けて整理（例: 2026-07）
        year_month = datetime.now().strftime("%Y-%m")
        subfolder_id = self._get_or_create_subfolder(
            subfolder_name=year_month,
            parent_folder_id=config.GOOGLE_DRIVE_FOLDER_ID,
        )

        filename = os.path.basename(local_path)
        file_metadata = {
            "name": filename,
            "parents": [subfolder_id],
        }
        media = MediaFileUpload(local_path, mimetype="image/jpeg", resumable=False)

        uploaded = (
            self._service.files()
            .create(body=file_metadata, media_body=media, fields="id, webViewLink")
            .execute()
        )
        file_id = uploaded["id"]

        # 閲覧権限を「リンクを知っている全員」に設定
        self._service.permissions().create(
            fileId=file_id,
            body={"role": "reader", "type": "anyone"},
        ).execute()

        # 直接表示URLに変換（ブラウザで画像が開く形式）
        direct_url = f"https://drive.google.com/uc?export=view&id={file_id}"
        return direct_url, file_id

    def _delete_local_file(self, local_path: str):
        """ローカルの画像ファイルを削除します。親ディレクトリが空になれば削除します。"""
        try:
            os.remove(local_path)
            logger.debug(f"ローカル画像削除: {local_path}")

            # セッションディレクトリが空になったら削除
            parent_dir = os.path.dirname(local_path)
            if os.path.isdir(parent_dir) and not os.listdir(parent_dir):
                os.rmdir(parent_dir)
                logger.debug(f"空ディレクトリ削除: {parent_dir}")

        except OSError as e:
            logger.error(f"ローカル画像削除エラー: {e}")
