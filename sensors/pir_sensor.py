"""
sensors/pir_sensor.py — HC-SR501 PIRセンサー制御
人の動きを検知し、コールバック関数を呼び出します。
"""

import logging
import time
import threading
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# Raspberry Pi 環境かどうかを判定
try:
    import RPi.GPIO as GPIO
    _GPIO_AVAILABLE = True
except (ImportError, RuntimeError):
    _GPIO_AVAILABLE = False
    logger.warning("RPi.GPIO が利用できません。シミュレーションモードで動作します。")


class PIRSensor:
    """
    HC-SR501 PIRセンサーの制御クラス。

    使用方法:
        def on_motion(active: bool):
            if active:
                print("動き検知！")
            else:
                print("動き終了")

        pir = PIRSensor(gpio_pin=17, on_motion_callback=on_motion)
        pir.start()
        # ... メインループ ...
        pir.stop()
    """

    def __init__(
        self,
        gpio_pin: int,
        on_motion_callback: Callable[[bool], None],
        debounce_sec: float = 2.0,
    ):
        """
        Args:
            gpio_pin: BCM形式のGPIOピン番号
            on_motion_callback: 動き検知時に呼ばれるコールバック (active: bool)
            debounce_sec: デバウンス時間（秒）— 誤検知防止
        """
        self.gpio_pin = gpio_pin
        self.on_motion_callback = on_motion_callback
        self.debounce_sec = debounce_sec
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_state = False
        self._last_trigger_time = 0.0

    def start(self):
        """センサー監視を開始します。"""
        if self._running:
            return
        self._running = True

        if _GPIO_AVAILABLE:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.gpio_pin, GPIO.IN)
            logger.info(f"PIRセンサー開始 GPIO={self.gpio_pin}")
        else:
            logger.info("PIRセンサー シミュレーションモードで開始")

        self._thread = threading.Thread(
            target=self._monitor_loop, name="PIRSensorThread", daemon=True
        )
        self._thread.start()

    def stop(self):
        """センサー監視を停止します。"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
        if _GPIO_AVAILABLE:
            GPIO.cleanup(self.gpio_pin)
        logger.info("PIRセンサー停止")

    def _monitor_loop(self):
        """GPIO状態を定期的にポーリングして変化を検知します。"""
        while self._running:
            try:
                current_state = self._read_sensor()
                now = time.time()

                # デバウンス: 前回トリガーから一定時間経過後のみ処理
                if current_state != self._last_state:
                    if now - self._last_trigger_time >= self.debounce_sec:
                        self._last_state = current_state
                        self._last_trigger_time = now
                        logger.debug(
                            f"PIR状態変化: {'検知' if current_state else '非検知'}"
                        )
                        self.on_motion_callback(current_state)

                time.sleep(0.1)  # 100msポーリング
            except Exception as e:
                logger.error(f"PIRセンサー監視エラー: {e}")
                time.sleep(1)

    def _read_sensor(self) -> bool:
        """センサーの現在の状態を読み取ります。"""
        if _GPIO_AVAILABLE:
            return bool(GPIO.input(self.gpio_pin))
        else:
            # シミュレーションモード: 常にFalseを返す
            return False

    @property
    def is_active(self) -> bool:
        """現在センサーがアクティブ（検知中）かどうかを返します。"""
        return self._last_state
