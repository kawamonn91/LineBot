"""
presence/network_checker.py — スマートフォン在宅判定モジュール
ARP/Pingスキャンで登録済みデバイスのネットワーク存在を確認します。

【事前設定】
1. ルーターでスマートフォンにIPアドレスを固定割り当て（MACアドレス指定）
2. スマートフォンのWi-Fi設定 →「プライベートWi-Fiアドレス」を無効化
3. config.py の HOME_DEVICE_IPS に固定IPを追加

【検知方式】
1次: ping (ICMP) で応答確認
2次: ARP テーブルを参照してMACアドレスが存在するか確認
いずれかのデバイスが1台以上検出されれば「在宅」と判定
"""

import logging
import subprocess
import time
import threading
import platform
from typing import Optional, Callable

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

logger = logging.getLogger(__name__)

_IS_LINUX = platform.system() == "Linux"


class NetworkPresenceChecker:
    """
    ネットワークスキャンによるスマートフォン在宅判定クラス。

    使用方法:
        def on_presence_change(is_home: bool):
            print(f"在宅状態変化: {'在宅' if is_home else '不在'}")

        checker = NetworkPresenceChecker(on_change_callback=on_presence_change)
        checker.start()
        is_home = checker.is_home  # 現在の在宅状態を取得
    """

    def __init__(
        self,
        device_ips: list[str] = None,
        check_interval_sec: float = None,
        on_change_callback: Optional[Callable[[bool], None]] = None,
    ):
        """
        Args:
            device_ips: スキャン対象のIPアドレスリスト
            check_interval_sec: チェック間隔（秒）
            on_change_callback: 在宅状態が変化した時のコールバック (is_home: bool)
        """
        self.device_ips = device_ips or config.HOME_DEVICE_IPS
        self.check_interval = check_interval_sec or config.PRESENCE_CHECK_INTERVAL_SEC
        self.on_change_callback = on_change_callback
        self._is_home: Optional[bool] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def start(self):
        """在宅チェックループを開始します。"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._check_loop, name="PresenceCheckerThread", daemon=True
        )
        self._thread.start()
        logger.info(
            f"在宅チェック開始: 対象IP={self.device_ips} "
            f"間隔={self.check_interval}秒"
        )

    def stop(self):
        """在宅チェックループを停止します。"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("在宅チェック停止")

    @property
    def is_home(self) -> Optional[bool]:
        """現在の在宅状態を返します。未判定の場合はNone。"""
        with self._lock:
            return self._is_home

    def _check_loop(self):
        """定期的にデバイスの存在確認を行うループ。"""
        while self._running:
            try:
                current = self._scan_all_devices()

                with self._lock:
                    previous = self._is_home
                    self._is_home = current

                # 状態変化があればコールバックを呼ぶ
                if previous != current and self.on_change_callback:
                    status = "在宅" if current else "不在"
                    logger.info(f"在宅状態変化: {status}")
                    try:
                        self.on_change_callback(current)
                    except Exception as e:
                        logger.error(f"在宅コールバックエラー: {e}")

                time.sleep(self.check_interval)

            except Exception as e:
                logger.error(f"在宅チェックエラー: {e}")
                time.sleep(self.check_interval)

    def _scan_all_devices(self) -> bool:
        """
        登録済み全デバイスをスキャンし、
        1台以上見つかれば True (在宅) を返します。
        """
        if not self.device_ips:
            logger.warning("HOME_DEVICE_IPS が設定されていません。常に不在と判定します。")
            return False

        for ip in self.device_ips:
            if self._ping(ip) or self._arp_check(ip):
                logger.debug(f"デバイス検出: {ip} → 在宅")
                return True

        logger.debug(f"全デバイス未検出 {self.device_ips} → 不在")
        return False

    def _ping(self, ip: str) -> bool:
        """
        ICMPピングでデバイスの応答を確認します。

        Returns:
            応答があればTrue
        """
        try:
            if _IS_LINUX:
                cmd = ["ping", "-c", "1", "-W", "2", ip]
            else:
                # Windows用
                cmd = ["ping", "-n", "1", "-w", "2000", ip]

            result = subprocess.run(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
            )
            return result.returncode == 0
        except subprocess.TimeoutExpired:
            return False
        except Exception as e:
            logger.debug(f"ping エラー ({ip}): {e}")
            return False

    def _arp_check(self, ip: str) -> bool:
        """
        ARPテーブルを参照してデバイスの存在を確認します。
        ping で応答しないiPhone等のスリープ端末に有効です。

        Returns:
            ARPテーブルにエントリがあればTrue
        """
        try:
            if _IS_LINUX:
                result = subprocess.run(
                    ["arp", "-n", ip],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                # "no entry" や "(incomplete)" は未検出とみなす
                output = result.stdout.lower()
                return (
                    ip in output
                    and "no entry" not in output
                    and "incomplete" not in output
                )
            else:
                result = subprocess.run(
                    ["arp", "-a", ip],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                return ip in result.stdout and "No ARP" not in result.stdout

        except Exception as e:
            logger.debug(f"ARP確認エラー ({ip}): {e}")
            return False

    def check_now(self) -> bool:
        """
        即座に在宅チェックを実行して結果を返します（デバッグ用）。
        """
        result = self._scan_all_devices()
        with self._lock:
            self._is_home = result
        return result


# コマンドライン実行時のデバッグ機能
if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.DEBUG)

    if "--debug" in sys.argv:
        print(f"対象デバイス: {config.HOME_DEVICE_IPS}")
        checker = NetworkPresenceChecker()
        result = checker.check_now()
        print(f"在宅状態: {'✅ 在宅' if result else '❌ 不在'}")
    else:
        print("使用方法: python -m presence.network_checker --debug")
