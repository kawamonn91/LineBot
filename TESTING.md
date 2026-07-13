# 🧪 テストガイド — 玄関モニタリングシステム

各機能の単体テスト方法をまとめています。  
すべてのコマンドは **プロジェクトルート** (`~/LineBot`) から実行してください。

---

## 🔧 共通の準備

```bash
# ① プロジェクトルートに移動
cd ~/LineBot

# ② 仮想環境を有効化（毎回必要）
source venv/bin/activate

python main.py
```

> **注意**: `cd ~/LineBot/presence` のようにサブディレクトリに移動した状態でモジュールを実行すると `ModuleNotFoundError` になります。常に `~/LineBot` から実行してください。

---

## 1. 📲 LINE 接続テスト

トークンが正しく設定されているか、メッセージが届くか確認します。

```bash
python -m notification.line_bot --test
```

**期待する出力:**
```
LINEテストメッセージを送信中...
✅ 送信成功
```

**失敗した場合:**
- `.env` の `LINE_CHANNEL_ACCESS_TOKEN` と `LINE_USER_ID` を確認
- `cat .env` で値が設定されているか確認

---

## 2. 📷 カメラ撮影 → LINE 画像送信テスト

カメラで撮影した画像を実際に LINE に送信します。

```bash
python test_camera_send.py
```

**期待する出力:**
```
[1/5] 設定確認...       ✅ TOKEN / USER_ID 確認済み
[2/5] カメラ起動...     ✅ カメラ起動成功
[3/5] フレーム取得中... ✅ フレーム取得成功: 1280x720 px
[4/5] テスト画像保存... ✅ 保存完了: data/images/test_capture.jpg
[5/5] LINE送信中...     ✅ アップロード成功 → LINE送信成功
```

**保存された画像の確認:**
```bash
ls -lh data/images/test_capture.jpg
```

**失敗した場合:**
| 症状 | 確認事項 |
|------|---------|
| カメラを開けない | `ls /dev/video*` でデバイス確認。`config.py` の `CAMERA_INDEX` を変更 |
| フレームが None | カメラの接続を確認、3秒待機でも取得できない場合は再接続 |
| imgur 400 エラー | ネットワーク接続を確認 |
| LINE 401 エラー | `LINE_CHANNEL_ACCESS_TOKEN` が期限切れまたは誤り |

---

## 3. 🏠 在宅判定テスト（Bluetooth モード）

スマートフォンの Bluetooth アドレスに l2ping を送り、在宅状態を判定します。

### 事前準備（初回のみ）

Raspberry Pi とスマートフォンを一度ペアリングしてください：

```bash
bluetoothctl
```
```
[bluetooth]# scan on
# スマホの BT アドレス（例: AA:BB:CC:DD:EE:FF）を確認したら:
[bluetooth]# pair AA:BB:CC:DD:EE:FF
[bluetooth]# trust AA:BB:CC:DD:EE:FF
[bluetooth]# scan off
[bluetooth]# exit
```

確認したアドレスを `.env` に設定してください：
```
HOME_BT_ADDRESSES=AA:BB:CC:DD:EE:FF
PRESENCE_USE_BLUETOOTH=true
```

---

### 3-1. 周辺デバイスのスキャン（アドレス確認）

```bash
python -m presence.bluetooth_checker --scan
```

**期待する出力:**
```
周辺の Bluetooth デバイスをスキャン中... (10秒)
スマートフォンの Bluetooth を ON にして画面をつけてください。

AA:BB:CC:DD:EE:FF    Taro's iPhone
上記のアドレスを .env の HOME_BT_ADDRESSES に設定してください。
```

---

### 3-2. 在宅判定テスト

```bash
python -m presence.bluetooth_checker --debug
```

**期待する出力（在宅時）:**
```
対象デバイス: ['AA:BB:CC:DD:EE:FF']
DEBUG: Bluetooth 検出: AA:BB:CC:DD:EE:FF → 在宅
在宅状態: ✅ 在宅
```

**期待する出力（不在時）:**
```
対象デバイス: ['AA:BB:CC:DD:EE:FF']
DEBUG: Bluetooth 未検出: AA:BB:CC:DD:EE:FF (連続失敗 3/3)
在宅状態: ❌ 不在
```

**失敗した場合:**
| 症状 | 確認事項 |
|------|---------|
| `HOME_BT_ADDRESSES が未設定` | `.env` の `HOME_BT_ADDRESSES` を設定 |
| `l2ping コマンドが見つかりません` | `sudo apt install bluez` でインストール |
| 常に不在と判定される | スマホの Bluetooth が ON になっているか確認。ペアリング済みか `bluetoothctl` で確認 |
| 常に在宅と判定される | `.env` の `PRESENCE_USE_BLUETOOTH=true` が設定されているか確認 |

---

## 4. 💡 光センサー（郵便受け）リアルタイム診断

センサーの現在値をリアルタイムで表示します。  
手で覆ったり、ライトを当てたりして反応を確認できます。

```bash
python test_light_sensor.py
```

**期待する出力:**
```
時刻         GPIO値    判定          棒グラフ
-----------------------------------------------
11:30:01      1      明るい ☀    ████████████████████
11:30:05      0      暗い 🌑     ██                    ← 変化！
11:30:08      1      明るい ☀    ████████████████████  ← 変化！
```

**Ctrl+C で終了**

**判断基準:**

| 操作 | 期待する変化 |
|------|------------|
| 何もしない（通常の室内光） | 明るい ☀ (1) |
| 手でセンサーを覆う | 暗い 🌑 (0) |
| スマホライトを当てる | 明るい ☀ (1) |

**常に「暗い」と表示される場合:**  
内蔵プルアップにより信号が反転している可能性があります。`main.py` で以下を設定してください：
```python
self._mailbox = MailboxSensor(
    gpio_pin=config.MAILBOX_GPIO_PIN,
    on_delivery_callback=self._on_mailbox_delivery,
    invert_logic=True,   # ← 追加
)
```

---

## 5. 📊 日次レポート即時送信テスト

毎日 19 時に送信される日次レポートを、今すぐ手動で送信します。

```bash
python -m scheduler.daily_report --send-now
```

**期待する動作:**  
LINE に本日分の訪問者集計レポートが届く。  
（データベースが空の場合は「訪問者: 0件」のレポートが届きます）

---

## 6. 🤖 YOLO 物体検出テスト

YOLOv8 モデルのロードと推論が正常に動作するか確認します。

```bash
python -c "
from detection.yolo_detector import YOLODetector
import logging
logging.basicConfig(level=logging.INFO)
detector = YOLODetector()
detector.load()
print('✅ YOLOモデルロード成功:', detector.is_loaded)
"
```

**期待する出力:**
```
INFO: YOLOモデルロード完了
✅ YOLOモデルロード成功: True
```

> 初回実行時はモデルファイル（約6MB）を自動ダウンロードします。

---

## 7. 🗄️ データベース確認

SQLite に記録されている訪問者データを確認します。

```bash
# 訪問者一覧（直近10件）
python -c "
from database import db_manager
db_manager.initialize_db()
import sqlite3, config
conn = sqlite3.connect(config.DB_PATH)
conn.row_factory = sqlite3.Row
rows = conn.execute('SELECT * FROM visitors ORDER BY id DESC LIMIT 10').fetchall()
for r in rows:
    print(dict(r))
conn.close()
"
```

**データが空の場合:**
```
（出力なし）
```

---

## 8. 🔔 PIR センサー動作確認

PIR センサー（HC-SR501）が動きを検知しているか確認します。

```bash
python -c "
import time, logging
logging.basicConfig(level=logging.DEBUG)
from sensors.pir_sensor import PIRSensor

def on_motion(active):
    print('🔔 動き検知！' if active else '  動き終了')

pir = PIRSensor(gpio_pin=17, on_motion_callback=on_motion)
pir.start()
print('PIRセンサー監視中... センサーの前を通過してください。Ctrl+C で終了')
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    pir.stop()
"
```

---

## 9. 🔄 システム全体の起動テスト

全モジュールを統合して起動します。

```bash
python main.py
```

**正常起動時のログ:**
```
✅ 全モジュール起動完了。監視中...
   PIR GPIO: 17
   郵便受け GPIO: 27
   在宅チェック対象: ['172.21.8.77']
   日次レポート時刻: 19:00
   停止: Ctrl+C
```

**ログをリアルタイムで確認:**
```bash
# 別ターミナルで実行
tail -f doorbell.log
```

**Ctrl+C で安全に停止**

---

## ✅ テスト実行順序（推奨）

初めて動作確認する場合は以下の順序で進めてください：

```
1. LINE 接続テスト                    → 通知インフラの確認
2. カメラ撮影 → LINE 送信テスト       → 画像送信の確認
3-1. BT スキャン（初回のみ）          → スマホの BT アドレス確認
3-2. 在宅判定テスト（Bluetooth）      → 在宅検知の確認
4. 光センサー診断                     → 郵便受けセンサーの確認
5. 日次レポートテスト                 → レポート機能の確認
6. システム全体起動                   → 統合動作の確認
```

---

## 🐛 よくあるエラーと対処法

| エラー | 原因 | 対処 |
|--------|------|------|
| `ModuleNotFoundError: No module named 'presence'` | サブディレクトリから実行している | `cd ~/LineBot` してから実行 |
| `ModuleNotFoundError: No module named 'cv2'` | OpenCV 未インストール | `pip install opencv-python-headless` |
| `LINE_CHANNEL_ACCESS_TOKEN が未設定` | `.env` が読み込まれていない | `source venv/bin/activate` で venv を有効化 |
| `カメラを開けませんでした` | カメラが接続されていない or インデックスが違う | `ls /dev/video*` で確認し `config.py` の `CAMERA_INDEX` を変更 |
| `RuntimeError: Not running on a RPi!` | GPIO を PC 上で実行した | Raspberry Pi 上で実行する（センサー以外は PC でも動作可） |
| `l2ping コマンドが見つかりません` | bluez 未インストール | `sudo apt install bluez` でインストール |
| Bluetooth 在宅判定が常に不在 | ペアリング未実施 or スマホの BT が OFF | `bluetoothctl` でペアリング、スマホの BT を ON に |
| `GPIO busy` | 別プロセスが GPIO を使用中 | `ps aux | grep python` で確認し、重複プロセスを `kill <PID>` で停止 |
