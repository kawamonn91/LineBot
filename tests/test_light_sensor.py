import RPi.GPIO as GPIO
import time
import sys

# 光センサーのGPIOピン番号 (物理ピン番号 13)
SENSOR_PIN = 13

def setup():
    # GPIOモードをBOARD(物理ピン番号)に設定
    GPIO.setmode(GPIO.BOARD)
    # センサーピンを入力モードに設定
    GPIO.setup(SENSOR_PIN, GPIO.IN)

def loop():
    try:
        while True:
            # センサーからの入力を読み取る
            # デジタル出力の場合: 光を検知すると0(LOW), 検知しないと1(HIGH)を出力するモジュールが多いです。
            # アナログ出力(ADC経由)を使用している場合は、別途ADCとの通信コードが必要です。
            # ここではデジタル出力を想定しています。
            sensor_state = GPIO.input(SENSOR_PIN)
            
            if sensor_state == GPIO.HIGH:
                print("光を検知しました (明るい)")
            else:
                print("光を検知していません (暗い)")
            
            time.sleep(1) # 1秒ごとに状態をチェック

    except KeyboardInterrupt:
        print("\nテストを終了します。")
    finally:
        # GPIOリソースを解放
        GPIO.cleanup()

if __name__ == '__main__':
    print(f"光センサーのテストを開始します... (使用ピン: GPIO {SENSOR_PIN})")
    print("終了するには Ctrl+C を押してください。")
    setup()
    loop()
