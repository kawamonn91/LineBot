"""
sensors/mailbox_sensor.py — 郵便受けセンサー制御（光センサー版）
フォトレジスタ（光センサー）を使って郵便物の投函を検知します。

【接続方法】
ブレッドボード上で以下のように配線してください：

  Raspberry Pi 5          ブレッドボード
  ─────────────           ──────────────────────────────
  3.3V (Pin 1)  ────────── フォトレジスタの片方の足
  GPIO 27 (Pin 13) ─────── フォトレジスタのもう片方の足
                           └── 10kΩ抵抗の片側（同じ列）
  GND (Pin 14)  ────────── 10kΩ抵抗のもう片側

【動作原理】
  郵便受け内が明るい（郵便物なし）
    → フォトレジスタの抵抗値 低
    → GPIO27 の電圧 高 → HIGH (1)

  郵便受け内が暗くなった（郵便物が投函された）
    → フォトレジスタの抵抗値 高
    → GPIO27 の電圧 低 → LOW (0)

  HIGH → LOW への変化（明→暗）を投函として検知
"""

import logging
import time
import threading
from typing import Callable, Optional

logger = logging.getLogger(__name__)

try:
    import RPi.GPIO as GPIO
    _GPIO_AVAILABLE = True
except (ImportError, RuntimeError):
    _GPIO_AVAILABLE = False
    logger.warning("RPi.GPIO が利用できません。シミュレーションモードで動作します。")


class MailboxSensor:
    """
    フォトレジスタ（光センサー）による郵便受け投函検知クラス。

    使用方法:
        def on_delivery(timestamp: float):
            print(f"投函検知！ {timestamp}")

        mailbox = MailboxSensor(gpio_pin=27, on_delivery_callback=on_delivery)
        mailbox.start()
    """

    def __init__(
        self,
        gpio_pin: int,
        on_delivery_callback: Callable[[float], None],
        dark_confirm_sec: float = 2.0,
        debounce_sec: float = 30.0,
        invert_logic: bool = False,
    ):
        """
        Args:
            gpio_pin: BCM形式のGPIOピン番号
            on_delivery_callback: 投函検知時のコールバック (timestamp: float)
            dark_confirm_sec: 暗い状態が続いた場合に投函と確定するまでの時間（秒）
            debounce_sec: 同一イベントの再検知抑制時間（秒）
                          郵便物が入ったままの間は再検知しない
            invert_logic: Trueの場合、センサーの HIGH/LOW を反転させる。
                          GPIO内蔵プルアップを有効にした場合など、
                          光が弱い時にHIGHになる回路構成で使用。
        """
        self.gpio_pin = gpio_pin
        self.on_delivery_callback = on_delivery_callback
        self.dark_confirm_sec = dark_confirm_sec
        self.debounce_sec = debounce_sec
        self.invert_logic = invert_logic

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_delivery_time = 0.0
        self._dark_start_time: Optional[float] = None
        self._last_state: Optional[bool] = None  # True=明るい, False=暗い
        self._delivered = False  # 今回の暗転で既に検知済みか

    def start(self):
        """センサー監視を開始します。"""
        if self._running:
            return
        self._running = True

        if _GPIO_AVAILABLE:
            GPIO.setmode(GPIO.BCM)
            # 内蔵プルアップ（素4 7kΩ・機種により50kΩ程度）を有効化。
            # 外部プルダウン（10kΩ）と分圧することで記GPIO電圧の変化点が下がり、
            # 少ない光量でも HIGH → LOW の遷移を検出できるようになる。
            GPIO.setup(self.gpio_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            logger.info(
                f"郵便受けセンサー（光センサー）開始 "
                f"GPIO={self.gpio_pin} "
                f"[内蔵プルアップ有効・感度高] "
                f"invert_logic={self.invert_logic}"
            )
        else:
            logger.info("郵便受けセンサー シミュレーションモードで開始")

        self._thread = threading.Thread(
            target=self._monitor_loop, name="MailboxSensorThread", daemon=True
        )
        self._thread.start()

    def stop(self):
        """センサー監視を停止します。"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
        if _GPIO_AVAILABLE:
            GPIO.cleanup(self.gpio_pin)
        logger.info("郵便受けセンサー停止")

    def _monitor_loop(self):
        """
        光センサーの状態をポーリングして投函を検知します。

        検知フロー:
          1. HIGH(明るい) → LOW(暗い) の変化を検知
          2. dark_confirm_sec 秒間ずっと暗い状態が続く
          3. 投函確定 → コールバック呼び出し
          4. HIGH(明るい)に戻ると次の投函を待機
        """
        while self._running:
            try:
                current = self._read_sensor()  # True=明るい(HIGH), False=暗い(LOW)
                now = time.time()

                if self._last_state is None:
                    # 初回読み取り
                    self._last_state = current
                    logger.debug(f"郵便受けセンサー初期状態: {'明るい' if current else '暗い'}")

                elif current != self._last_state:
                    # 状態変化
                    if not current:
                        # HIGH → LOW: 暗くなった（投函の可能性）
                        self._dark_start_time = now
                        self._delivered = False
                        logger.debug("郵便受け: 暗くなった（投函待機中）")
                    else:
                        # LOW → HIGH: 明るくなった（郵便物が取り出された）
                        self._dark_start_time = None
                        self._delivered = False
                        logger.debug("郵便受け: 明るくなった（郵便物取り出し or 誤検知リセット）")

                    self._last_state = current

                # 暗い状態が一定時間続いたか確認
                if (
                    not current
                    and self._dark_start_time is not None
                    and not self._delivered
                    and (now - self._dark_start_time) >= self.dark_confirm_sec
                    and (now - self._last_delivery_time) >= self.debounce_sec
                ):
                    # 投函確定！
                    self._delivered = True
                    self._last_delivery_time = now
                    logger.info(
                        f"郵便受け投函検知！ "
                        f"暗転継続={now - self._dark_start_time:.1f}秒"
                    )
                    self.on_delivery_callback(now)

                time.sleep(0.2)  # 200msポーリング

            except Exception as e:
                logger.error(f"郵便受けセンサー監視エラー: {e}")
                time.sleep(1)

    def _read_sensor(self) -> bool:
        """
        センサーの現在の状態を読み取ります。

        Returns:
            True = 明るい (郵便物なし), False = 暗い (投函検知)
        """
        if _GPIO_AVAILABLE:
            raw = bool(GPIO.input(self.gpio_pin))
            # invert_logic=True の場合は極性を反転する
            # （内蔵プルアップ有効時に光が少ないと HIGH になる場合の回路構成用）
            return raw if not self.invert_logic else not raw
        else:
            return True  # シミュレーションモード: 常に明るい
