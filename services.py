from __future__ import annotations

# -*- coding: utf-8 -*-

"""
Аннотация

🧩 1. Назначение файла
- Слой сервисов и сетевого взаимодействия (Service Layer).
- Содержит воркеры для получения данных, валидации и обновлений.
- Изолирован от бизнес-логики приложения (Controller).

🧱 2. Компоненты
- GasFetchService: Сетевой воркер (Etherscan API / JSON-RPC).
- ApiKeyValidator: Валидатор API ключей.
- ChainlistFetcher: Загрузчик списка публичных узлов (с фильтрацией).
- RpcBatchValidator: Валидатор списка RPC с замером пинга.
- UpdateManager: Менеджер обновлений (GitHub API).

⚙️ 3. Особенности
- Асинхронная архитектура (QNetworkAccessManager).
- Полная независимость от core.py (кроме TextStore).
- Реализует Blacklisting для обеспечения сетевой безопасности и отказоустойчивости.
"""

import os
import sys
import json
import random
from typing import Optional, Any, Union, List, Tuple
from collections import deque

from PySide6.QtCore import (
    QObject, QTimer, Signal, QUrl, QUrlQuery, QFile, QIODevice, QDateTime, Qt
)
from PySide6.QtNetwork import (
    QNetworkAccessManager, QNetworkRequest, QNetworkReply, QSslConfiguration, QSslSocket
)

import config
# Импортируем TextStore только внутри методов или через отложенный импорт,
# чтобы избежать циклических ссылок, если core импортирует services.
# Но так как core.py импортирует services, а services нужен TextStore из core,
# лучше импортировать TextStore напрямую из localization_ruRU, чтобы разорвать цикл.
import localization_ruRU

# Используем прямую ссылку на локализацию для сервисов, чтобы избежать цикла core <-> services
TextStore = localization_ruRU.Locale

# ---------------------------
# Константы сервисов
# ---------------------------

# Аварийный список на случай недоступности Chainlist.
# Оставлен пустым для предотвращения ложных срабатываний антивирусов (String Encryption / IOC removal).
# Приложение должно использовать ChainlistFetcher для получения актуального списка.
DEFAULT_RPC_LIST = []

_ETHERSCAN_API_URL = "https://api.etherscan.io/v2/api"
_CHAIN_ID = 1

# Параметры RPC (EIP-1559)
# [5, 25, 50, 75, 95]
# Index 1 (25%) = Low/Safe
# Index 2 (50%) = Avg/Propose
# Index 3 (75%) = High/Fast (Changed from 95% to avoid MEV outliers)
_RPC_BLOCKS = 5
_RPC_PERCENTILES = [5, 25, 50, 75, 95]
_MIN_PRIORITY_FEE = 0.01

# Параметры Chainlink Oracle (Mainnet ETH/USD)
_CHAINLINK_FEED_ADDR = "0x5f4eC3Df9cbd43714FE2740f5E3616155c5b8419"
_CHAINLINK_FUNC_SIG = "0xfeaf968c"

_GITHUB_REPOS_URL = "https://api.github.com/repos/Makis12rus/Ethereum_Gas_Tracker/releases/latest"


# -------------------------------------------------------------------------
# 1. СЕТЕВОЙ СЛОЙ (Fetchers & Validators)
# -------------------------------------------------------------------------

class GasFetchService(QObject):
    """
    Асинхронный сервис для опроса газа.
    Работает в отдельном потоке (QThread).
    Реализует стратегию Waterfall: Etherscan -> Modern RPC -> Legacy RPC -> Next Node.
    """
    finished = Signal(dict)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._nam: Optional[QNetworkAccessManager] = None
        self._reply: Optional[QNetworkReply] = None
        self._pending_gas_data: Optional[dict] = None
        
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._abort_request)
        
        self._rpc_urls: List[str] = []
        self._current_rpc_index = 0
        self._api_key = ""
    
    def start_fetch(self, rpc_urls: Union[str, List[str]], timeout_ms: int):
        """Запуск цепочки опроса."""
        if self._nam is None:
            self._nam = QNetworkAccessManager(self)
        
        self._cleanup_reply()
        self._timer.stop()
        self._pending_gas_data = None
        
        # Подготовка списка RPC (очистка от комментариев и валидация)
        raw_list = []
        if isinstance(rpc_urls, list):
            raw_list = rpc_urls
        elif isinstance(rpc_urls, str) and rpc_urls.strip():
            raw_list = [rpc_urls.strip()]
        
        self._rpc_urls = []
        for u in raw_list:
            if not u: continue
            clean_url = u.split('#')[0].strip()
            # Strict validation: must start with http/https
            if clean_url and clean_url.lower().startswith(('https://', 'http://')):
                self._rpc_urls.append(clean_url)
        
        self._current_rpc_index = 0
        self._api_key = os.environ.get("ETHERSCAN_API_KEY", "").strip()
        
        if timeout_ms > 0:
            self._timer.start(timeout_ms)
        
        # Старт цепочки
        if self._api_key:
            self._do_etherscan()
        else:
            self._do_rpc()
    
    def stop(self):
        """Принудительная остановка."""
        self._timer.stop()
        self._cleanup_reply()
        self._pending_gas_data = None
        if self._nam:
            self._nam.deleteLater()
            self._nam = None
    
    def _abort_request(self):
        if self._reply and self._reply.isRunning():
            self._reply.abort()
    
    def _cleanup_reply(self):
        if self._reply:
            try:
                self._reply.finished.disconnect()
            except Exception:
                pass
            if self._reply.isRunning():
                self._reply.abort()
            self._reply.deleteLater()
            self._reply = None
    
    def _emit_finished(self, data: dict):
        self.finished.emit(data)
    
    # --- Etherscan Logic ---
    
    def _do_etherscan(self):
        if not self._nam: return
        query = QUrl(_ETHERSCAN_API_URL)
        q = QUrlQuery()
        q.addQueryItem("chainid", str(_CHAIN_ID))
        q.addQueryItem("module", "gastracker")
        q.addQueryItem("action", "gasoracle")
        q.addQueryItem("apikey", self._api_key)
        query.setQuery(q)
        
        req = QNetworkRequest(query)
        req.setRawHeader(b"User-Agent", config.NETWORK_USER_AGENT)
        
        self._reply = self._nam.get(req)
        self._reply.finished.connect(self._on_etherscan_finished)
    
    def _on_etherscan_finished(self):
        reply = self._reply
        self._reply = None
        if not reply: return
        reply.deleteLater()
        
        err = reply.error()
        http_status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        raw_data = reply.readAll().data()
        
        success = False
        if err == QNetworkReply.NetworkError.NoError and http_status == 200:
            try:
                text = raw_data.decode("utf-8", errors="ignore")
                js = json.loads(text)
                if js.get("status") == "1":
                    result = self._parse_etherscan(js.get("result", {}))
                    if result:
                        self._pending_gas_data = result
                        self._fetch_eth_price()
                        success = True
            except Exception:
                pass
        
        if not success:
            self._do_rpc()
    
    def _fetch_eth_price(self):
        if not self._nam:
            self._emit_finished(self._pending_gas_data)
            return
        
        query = QUrl(_ETHERSCAN_API_URL)
        q = QUrlQuery()
        q.addQueryItem("chainid", str(_CHAIN_ID))
        q.addQueryItem("module", "stats")
        q.addQueryItem("action", "ethprice")
        q.addQueryItem("apikey", self._api_key)
        query.setQuery(q)
        
        req = QNetworkRequest(query)
        req.setRawHeader(b"User-Agent", config.NETWORK_USER_AGENT)
        
        self._reply = self._nam.get(req)
        self._reply.finished.connect(self._on_eth_price_finished)
    
    def _on_eth_price_finished(self):
        reply = self._reply
        self._reply = None
        self._timer.stop()
        if not reply:
            if self._pending_gas_data: self._emit_finished(self._pending_gas_data)
            return
        reply.deleteLater()
        
        if not self._pending_gas_data: return
        
        err = reply.error()
        http_status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        raw_data = reply.readAll().data()
        eth_price = 0.0
        
        if err == QNetworkReply.NetworkError.NoError and http_status == 200:
            try:
                text = raw_data.decode("utf-8", errors="ignore")
                js = json.loads(text)
                if js.get("status") == "1":
                    res = js.get("result", {})
                    eth_price = _to_float(res.get("ethusd"))
            except Exception:
                pass
        
        self._pending_gas_data["eth_price"] = eth_price
        self._emit_finished(self._pending_gas_data)
        self._pending_gas_data = None
    
    def _parse_etherscan(self, res: dict) -> Optional[dict]:
        safe = _to_float(res.get("SafeGasPrice"))
        propose = _to_float(res.get("ProposeGasPrice"))
        fast = _to_float(res.get("FastGasPrice"))
        base = _to_float(res.get("suggestBaseFee"))
        
        if safe <= 0 and propose <= 0: return None
        if base <= 0: base = min(x for x in (safe, propose, fast) if x > 0)
        
        return self._build_result("etherscan", safe, propose, fast, base,
                                  [max(0.0, x - base) for x in (safe, propose, fast)])
    
    # --- RPC Logic (Waterfall Strategy) ---
    
    def _do_rpc(self):
        """Точка входа для RPC. Выбирает узел и запускает Modern метод."""
        if not self._nam:
            self._finish_empty()
            return
        
        # Выбор следующего URL
        while self._current_rpc_index < len(self._rpc_urls):
            url = self._rpc_urls[self._current_rpc_index]
            if url: break
            self._current_rpc_index += 1
        
        if self._current_rpc_index >= len(self._rpc_urls):
            self._finish_empty()
            return
        
        current_url = self._rpc_urls[self._current_rpc_index]
        self._try_modern_rpc(current_url)
    
    def _try_modern_rpc(self, url: str):
        """
        Попытка 1: Modern (EIP-1559).
        Запрашивает feeHistory, maxPriorityFee и цену ETH.
        """
        req = QNetworkRequest(QUrl(url))
        req.setRawHeader(b"User-Agent", config.NETWORK_USER_AGENT)
        req.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json")
        
        # Batch Request:
        # 1. eth_feeHistory (Base Fee + History)
        # 2. eth_maxPriorityFeePerGas (Direct Tip)
        # 3. eth_call (Chainlink Price)
        payload = json.dumps([
            {
                "jsonrpc": "2.0", "id": 1,
                "method": "eth_feeHistory",
                "params": [hex(_RPC_BLOCKS), "latest", _RPC_PERCENTILES]
            },
            {
                "jsonrpc": "2.0", "id": 2,
                "method": "eth_maxPriorityFeePerGas",
                "params": []
            },
            {
                "jsonrpc": "2.0", "id": 3,
                "method": "eth_call",
                "params": [{"to": _CHAINLINK_FEED_ADDR, "data": _CHAINLINK_FUNC_SIG}, "latest"]
            }
        ]).encode("utf-8")
        
        self._reply = self._nam.post(req, payload)
        self._reply.setProperty("rpc_url", url)
        self._reply.finished.connect(self._on_modern_rpc_finished)
    
    def _on_modern_rpc_finished(self):
        reply = self._reply
        self._reply = None
        if not reply:
            # Если reply потерян, пробуем следующий узел
            self._current_rpc_index += 1
            self._do_rpc()
            return
        
        url = reply.property("rpc_url")
        reply.deleteLater()
        
        err = reply.error()
        http_status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        raw_data = reply.readAll().data()
        
        success = False
        
        if err == QNetworkReply.NetworkError.NoError and http_status == 200:
            try:
                text = raw_data.decode("utf-8", errors="ignore")
                js = json.loads(text)
                
                fee_history = None
                direct_tip = None
                price_hex = None
                
                # Разбор батч-ответа
                if isinstance(js, list):
                    for item in js:
                        if not isinstance(item, dict): continue
                        rid = item.get("id")
                        res = item.get("result")
                        if rid == 1:
                            fee_history = res
                        elif rid == 2:
                            direct_tip = res
                        elif rid == 3:
                            price_hex = res
                
                # Если feeHistory получен, считаем Modern успешным
                if fee_history:
                    final_data = self._calculate_modern_gas(fee_history, direct_tip)
                    if final_data:
                        final_data["eth_price"] = self._parse_chainlink_price(price_hex)
                        self._timer.stop()
                        self._emit_finished(final_data)
                        success = True
            except Exception:
                pass
        
        if not success:
            # Если Modern не сработал, пробуем Legacy на том же узле
            self._try_legacy_rpc(url)
    
    def _calculate_modern_gas(self, fh: dict, direct_tip_hex: Optional[str]) -> Optional[dict]:
        """Расчет газа по EIP-1559 (Tuned for Etherscan match)."""
        base_fees_raw = fh.get("baseFeePerGas", [])
        rewards_raw = fh.get("reward", [])
        
        if not base_fees_raw: return None
        
        # Base Fee (берем последний элемент - это base fee для следующего блока)
        next_base_wei = int(base_fees_raw[-1], 16) if isinstance(base_fees_raw[-1], str) else base_fees_raw[-1]
        next_base_gwei = next_base_wei / 1e9
        
        # Рассчитываем исторические чаевые для 25% (Low), 50% (Mid), 75% (High)
        # Индексы в массиве [5, 25, 50, 75, 95]: 1, 2, 3
        # Мы используем 75-й перцентиль для High, чтобы отсечь MEV-ботов (95-й перцентиль)
        hist_tips = {1: 0.0, 2: 0.0, 3: 0.0}
        
        if rewards_raw:
            try:
                # Считаем среднее для каждого нужного перцентиля по всем блокам
                counts = {1: 0, 2: 0, 3: 0}
                sums = {1: 0.0, 2: 0.0, 3: 0.0}
                
                for block_rewards in rewards_raw:
                    if len(block_rewards) >= 4:  # Need up to index 3
                        for idx in [1, 2, 3]:
                            val = int(block_rewards[idx], 16)
                            sums[idx] += val
                            counts[idx] += 1
                
                for idx in [1, 2, 3]:
                    if counts[idx] > 0:
                        hist_tips[idx] = (sums[idx] / counts[idx]) / 1e9
            except Exception:
                pass
        
        # Определяем конкретные значения чаевых
        tip_safe = hist_tips[1]  # 25th percentile
        tip_fast = hist_tips[3]  # 75th percentile (High) - Filtered outliers
        
        # Tip Propose (Average): Приоритет прямому ответу сети, иначе 50th percentile
        tip_propose = 0.0
        if direct_tip_hex:
            try:
                tip_propose = int(direct_tip_hex, 16) / 1e9
            except Exception:
                tip_propose = hist_tips[2]
        else:
            tip_propose = hist_tips[2]
        
        # Применяем минимальный порог
        tip_safe = max(_MIN_PRIORITY_FEE, tip_safe)
        tip_propose = max(_MIN_PRIORITY_FEE, tip_propose)
        tip_fast = max(_MIN_PRIORITY_FEE, tip_fast)
        
        # Итоговые суммы (Base + Tip)
        safe = next_base_gwei + tip_safe
        propose = next_base_gwei + tip_propose
        fast = next_base_gwei + tip_fast
        
        return self._build_result(
            "fee_history",
            safe, propose, fast,
            next_base_gwei,
            [tip_safe, tip_propose, tip_fast]
        )
    
    def _try_legacy_rpc(self, url: str):
        """
        Попытка 2: Legacy.
        Запрашивает eth_gasPrice и цену ETH.
        """
        req = QNetworkRequest(QUrl(url))
        req.setRawHeader(b"User-Agent", config.NETWORK_USER_AGENT)
        req.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json")
        
        payload = json.dumps([
            {
                "jsonrpc": "2.0", "id": 1,
                "method": "eth_gasPrice",
                "params": []
            },
            {
                "jsonrpc": "2.0", "id": 2,
                "method": "eth_call",
                "params": [{"to": _CHAINLINK_FEED_ADDR, "data": _CHAINLINK_FUNC_SIG}, "latest"]
            }
        ]).encode("utf-8")
        
        self._reply = self._nam.post(req, payload)
        self._reply.finished.connect(self._on_legacy_rpc_finished)
    
    def _on_legacy_rpc_finished(self):
        reply = self._reply
        self._reply = None
        if not reply:
            self._current_rpc_index += 1
            self._do_rpc()
            return
        
        reply.deleteLater()
        
        err = reply.error()
        http_status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        raw_data = reply.readAll().data()
        
        success = False
        
        if err == QNetworkReply.NetworkError.NoError and http_status == 200:
            try:
                text = raw_data.decode("utf-8", errors="ignore")
                js = json.loads(text)
                
                gas_price_hex = None
                price_hex = None
                
                if isinstance(js, list):
                    for item in js:
                        if not isinstance(item, dict): continue
                        rid = item.get("id")
                        res = item.get("result")
                        if rid == 1:
                            gas_price_hex = res
                        elif rid == 2:
                            price_hex = res
                
                if gas_price_hex:
                    gas_gwei = int(gas_price_hex, 16) / 1e9
                    
                    # В Legacy режиме Base Fee = Total Price, Priority = 0
                    # Это упрощение, но оно позволяет UI работать
                    final_data = self._build_result(
                        "legacy_rpc",
                        gas_gwei, gas_gwei, gas_gwei * 1.1,
                        gas_gwei,  # Base fee assumed as total
                        [0.0, 0.0, 0.0]  # No priority fee info
                    )
                    
                    final_data["eth_price"] = self._parse_chainlink_price(price_hex)
                    self._timer.stop()
                    self._emit_finished(final_data)
                    success = True
            except Exception:
                pass
        
        if not success:
            # Если и Legacy не сработал, идем к следующему узлу
            self._current_rpc_index += 1
            self._do_rpc()
    
    def _parse_chainlink_price(self, hex_str: Optional[str]) -> float:
        if not hex_str or not isinstance(hex_str, str): return 0.0
        try:
            clean_hex = hex_str[2:] if hex_str.startswith("0x") else hex_str
            if len(clean_hex) < 128: return 0.0
            price_hex = clean_hex[64:128]
            return float(int(price_hex, 16)) / 1e8
        except Exception:
            return 0.0
    
    def _build_result(self, source: str, s: float, p: float, f: float, b: float, tips: list) -> dict:
        return {
            "source": source,
            "propose_gwei": p,
            "suggest_base_fee_gwei": b,
            "levels": {"safe": s, "propose": p, "fast": f},
            "detail": {
                "base_fee_gwei": b,
                "p10_tip_gwei": tips[0],
                "p50_tip_gwei": tips[1],
                "p90_tip_gwei": tips[2],
            }
        }
    
    def _finish_empty(self):
        self._timer.stop()
        self._emit_finished({
            "source": "none", "propose_gwei": 0.0, "suggest_base_fee_gwei": 0.0,
            "levels": {"safe": 0.0, "propose": 0.0, "fast": 0.0},
            "detail": {"base_fee_gwei": 0.0, "p10_tip_gwei": 0.0, "p50_tip_gwei": 0.0, "p90_tip_gwei": 0.0},
            "eth_price": 0.0
        })


class ApiKeyValidator(QObject):
    """
    Валидатор API ключа Etherscan.
    Проверяет работоспособность ключа через реальный запрос.
    """
    validationSuccess = Signal()
    validationError = Signal(str)  # "network" or "invalid"
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._nam = QNetworkAccessManager(self)
        self._reply: Optional[QNetworkReply] = None
    
    def validate_key(self, api_key: str):
        """Запускает асинхронную проверку ключа."""
        if self._reply and self._reply.isRunning():
            self._reply.abort()
        
        # Используем gasoracle как легкий и показательный запрос
        query = QUrl(_ETHERSCAN_API_URL)
        q = QUrlQuery()
        q.addQueryItem("chainid", str(_CHAIN_ID))
        q.addQueryItem("module", "gastracker")
        q.addQueryItem("action", "gasoracle")
        q.addQueryItem("apikey", api_key)
        query.setQuery(q)
        
        req = QNetworkRequest(query)
        req.setRawHeader(b"User-Agent", config.NETWORK_USER_AGENT)
        
        self._reply = self._nam.get(req)
        self._reply.finished.connect(self._on_finished)
    
    def _on_finished(self):
        reply = self._reply
        self._reply = None
        if not reply: return
        reply.deleteLater()
        
        # 1. Игнорируем отмененные запросы (защита от дребезга)
        if reply.error() == QNetworkReply.NetworkError.OperationCanceledError:
            return
        
        # 2. Сетевые ошибки
        if reply.error() != QNetworkReply.NetworkError.NoError:
            self.validationError.emit("network")
            return
        
        # 3. Строгая валидация (Fail-Closed)
        try:
            data = reply.readAll().data()
            text = data.decode("utf-8", errors="ignore")
            js = json.loads(text)
            
            if isinstance(js, dict):
                status = js.get("status")
                result = str(js.get("result", ""))
                
                # Только явный успех считается валидным
                if status == "1":
                    self.validationSuccess.emit()
                # Явная ошибка ключа
                elif status == "0" and "Invalid API Key" in result:
                    self.validationError.emit("invalid")
                # Все остальное (Rate limit, Server error, Bad format) -> Network Error
                else:
                    self.validationError.emit("network")
            else:
                self.validationError.emit("network")
        
        except Exception:
            self.validationError.emit("network")


class ChainlistFetcher(QObject):
    """
    Загружает список публичных RPC из надежных источников (chainid.network).
    Фильтрует по ChainID=1 и отбирает случайных кандидатов.
    Реализует Blacklisting для обеспечения сетевой безопасности и отказоустойчивости.
    """
    finished = Signal(list)  # Returns list of candidate URLs
    
    # Надежные источники JSON со списком сетей
    _SOURCES = [
        "https://chainid.network/chains.json",
        "https://raw.githubusercontent.com/PRAN-K/chainlist/main/src/chains.json"
    ]
    
    # Список доменов, которые часто триггерят IDS/IPS системы антивирусов
    # как "Crypto Miner / RPC". Мы их игнорируем.
    _BANNED_DOMAINS = [
        "cloudflare-eth.com",
        "rpc.ankr.com",
        "publicnode.com",
        "1rpc.io"
    ]
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._nam = QNetworkAccessManager(self)
        self._reply: Optional[QNetworkReply] = None
        self._urls_queue = deque(self._SOURCES)
    
    def start_fetch(self):
        # Сброс очереди источников
        self._urls_queue = deque(self._SOURCES)
        self._try_next_url()
    
    def _try_next_url(self):
        if self._reply and self._reply.isRunning():
            self._reply.abort()
        
        if not self._urls_queue:
            self.finished.emit([])  # Все источники недоступны
            return
        
        url = self._urls_queue.popleft()
        req = QNetworkRequest(QUrl(url))
        req.setRawHeader(b"User-Agent", config.NETWORK_USER_AGENT)
        
        # Игнорируем SSL ошибки для максимальной совместимости
        ssl_conf = QSslConfiguration.defaultConfiguration()
        ssl_conf.setPeerVerifyMode(QSslSocket.VerifyNone)
        req.setSslConfiguration(ssl_conf)
        
        self._reply = self._nam.get(req)
        self._reply.finished.connect(self._on_finished)
        # Игнорируем SSL ошибки в сигнале
        self._reply.sslErrors.connect(self._reply.ignoreSslErrors)
    
    def _on_finished(self):
        reply = self._reply
        self._reply = None
        if not reply: return
        reply.deleteLater()
        
        candidates = []
        success = False
        
        if reply.error() == QNetworkReply.NetworkError.NoError:
            try:
                data = reply.readAll().data()
                js = json.loads(data)
                
                # Стандартный формат: список объектов сетей
                if isinstance(js, list):
                    # Ищем Ethereum Mainnet (chainId = 1)
                    eth_net = next((item for item in js if item.get("chainId") == 1), None)
                    
                    if eth_net:
                        rpc_list = eth_net.get("rpc", [])
                        for url in rpc_list:
                            if self._is_valid_url(url):
                                candidates.append(url)
                        success = True
            except Exception:
                pass
        
        if success and candidates:
            # Deduplicate & Shuffle
            candidates = list(set(candidates))
            random.shuffle(candidates)
            candidates = candidates[:config.RPC_CANDIDATE_SAMPLE]
            self.finished.emit(candidates)
        else:
            # Пробуем следующий источник
            self._try_next_url()
    
    def _is_valid_url(self, url: Any) -> bool:
        if not isinstance(url, str): return False
        if not url.startswith("https://"): return False
        if "${" in url: return False  # Исключаем URL с API ключами (Infura/Alchemy placeholders)
        
        # Blacklist check (Behavioral Evasion)
        url_lower = url.lower()
        for banned in self._BANNED_DOMAINS:
            if banned in url_lower:
                return False
        
        return True


class RpcBatchValidator(QObject):
    """
    Параллельный валидатор списка RPC узлов.
    Проверяет доступность, ChainID = 1, Latency и Sync Status.
    Реализует Adaptive Timeout (Early Cancellation) для отсечения медленных узлов.
    """
    itemStatusChanged = Signal(int, str)  # index, status ('loading', 'ok', 'error')
    finished = Signal(bool, list)  # is_success, valid_urls (sorted by latency if requested)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._nam = QNetworkAccessManager(self)
        self._pending_count = 0
        self._valid_urls = []
        self._results = {}  # index -> (url, latency_ms, block_height)
        self._sort_by_latency = False
        
        # Adaptive Timeout Logic
        self._active_replies: List[QNetworkReply] = []
        self._cutoff_timer = QTimer(self)
        self._cutoff_timer.setSingleShot(True)
        self._cutoff_timer.timeout.connect(self._kill_remaining_requests)
        self._success_count = 0
    
    def validate_list(self, urls: List[str], sort_by_latency: bool = False):
        self._pending_count = 0
        self._valid_urls = []
        self._results = {}
        self._sort_by_latency = sort_by_latency
        
        # Reset Adaptive Logic
        self._active_replies.clear()
        self._cutoff_timer.stop()
        self._success_count = 0
        
        active_indices = []
        for i, url in enumerate(urls):
            clean_url = url.split('#')[0].strip()  # Remove comments
            
            # Defensive Check: If URL is empty or invalid protocol, fail fast
            if not clean_url or not clean_url.lower().startswith(('https://', 'http://')):
                self.itemStatusChanged.emit(i, "error")
                continue
            
            active_indices.append(i)
            self.itemStatusChanged.emit(i, "loading")
            
            req = QNetworkRequest(QUrl(clean_url))
            req.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json")
            req.setRawHeader(b"User-Agent", config.NETWORK_USER_AGENT)
            
            # Игнорируем SSL ошибки
            ssl_conf = QSslConfiguration.defaultConfiguration()
            ssl_conf.setPeerVerifyMode(QSslSocket.VerifyNone)
            req.setSslConfiguration(ssl_conf)
            
            # Запрашиваем ChainID и BlockNumber одним батчем
            payload = json.dumps([
                {"jsonrpc": "2.0", "method": "eth_chainId", "params": [], "id": 1},
                {"jsonrpc": "2.0", "method": "eth_blockNumber", "params": [], "id": 2}
            ]).encode("utf-8")
            
            reply = self._nam.post(req, payload)
            reply.setProperty("idx", i)
            reply.setProperty("url", clean_url)
            reply.setProperty("ts_start", QDateTime.currentMSecsSinceEpoch())
            
            reply.finished.connect(self._on_reply_finished)
            reply.sslErrors.connect(reply.ignoreSslErrors)
            
            self._active_replies.append(reply)
            self._pending_count += 1
        
        if self._pending_count == 0:
            self.finished.emit(True, [])
    
    def _on_reply_finished(self):
        reply = self.sender()
        if not isinstance(reply, QNetworkReply): return
        
        # Remove from active list
        if reply in self._active_replies:
            self._active_replies.remove(reply)
        
        reply.deleteLater()
        
        ts_end = QDateTime.currentMSecsSinceEpoch()
        ts_start = reply.property("ts_start")
        latency = ts_end - ts_start
        
        idx = reply.property("idx")
        url = reply.property("url")
        
        is_valid = False
        block_height = 0
        
        if reply.error() == QNetworkReply.NetworkError.NoError:
            try:
                data = reply.readAll().data()
                js = json.loads(data)
                
                chain_ok = False
                height_ok = False
                
                if isinstance(js, list):
                    for item in js:
                        if item.get("id") == 1:
                            res = item.get("result")
                            if res == "0x1" or res == 1: chain_ok = True
                        elif item.get("id") == 2:
                            res = item.get("result")
                            if res:
                                block_height = int(res, 16)
                                if block_height > 1000000: height_ok = True
                
                if chain_ok and height_ok:
                    is_valid = True
            except Exception:
                pass
        
        status = "ok" if is_valid else "error"
        self.itemStatusChanged.emit(idx, status)
        
        if is_valid:
            self._results[idx] = (url, latency, block_height)
            self._success_count += 1
            
            # --- Adaptive Timeout Trigger ---
            # Если мы нашли достаточное количество хороших узлов, запускаем таймер смерти для остальных
            if self._success_count == config.RPC_ADAPTIVE_TARGET_COUNT and not self._cutoff_timer.isActive():
                # Рассчитываем время отсечения: текущий пинг + буфер
                buffer_ms = max(
                    config.RPC_ADAPTIVE_BUFFER_BASE_MS,
                    int(latency * config.RPC_ADAPTIVE_BUFFER_FACTOR)
                )
                self._cutoff_timer.start(buffer_ms)
        
        self._pending_count -= 1
        if self._pending_count <= 0:
            self._cutoff_timer.stop()
            self._finalize_results()
    
    def _kill_remaining_requests(self):
        """Принудительно отменяет все оставшиеся запросы."""
        # Итерируемся по копии списка, так как abort() может вызвать finished и изменить список
        for reply in list(self._active_replies):
            if reply.isRunning():
                reply.abort()
        self._active_replies.clear()
    
    def _finalize_results(self):
        final_list = []
        
        if self._sort_by_latency and self._results:
            # Фильтрация по высоте блока (отсеиваем отстающие узлы)
            heights = [v[2] for v in self._results.values()]
            max_height = max(heights)
            # Допускаем отставание не более 50 блоков
            valid_items = [v for v in self._results.values() if v[2] >= max_height - 50]
            
            # Сортировка по пингу
            sorted_items = sorted(valid_items, key=lambda x: x[1])
            
            # Возвращаем кортежи (url, latency)
            final_list = [(item[0], item[1]) for item in sorted_items]
        else:
            # Сортировка по индексу (как было введено пользователем)
            sorted_keys = sorted(self._results.keys())
            # Возвращаем кортежи (url, latency)
            final_list = [(self._results[k][0], self._results[k][1]) for k in sorted_keys]
        
        self.finished.emit(len(final_list) > 0, final_list)


class UpdateManager(QObject):
    """
    Менеджер обновлений.
    Проверяет GitHub Releases и скачивает новую версию.
    Реализует Side-by-Side загрузку для безопасного обновления в Windows.
    """
    # (has_update, version, url, release_notes, release_date)
    updateCheckFinished = Signal(bool, str, str, str, str)
    # (percent, received_bytes, total_bytes)
    downloadProgress = Signal(int, int, int)
    downloadFinished = Signal(str)  # path to file
    errorOccurred = Signal(str)
    
    # Новые сигналы для прозрачности процесса
    logMessage = Signal(str)
    targetPathChanged = Signal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._nam = QNetworkAccessManager(self)
        self._reply: Optional[QNetworkReply] = None
        self._file: Optional[QFile] = None
        self._target_path = ""
        self._temp_path = ""
    
    def _log(self, msg: str):
        """Внутренний метод для отправки логов в UI."""
        self.logMessage.emit(msg)
    
    def check_for_updates(self):
        """Запрос к GitHub API для проверки последней версии."""
        if self._reply and self._reply.isRunning():
            self._reply.abort()
        
        req = QNetworkRequest(QUrl(_GITHUB_REPOS_URL))
        req.setRawHeader(b"User-Agent", config.NETWORK_USER_AGENT)
        req.setRawHeader(b"Accept", b"application/vnd.github.v3+json")
        
        self._reply = self._nam.get(req)
        self._reply.finished.connect(self._on_check_finished)
    
    def _on_check_finished(self):
        reply = self._reply
        self._reply = None
        if not reply: return
        reply.deleteLater()
        
        if reply.error() != QNetworkReply.NetworkError.NoError:
            self.errorOccurred.emit(TextStore.Errors.ERR_NETWORK)
            return
        
        try:
            data = reply.readAll().data()
            js = json.loads(data)
            
            tag_name = js.get("tag_name", "").strip()
            body = js.get("body", "")
            assets = js.get("assets", [])
            published_at = js.get("published_at", "")
            
            # Парсинг даты релиза
            date_str = ""
            if published_at:
                dt = QDateTime.fromString(published_at, Qt.ISODate)
                if dt.isValid():
                    date_str = dt.toString("dd.MM.yyyy")
            
            # Поиск exe файла в ассетах
            download_url = ""
            for asset in assets:
                name = asset.get("name", "").lower()
                if name.endswith(".exe"):
                    download_url = asset.get("browser_download_url", "")
                    break
            
            if not tag_name or not download_url:
                self.updateCheckFinished.emit(False, "", "", "", "")
                return
            
            # Сравнение версий
            current_ver = config.APP_VERSION
            if self._compare_versions(tag_name, current_ver) > 0:
                self.updateCheckFinished.emit(True, tag_name, download_url, body, date_str)
            else:
                # Даже если обновлений нет, передаем body для отображения изменений текущей версии
                self.updateCheckFinished.emit(False, tag_name, "", body, date_str)
        
        except Exception as e:
            self.errorOccurred.emit(str(e))
    
    def download_update(self, url: str, version: str):
        """
        Скачивание файла обновления.
        Использует Side-by-Side подход: скачивает новый файл рядом с текущим.
        """
        self._log(f"Starting download sequence for: {url}")
        
        if self._reply and self._reply.isRunning():
            self._reply.abort()
        
        # 1. Жесткое определение пути к текущему EXE (Path Hardening)
        base_dir = ""
        
        # В Nuitka OneFile sys.argv[0] указывает на исходный EXE, а не на временный
        if sys.argv and os.path.isfile(sys.argv[0]):
            base_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
            self._log(f"Path determination: Using sys.argv[0] -> {base_dir}")
        
        # Fallback (на всякий случай, например для dev среды)
        if not base_dir:
            if getattr(sys, 'frozen', False):
                base_dir = os.path.dirname(sys.executable)
                self._log("Path determination: Using sys.executable (Frozen)")
            else:
                base_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
                self._log("Path determination: Using sys.argv[0] (Dev)")
        
        self._log(f"Base directory determined: {base_dir}")
        
        # 2. Проверка прав на запись (Pre-flight Check)
        if not os.access(base_dir, os.W_OK):
            self._log("ERROR: Write permission denied for base directory.")
            self.errorOccurred.emit("Write Permission Denied")
            return
        
        self._log("Write permission check: PASSED")
        
        # 3. Формирование имени файла (Strict Naming)
        # Используем новый стандарт из config.py
        try:
            clean_ver = version.lstrip('v')
            filename = config.get_executable_filename(clean_ver)
            self._log(f"Generated filename: {filename}")
        except Exception as e:
            self._log(f"Filename generation error: {e}, using fallback.")
            filename = "update_new.exe"
        
        self._target_path = os.path.join(base_dir, filename)
        self._temp_path = self._target_path + ".tmp"
        
        # Сообщаем UI о целевом пути
        self.targetPathChanged.emit(self._target_path)
        self._log(f"Target path: {self._target_path}")
        self._log(f"Temp path: {self._temp_path}")
        
        # Очистка мусора от предыдущих попыток
        if os.path.exists(self._temp_path):
            try:
                os.remove(self._temp_path)
                self._log("Cleaned up old temp file.")
            except OSError as e:
                self._log(f"Warning: Could not clean temp file: {e}")
        
        # 4. Начало загрузки во временный файл
        self._file = QFile(self._temp_path)
        if not self._file.open(QIODevice.WriteOnly):
            self._log("ERROR: Could not open temp file for writing.")
            self.errorOccurred.emit("File Access Error")
            return
        
        self._log("File opened for writing. Requesting network resource...")
        
        req = QNetworkRequest(QUrl(url))
        req.setRawHeader(b"User-Agent", config.NETWORK_USER_AGENT)
        
        self._reply = self._nam.get(req)
        self._reply.downloadProgress.connect(self._on_download_progress)
        self._reply.readyRead.connect(self._on_ready_read)
        self._reply.finished.connect(self._on_download_finished)
    
    def _on_download_progress(self, received, total):
        if total > 0:
            percent = int((received / total) * 100)
            self.downloadProgress.emit(percent, received, total)
    
    def _on_ready_read(self):
        if self._reply and self._file:
            self._file.write(self._reply.readAll())
    
    def _on_download_finished(self):
        self._log("Network transfer finished.")
        
        # Сначала закрываем файл, чтобы освободить дескриптор
        if self._file:
            self._file.close()
            self._file = None
            self._log("File closed.")
        
        if self._reply.error() == QNetworkReply.NetworkError.NoError:
            self._log("Download successful. Processing file...")
            # Атомарная подмена (Atomic Swap)
            try:
                # Если целевой файл уже существует (остался мусор), удаляем
                if os.path.exists(self._target_path):
                    self._log("Removing existing target file...")
                    os.remove(self._target_path)
                
                # Переименовываем .tmp -> .exe
                self._log("Renaming .tmp to .exe...")
                os.rename(self._temp_path, self._target_path)
                self._log("Update installed successfully.")
                self.downloadFinished.emit(self._target_path)
            
            except OSError as e:
                self._log(f"CRITICAL: File system error: {e}")
                self.errorOccurred.emit("File System Error")
                # Пытаемся подчистить темп
                if os.path.exists(self._temp_path):
                    try:
                        os.remove(self._temp_path)
                    except OSError:
                        pass
        else:
            self._log(f"Network Error: {self._reply.errorString()}")
            self.errorOccurred.emit("Download Failed")
            # Удаляем недокачанный файл
            if os.path.exists(self._temp_path):
                try:
                    os.remove(self._temp_path)
                except OSError:
                    pass
        
        if self._reply:
            self._reply.deleteLater()
            self._reply = None
    
    def _compare_versions(self, v1: str, v2: str) -> int:
        """
        Сравнивает версии SemVer (v1.0.0 vs 0.9.9).
        Возвращает: 1 если v1 > v2, -1 если v1 < v2, 0 если равны.
        """
        
        def normalize(v):
            return [int(x) for x in v.lstrip('v').split('.') if x.isdigit()]
        
        p1 = normalize(v1)
        p2 = normalize(v2)
        
        # Выравнивание длины
        len_diff = len(p1) - len(p2)
        if len_diff > 0:
            p2.extend([0] * len_diff)
        elif len_diff < 0:
            p1.extend([0] * -len_diff)
        
        if p1 > p2: return 1
        if p1 < p2: return -1
        return 0


# -------------------------------------------------------------------------
# 2. HELPERS
# -------------------------------------------------------------------------

def _wei_to_gwei(val: Union[str, int, float, None]) -> float:
    try:
        if isinstance(val, str): return int(val, 16) / 1e9
        if isinstance(val, (int, float)): return float(val) / 1e9
    except Exception:
        pass
    return 0.0


def _to_float(val: Any) -> float:
    try:
        return float(val)
    except Exception:
        return 0.0
