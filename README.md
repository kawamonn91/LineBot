# 🚪 玄関モニタリングシステム

Raspberry Pi 5 と各種センサー（OSOYOO DKRK100600）を組み合わせた、
PIRセンサー・USBカメラ・YOLOv8による訪問者検知・LINE通知システムです。

---

## 機能一覧

| 機能 | 説明 |
|------|------|
| 👤 通過検知 | HC-SR501 PIRセンサーで人の通過を検知 |
| 📹 録画・記録 | USBカメラで3秒以上滞在した訪問者を記録 |
| 🤖 訪問者分類 | YOLOv8 + 色ヒストグラムで配達員を分類 |
| 📬 郵便受け検知 | フォトレジスタ（光センサー）で投函を検知 |
| 🏠 在宅判定 | スマートフォンIPのARP/Pingスキャンで判定 |
| 📲 LINE通知 | 不在時訪問・配達物をLINEで即時通知 |
| 📊 日次レポート | 毎日19時に訪問者データをLINEで送信 |

## 訪問者分類カテゴリ

- 📮 **郵便局（日本郵便）** — 赤・オレンジ系制服
- 🚚 **ヤマト運輸** — 黒・濃紺系制服
- 📦 **佐川急便** — 青系制服
- 🏠 **住人** — 上記以外の繰り返し来訪者
- 👤 **その他** — 分類不明

---

## ハードウェア構成

| パーツ | 型番 | 接続先 |
|--------|------|--------|
| Raspberry Pi 5 | 8GB推奨 | — |
| PIRセンサー | HC-SR501 (DKRK100600内) | GPIO 17 (BCM) |
| 郵便受けセンサー | フォトレジスタ + 10kΩ抵抗 | GPIO 27 (BCM) |
| カメラ | USBカメラ | USB |

### HC-SR501 配線
```
HC-SR501    Raspberry Pi 5
VCC    →   5V (Pin 2)
GND    →   GND (Pin 6)
OUT    →   GPIO 17 (Pin 11)
```

### フォトレジスタ配線（郵便受け内部に設置）
```
フォトレジスタ + 10kΩ抵抗（プルダウン）  Raspberry Pi 5
3.3V (Pin 1)  ──────────────────────── フォトレジスタの片方の足
GPIO 27 (Pin 13) ───────────────────── フォトレジスタのもう片方の足
                                        └── 10kΩ抵抗の片側（同じ列）
GND (Pin 14)  ──────────────────────── 10kΩ抵抗のもう片側
```

**動作原理**: 郵便物が投函されると郵便受け内部が暗くなり（HIGH→LOW変化）、
2秒以上暗い状態が続いた場合に投函確定と判定します。

---

## セットアップ手順

### 1. ファイルをRaspberry Piにコピー
Google Driveからダウンロードするか、`git clone` でコピーします。

```bash
# 例: ホームディレクトリにコピー
cp -r /media/pi/GoogleDrive/LineBot ~/LineBot
cd ~/LineBot
```

### 2. 環境構築スクリプトを実行
```bash
chmod +x setup.sh
./setup.sh
```

### 3. LINE Bot の設定
1. [LINE Developers](https://developers.line.biz/) でMessaging APIチャンネルを作成（完了済み）
2. **Channel Access Token** を発行
3. **User ID** を確認（LINE公式アカウントマネージャー or Webhookで確認）

### 4. config.py を編集
```python
# config.py の以下の項目を実際の値に書き換え
LINE_CHANNEL_ACCESS_TOKEN = "実際のトークンをここに"
LINE_USER_ID = "Uxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

# スマートフォンの固定IPアドレス（ルーターで設定）
HOME_DEVICE_IPS = [
    "192.168.1.100",  # あなたのスマートフォン
]
```

### 5. 動作テスト
```bash
source venv/bin/activate

# LINE接続テスト
python -m notification.line_bot --test

# 在宅判定テスト
python -m presence.network_checker --debug

# 日次レポートをすぐ送信（テスト）
python -m scheduler.daily_report --send-now
```

### 6. システム起動
```bash
source venv/bin/activate
python main.py
```

### 7. 自動起動設定（任意）
```bash
# systemd/doorbell.service の WorkingDirectory と User を実際のパスに変更してから:
sudo cp systemd/doorbell.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable doorbell
sudo systemctl start doorbell

# 状態確認
sudo systemctl status doorbell

# ログ確認
tail -f doorbell.log
```

---

## スマートフォン在宅判定の注意事項

> ⚠️ **MACアドレスランダム化について**
>
> iOS 14以降・Android 10以降では、Wi-Fi接続時にMACアドレスをランダム化する機能が
> デフォルトで有効です。これを有効のままにするとARPスキャンでデバイスを
> 識別できなくなります。
>
> **対処方法**: スマートフォンのWi-Fi設定 → 接続中のネットワーク → 
> 「プライベートWi-Fiアドレス」or「MACアドレスのランダム化」を **オフ** に設定

---

## ディレクトリ構成

```
LineBot/
├── main.py                    # メインエントリーポイント
├── config.py                  # ⚙️ 設定ファイル（要編集）
├── requirements.txt           # Pythonライブラリ一覧
├── setup.sh                   # 環境構築スクリプト
├── doorbell.log               # 実行ログ（起動後生成）
│
├── sensors/
│   ├── pir_sensor.py          # HC-SR501 PIRセンサー
│   └── mailbox_sensor.py      # SW-520D 郵便受けセンサー
│
├── camera/
│   ├── camera_module.py       # USBカメラ制御（OpenCV）
│   └── visitor_tracker.py     # 滞在時間計測
│
├── detection/
│   ├── yolo_detector.py       # YOLOv8 人物検出
│   └── classifier.py          # 色ベース訪問者分類
│
├── presence/
│   └── network_checker.py     # ネットワーク在宅判定
│
├── database/
│   ├── db_manager.py          # SQLite操作
│   └── models.py              # データモデル定義
│
├── notification/
│   └── line_bot.py            # LINE Messaging API
│
├── scheduler/
│   └── daily_report.py        # 日次レポート（19時）
│
├── systemd/
│   └── doorbell.service       # 自動起動サービス設定
│
└── data/                      # 起動後自動生成
    ├── visitors.db            # SQLiteデータベース
    ├── images/                # 訪問者画像
    └── models/                # YOLOモデルファイル
```

---

## トラブルシューティング

| 症状 | 確認事項 |
|------|---------|
| カメラが起動しない | `ls /dev/video*` でデバイス確認、`config.py`の`CAMERA_INDEX`を変更 |
| GPIO エラー | `sudo usermod -aG gpio $USER` でユーザーをgroupに追加後、再ログイン |
| LINE通知が届かない | `python -m notification.line_bot --test` でトークンを確認 |
| 在宅判定が機能しない | スマホのMACランダム化無効化・固定IP設定を確認 |
| YOLOのロードが遅い | 初回のみモデルダウンロードが発生（~6MB）。2回目以降は高速 |
| ログ確認 | `tail -f doorbell.log` |

---

## 📋 テスト方法

各機能の詳細なテスト手順は **[TESTING.md](TESTING.md)** を参照してください。
