"""
test_light_sensor.py — 光センサー リアルタイム診断ツール

使用方法:
    cd /home/toya/LineBot
    source venv/bin/activate
    python test_light_sensor.py

センサーの現在値を0.2秒ごとに表示します。
郵便受けを手で覆ったり、ライトを当てたりして反応を確認してください。
Ctrl+C で終了。
"""

import sys
import time
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config

try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except (ImportError, RuntimeError):
    GPIO_AVAILABLE = False

GPIO_PIN = config.MAILBOX_GPIO_PIN  # デフォルト GPIO 27

def main():
    print("=" * 50)
    print(f"光センサー診断 (GPIO={GPIO_PIN})")
    print("=" * 50)

    if not GPIO_AVAILABLE:
        print("❌ RPi.GPIO が利用できません（Raspberry Pi 上で実行してください）")
        sys.exit(1)

    GPIO.setmode(GPIO.BCM)
    # 内蔵プルアップを有効化（mailbox_sensor.py と同じ設定）
    GPIO.setup(GPIO_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    print(f"\n GPIO{GPIO_PIN} の状態をリアルタイム表示します。")
    print(" 郵便受けを手で覆ったり、ライトを当てたりして変化を確認してください。")
    print(" Ctrl+C で終了\n")
    print(f"{'時刻':^12} {'GPIO値':^8} {'判定':^12} {'棒グラフ'}")
    print("-" * 55)

    prev_val = None
    try:
        while True:
            raw = bool(GPIO.input(GPIO_PIN))
            val = int(raw)
            label = "明るい ☀" if raw else "暗い 🌑"
            bar = "█" * (20 if raw else 2)

            # 値が変化したときは目立たせる
            changed = (prev_val is not None and raw != prev_val)
            marker = " ← 変化！" if changed else ""

            t = time.strftime("%H:%M:%S")
            print(f"\r{t:^12} {val:^8} {label:^12} {bar:<20}{marker}", end="", flush=True)

            if changed:
                print()  # 変化行は改行して保持

            prev_val = raw
            time.sleep(0.2)

    except KeyboardInterrupt:
        print("\n\n停止しました。")
    finally:
        GPIO.cleanup(GPIO_PIN)

if __name__ == "__main__":
    main()
