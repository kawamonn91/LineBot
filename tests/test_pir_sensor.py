import RPi.GPIO as GPIO
import time
import sys
import os

# 上の階層のconfigを読み込むためのパス設定
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
import config

# config.py からピン番号を取得 (BCM 17)
SENSOR_PIN = config.PIR_GPIO_PIN

def setup():
    # GPIOモードをBCMに設定 (LineBot全体でBCMを使用しています)
    GPIO.setmode(GPIO.BCM)
    # センサーピンを入力モードに設定
    GPIO.setup(SENSOR_PIN, GPIO.IN)

def loop():
    try:
        # 前回状態を記憶して、変化した時だけ出力する
        last_state = GPIO.input(SENSOR_PIN)
        if last_state == GPIO.HIGH:
            print("初期状態: 動きを検知しています (HIGH)")
        else:
            print("初期状態: 待機中... (LOW)")

        while True:
            current_state = GPIO.input(SENSOR_PIN)
            
            if current_state != last_state:
                if current_state == GPIO.HIGH:
                    print("🏃 動きを検知しました！ (HIGH)")
                else:
                    print("静止しました (LOW)")
                last_state = current_state
            
            time.sleep(0.1) # 100msごとに状態をチェック

    except KeyboardInterrupt:
        print("\nテストを終了します。")
    finally:
        # GPIOリソースを解放
        GPIO.cleanup()

if __name__ == '__main__':
    print(f"人感センサー(PIR)のテストを開始します... (使用ピン: BCM {SENSOR_PIN})")
    print("終了するには Ctrl+C を押してください。")
    setup()
    loop()
