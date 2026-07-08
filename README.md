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

### 1. Raspberry Pi にファイルをコピー

```bash
git clone <your-repo-url> ~/LineBot
cd ~/LineBot
```

### 2. 環境構築（venv + パッケージインストール）

> ⚠️ **Debian 12 (bookworm) の注意**: `setup.sh` は `pip install --upgrade pip` が
> システム管理Pythonで失敗する場合があります。その場合は以下を手動で実行してください。

```bash
# venv を作成
python3 -m venv ~/LineBot/venv

# torch CPU-only 版を先にインストール（CUDA不要・ディスク節約）
~/LineBot/venv/bin/pip install "torch==2.1.2" "torchvision==0.16.2" \
    --index-url https://download.pytorch.org/whl/cpu --no-cache-dir

# 残りのパッケージをインストール
~/LineBot/venv/bin/pip install \
    "opencv-python>=4.8.0,<5.0" "RPi.GPIO>=0.7.1" "gpiozero>=2.0" \
    "requests>=2.31.0" "numpy>=1.24.0,<2.0" "python-dotenv>=1.0.0" \
    "scikit-learn>=1.3.0" "joblib>=1.3.0" \
    "google-api-python-client>=2.100.0" "google-auth>=2.23.0" \
    "google-auth-httplib2>=0.2.0" "ultralytics>=8.0.0" --no-cache-dir
```

> **システムパッケージ（apt）も必要:**
> ```bash
> sudo apt-get install -y python3-venv python3-opencv libopencv-dev \
>     net-tools arp-scan libatlas-base-dev libhdf5-dev git
> ```

### 3. .env を設定

```bash
cp .env.example .env   # .env.example があれば
nano .env
```

```env
LINE_CHANNEL_ACCESS_TOKEN=<LINEトークン>
LINE_USER_ID=U<ユーザーID>
HOME_DEVICE_IPS=192.168.1.100       # Wi-Fi在宅判定を使う場合のスマホIP
HOME_BT_ADDRESSES=XX:XX:XX:XX:XX:XX # Bluetooth在宅判定を使う場合のスマホBTアドレス
PRESENCE_USE_BLUETOOTH=true          # true=BT / false=Wi-Fi
```

### 4. GPIO権限の確認

```bash
groups $USER
# "gpio" が含まれていなければ:
sudo usermod -aG gpio $USER
# → 一度ログアウト・再ログインが必要
```

### 5. LINE Bot の動作テスト

```bash
source venv/bin/activate
python -m notification.line_bot --test
# → ✅ 送信成功
```

### 6. 在宅判定テスト

**Bluetooth モード（推奨）:**
```bash
# ① スマホとペアリング（初回のみ）
bluetoothctl
# [bluetooth]# scan on
# [bluetooth]# pair XX:XX:XX:XX:XX:XX   ← スマホのBTアドレス
# [bluetooth]# trust XX:XX:XX:XX:XX:XX
# [bluetooth]# exit

# ② 動作テスト
python -m presence.bluetooth_checker --debug
```

**Wi-Fi モード（家庭内ルーターのみ）:**
```bash
python -m presence.network_checker --debug
```

### 7. システム起動

```bash
source venv/bin/activate
python main.py
```

### 8. 自動起動設定（任意）

```bash
# doorbell.service の User と WorkingDirectory を自分のユーザー名に変更してから:
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

## スマートフォン在宅判定

### 🔵 Bluetooth モード（推奨）

Wi-Fi ネットワーク環境に依存せず、Raspi5 の内蔵 Bluetooth で直接スマホを検知します。
エンタープライズ/大学ネットワーク等でも動作します。

```env
# .env 設定
HOME_BT_ADDRESSES=XX:XX:XX:XX:XX:XX   # スマホのBTアドレス（設定→デバイス情報）
PRESENCE_USE_BLUETOOTH=true
```

**スマホのBTアドレス確認（Android）:**
> 設定 → デバイス情報 → Bluetooth アドレス

**ペアリング手順（初回のみ）:**
```bash
bluetoothctl
# [bluetooth]# scan on
# [bluetooth]# pair XX:XX:XX:XX:XX:XX
# [bluetooth]# trust XX:XX:XX:XX:XX:XX
# [bluetooth]# exit
```

### 📡 Wi-Fi モード（家庭内ルーター限定）

> ⚠️ エンタープライズ/大学ネットワークではクライアント間通信がブロックされるため動作しません。
> 家庭用ルーター（クライアントアイソレーションがOFF）環境でのみ使用してください。

```env
HOME_DEVICE_IPS=192.168.1.100   # ルーターで固定割り当てしたスマホIP
PRESENCE_USE_BLUETOOTH=false
```

> ⚠️ **MACアドレスランダム化について**
>
> Android 10以降・iOS 14以降では Wi-Fi 接続時に MAC アドレスをランダム化する機能が
> デフォルトで有効です。Wi-Fi モードを使う場合はこれを無効化し、
> ルーターでスマホの MAC に固定 IP を割り当ててください。

---

## ディレクトリ構成

```
LineBot/
├── main.py                    # メインエントリーポイント
├── config.py                  # ⚙️ 設定ファイル
├── requirements.txt           # Pythonライブラリ一覧
├── setup.sh                   # 環境構築スクリプト
├── doorbell.log               # 実行ログ（起動後生成）
│
├── sensors/
│   ├── pir_sensor.py          # HC-SR501 PIRセンサー
│   └── mailbox_sensor.py      # 郵便受けセンサー
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
│   ├── bluetooth_checker.py   # 🔵 Bluetooth在宅判定（推奨）
│   └── network_checker.py     # 📡 Wi-Fi (ARP/ping) 在宅判定
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
| GPIO エラー | `sudo usermod -aG gpio $USER` でグループ追加後、再ログイン |
| LINE通知が届かない | `python -m notification.line_bot --test` でトークンを確認 |
| Bluetooth在宅判定が動かない | `bluetoothctl` でペアリング済みか確認。`sudo l2ping -c 1 XX:XX:XX` で直接テスト |
| Wi-Fi在宅判定が動かない | 家庭用ルーターでのみ動作。大学/企業ネットワークはクライアント間通信ブロックで不可 |
| pip install が途中で止まる | `venv/bin/pip install torch --index-url https://download.pytorch.org/whl/cpu` で個別インストール |
| YOLOのロードが遅い | 初回のみモデルダウンロードが発生（~6MB）。2回目以降は高速 |
| ログ確認 | `tail -f doorbell.log` |

---

## 📋 テスト方法

各機能の詳細なテスト手順は **[TESTING.md](TESTING.md)** を参照してください。
