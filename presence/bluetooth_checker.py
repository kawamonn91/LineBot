"""
presence/bluetooth_checker.py — Bluetooth 近接スキャンによる在宅判定モジュール

Wi-Fi や LAN 環境に依存せず、Raspberry Pi 5 の内蔵 Bluetooth を使って
スマートフォンの存在を検知します。

【仕組み】
  l2ping で登録済みスマホの Bluetooth アドレスに L2CAP エコーを送信し、
  応答があれば「在宅」、一定時間応答がなければ「不在」と判定します。

【事前設定】
  1. スマートフォンの Bluetooth をONにする
  2. Raspi と一度ペアリングする
  3. .env の HOME_BT_ADDRESSES にスマホの BT アドレスを設定

【ペアリング手順（初回のみ）】
  $ bluetoothctl
  [bluetooth]# scan on
  [bluetooth]# pair XX:XX:XX:XX:XX:XX
  [bluetooth]# trust XX:XX:XX:XX:XX:XX
  [bluetooth]# scan off
  [bluetooth]# exit

【デバッグ実行】
  python -m presence.bluetooth_checker --debug
  python -m presence.bluetooth_checker --scan   # 周辺デバイスを探す
"""

import logging
import subprocess
import time
import threading
from typing import Optional, Callable

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

logger = logging.getLogger(__name__)

L2PING_TIMEOUT_SEC = 3    # l2ping 1回のタイムアウト（秒）
ABSENT_FAIL_COUNT = 3     # N回連続失敗で不在確定（誤検知防止）


class BluetoothPresenceChecker:
    """
    Bluetooth (l2ping) によるスマートフォン在宅判定クラス。
    NetworkPresenceChecker と同一インターフェースを持ち、差し替え可能です。

    使用方法:
        def on_change(is_home: bool):
            print("在宅" if is_home else "不在")

        checker = BluetoothPresenceChecker(on_change_callback=on_change)
        checker.start()
        print(checker.is_home)
    """

    def __init__(
        self,
        bt_addresses: list = None,
        check_interval_sec: float = None,
        on_change_callback: Optional[Callable[[bool], None]] = None,
    ):
        self.bt_addresses = bt_addresses or config.HOME_BT_ADDRESSES
        self.check_interval = (
            check_interval_sec or config.PRESENCE_CHECK_INTERVAL_SEC
        )
        self.on_change_callback = on_change_callback
        self._is_home: Optional[bool] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._fail_counts: dict = {addr: 0 for addr in self.bt_addresses}

    def start(self):
        """在宅チェックループを開始します。"""
        if self._running:
            return
        if not self.bt_addresses:
            logger.warning("HOME_BT_ADDRESSES が未設定です。Bluetooth 在宅判定を無効化します。")
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._check_loop,
            name="BluetoothPresenceCheckerThread",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            f"Bluetooth 在宅チェック開始: 対象={self.bt_addresses} "
            f"間隔={self.check_interval}秒"
        )

    def stop(self):
        """在宅チェックループを停止します。"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=10)
        logger.info("Bluetooth 在宅チェック停止")

    @property
    def is_home(self) -> Optional[bool]:
        """現在の在宅状態を返します。未判定の場合は None。"""
        with self._lock:
            return self._is_home

    def check_now(self) -> bool:
        """即座に在宅チェックを実行して結果を返します（デバッグ用）。"""
        result = self._scan_all_devices()
        with self._lock:
            self._is_home = result
        return result

    def _check_loop(self):
        """定期的にデバイスの存在確認を行うループ。"""
        while self._running:
            try:
                current = self._scan_all_devices()
                with self._lock:
                    previous = self._is_home
                    self._is_home = current
                if previous != current and self.on_change_callback:
                    status = "在宅" if current else "不在"
                    logger.info(f"Bluetooth 在宅状態変化: {status}")
                    try:
                        self.on_change_callback(current)
                    except Exception as e:
                        logger.error(f"在宅コールバックエラー: {e}")
                time.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"Bluetooth 在宅チェックエラー: {e}")
                time.sleep(self.check_interval)

    def _scan_all_devices(self) -> bool:
        """
        登録済み全デバイスをスキャン。
        誤検知防止のため ABSENT_FAIL_COUNT 回連続失敗で不在確定。
        """
        if not self.bt_addresses:
            logger.warning("HOME_BT_ADDRESSES が未設定です。常に不在と判定します。")
            return False

        for addr in self.bt_addresses:
            if self._l2ping(addr):
                self._fail_counts[addr] = 0
                logger.debug(f"Bluetooth 検出: {addr} → 在宅")
                return True
            else:
                self._fail_counts[addr] = self._fail_counts.get(addr, 0) + 1
                count = self._fail_counts[addr]
                logger.debug(
                    f"Bluetooth 未検出: {addr} "
                    f"(連続失敗 {count}/{ABSENT_FAIL_COUNT})"
                )
                if count < ABSENT_FAIL_COUNT:
                    # まだ確定していない → 前回の状態を維持
                    with self._lock:
                        return self._is_home if self._is_home is not None else False

        logger.debug(f"全デバイス不在確定 (連続失敗 >= {ABSENT_FAIL_COUNT})")
        return False

    def _l2ping(self, bt_address: str) -> bool:
        """
        l2ping で Bluetooth アドレスに L2CAP エコーを送信します。
        ペアリング済みデバイスはスリープ中でも応答します。

        Args:
            bt_address: Bluetooth アドレス (例: "AA:BB:CC:DD:EE:FF")
        Returns:
            応答があれば True
        """
        try:
            result = subprocess.run(
                ["sudo", "l2ping", "-c", "1", "-t", str(L2PING_TIMEOUT_SEC), bt_address],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=L2PING_TIMEOUT_SEC + 2,
            )
            return result.returncode == 0
        except subprocess.TimeoutExpired:
            logger.debug(f"l2ping タイムアウト: {bt_address}")
            return False
        except FileNotFoundError:
            logger.error("l2ping コマンドが見つかりません。sudo apt install bluez でインストール")
            return False
        except Exception as e:
            logger.debug(f"l2ping エラー ({bt_address}): {e}")
            return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    if "--debug" in sys.argv:
        print(f"対象デバイス: {config.HOME_BT_ADDRESSES}")
        if not config.HOME_BT_ADDRESSES:
            print("⚠️  HOME_BT_ADDRESSES が未設定です。.env を確認してください。")
            sys.exit(1)
        checker = BluetoothPresenceChecker()
        result = checker.check_now()
        print(f"在宅状態: {'✅ 在宅' if result else '❌ 不在'}")

    elif "--scan" in sys.argv:
        print("周辺の Bluetooth デバイスをスキャン中... (10秒)")
        print("スマートフォンの Bluetooth を ON にして画面をつけてください。\n")
        proc = subprocess.Popen(
            ["sudo", "hcitool", "scan", "--length=10"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        stdout, _ = proc.communicate()
        print(stdout or "デバイスが見つかりませんでした。")
        print("上記のアドレスを .env の HOME_BT_ADDRESSES に設定してください。")

    else:
        print("使用方法:")
        print("  python -m presence.bluetooth_checker --debug   # 在宅判定テスト")
        print("  python -m presence.bluetooth_checker --scan    # 周辺デバイスを探す")
