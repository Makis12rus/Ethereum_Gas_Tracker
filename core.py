from __future__ import annotations

# -*- coding: utf-8 -*-

"""
Аннотация

🧩 1. Назначение файла
- Ядро приложения (Core Business Logic).
- Менеджер Локализации (TextStore Provider).
- Отвечает за управление состоянием, таймерами и обработку данных.

🧱 2. Компоненты
- TextStore: Глобальная ссылка на активную локализацию.
- AppLogic: Главный контроллер (Таймеры, Состояние, Тренды, Discovery).
- HeartbeatMonitor: Сторожевой таймер (Watchdog).

⚙️ 3. Особенности
- Централизованное управление текстами (SSOT).
- Взаимодействие с services.py для тяжелых операций.
- Сохранение логики Failover и Watchdog.
"""

import os
import sys
import time
from typing import Optional, Any, Union, List
from collections import deque

from PySide6.QtCore import (
    QObject, QTimer, Signal, QSettings, QThread, QProcess
)

import config
import services  # Подключение слоя сервисов
import localization_ruRU  # Подключение источника текстов

# ---------------------------
# Локализация (Text Store)
# ---------------------------

# В будущем здесь можно реализовать логику переключения языков.
# Сейчас жестко привязано к ruRU.
TextStore = localization_ruRU.Locale

# ---------------------------
# Константы логики
# ---------------------------

_SMA_WINDOW = 5
_WATCHDOG_INTERVAL_MS = 500
_HEARTBEAT_TIMEOUT_SEC = 10.0


# -------------------------------------------------------------------------
# 1. WATCHDOG (HeartbeatMonitor)
# -------------------------------------------------------------------------

class HeartbeatMonitor(QThread):
    """
    Фоновый поток, следящий за активностью главного цикла.
    Если приложение зависает, перезапускает процесс.
    """
    
    def __init__(self, timeout: float = 2.0):
        super().__init__()
        self._timeout = timeout
        self._last_beat = time.time()
        self._running = True
    
    def beat(self):
        self._last_beat = time.time()
    
    def stop(self):
        self._running = False
        self.wait()
    
    def run(self):
        while self._running:
            self.msleep(500)
            if not self._running: break
            
            delta = time.time() - self._last_beat
            if delta > self._timeout:
                try:
                    # AV Evasion: Используем легитимный способ перезапуска через Qt.
                    # os.execl удален, так как он триггерит эвристику (Process Hollowing).
                    program = sys.executable
                    args = []
                    
                    # Если запущено как скрипт (dev mode), передаем скрипт как аргумент
                    if not getattr(sys, 'frozen', False):
                        args = sys.argv
                    else:
                        # Если скомпилировано (Nuitka/PyInstaller), sys.argv[0] это сам exe
                        # Передаем только аргументы командной строки, если они есть
                        args = sys.argv[1:]
                    
                    QProcess.startDetached(program, args)
                except Exception:
                    pass
                finally:
                    # Fallback exit: Гарантированно завершаем зависший процесс
                    os._exit(1)


# -------------------------------------------------------------------------
# 2. CONTROLLER (AppLogic)
# -------------------------------------------------------------------------

class AppLogic(QObject):
    """
    Главный контроллер приложения.
    Связывает настройки, таймеры и сетевой слой (через services).
    """
    # Сигналы для UI и System
    priceUpdated = Signal(object)
    countdownTick = Signal(int)
    requestNotification = Signal(str, str)
    stateInfo = Signal(str, bool)
    watchdogRecovery = Signal()
    
    # Сигнал о найденных быстрых узлах
    bestNodesFound = Signal(list)
    
    # Внутренние сигналы для воркера
    _requestFetch = Signal(object, int)
    _requestStop = Signal()
    
    def __init__(self, settings: QSettings) -> None:
        super().__init__()
        self._s = settings
        
        # Чтение настроек
        self._interval_s = max(5, _read_val(self._s, "poll_interval_s", 30, int))
        self._timeout_ms = max(500, _read_val(self._s, "request_timeout_ms", 3000, int))
        self._threshold_gwei = max(0.0, _read_val(self._s, "threshold_gwei", 0.0, float))
        self._rpc_url = self._read_rpc_url()
        
        # Состояние
        self._stopped = True
        self._request_in_flight = False
        self._notification_sent = False
        
        self._last_valid_data: Optional[dict] = None
        self._last_gwei: Optional[float] = None
        self._cached_eth_price: float = 0.0
        self._price_history = deque(maxlen=_SMA_WINDOW)
        self._countdown_left = 0
        
        # Кэш найденных узлов
        self._cached_best_nodes = []
        
        # Таймеры
        self._poll_timer = QTimer(self)
        self._poll_timer.setSingleShot(True)
        self._poll_timer.timeout.connect(self._poll_once)
        
        self._countdown_timer = QTimer(self)
        self._countdown_timer.setInterval(1000)
        self._countdown_timer.timeout.connect(self._on_countdown_tick)
        
        self._watchdog_timer = QTimer(self)
        self._watchdog_timer.setInterval(_WATCHDOG_INTERVAL_MS)
        self._watchdog_timer.timeout.connect(self._on_watchdog_tick)
        
        self._last_tick_time = time.time()
        self._last_data_time = time.time()
        
        self._heartbeat = HeartbeatMonitor(timeout=_HEARTBEAT_TIMEOUT_SEC)
        
        # Инициализация сетевого воркера (через Services)
        self._thread = QThread()
        self._fetcher = services.GasFetchService()
        self._fetcher.moveToThread(self._thread)
        self._fetcher.finished.connect(self._on_fetch_finished)
        self._requestFetch.connect(self._fetcher.start_fetch)
        self._requestStop.connect(self._fetcher.stop)
        self._thread.start()
        
        # Инициализация сервисов поиска узлов (через Services)
        self._chainlist_fetcher = services.ChainlistFetcher(self)
        self._chainlist_fetcher.finished.connect(self._on_chainlist_candidates)
        
        self._discovery_validator = services.RpcBatchValidator(self)
        self._discovery_validator.finished.connect(self._on_discovery_finished)
    
    @property
    def key_storage_method(self) -> str:
        if not os.environ.get("ETHERSCAN_API_KEY", "").strip():
            return "none"
        return os.environ.get("_KEY_STORAGE_METHOD", "memory")
    
    @property
    def is_custom_rpc(self) -> bool:
        current = self._read_rpc_url()
        # Если текущий список совпадает с дефолтным или пуст - считаем не кастомным
        return current != services.DEFAULT_RPC_LIST and bool(current)
    
    @property
    def cached_best_nodes(self) -> List[str]:
        return self._cached_best_nodes
    
    def start(self) -> None:
        if not self._stopped: return
        self._stopped = False
        
        self._last_tick_time = time.time()
        self._last_data_time = time.time()
        self._watchdog_timer.start()
        
        self._heartbeat.beat()
        if not self._heartbeat.isRunning():
            self._heartbeat.start()
        
        self.refresh_state_info()
        self.force_refresh()
        self._countdown_timer.start()
        
        # Lazy Start: Автоматический поиск узлов отключен для обхода песочниц.
        # Поиск запускается только по явной команде пользователя из UI.
    
    def stop(self) -> None:
        self._stopped = True
        self._poll_timer.stop()
        self._countdown_timer.stop()
        self._watchdog_timer.stop()
        self._request_in_flight = False
        
        self._heartbeat.stop()
        self._requestStop.emit()
        
        if self._thread.isRunning():
            self._thread.quit()
            self._thread.wait()
    
    def force_refresh(self) -> None:
        if self._stopped: return
        self._poll_timer.stop()
        self._request_in_flight = False
        self._schedule_next(immediate=True)
    
    def refresh_state_info(self) -> None:
        self.stateInfo.emit(self.key_storage_method, self.is_custom_rpc)
    
    def set_poll_interval(self, seconds: int) -> None:
        self._interval_s = max(5, int(seconds))
        _write_val(self._s, "poll_interval_s", self._interval_s)
        self.force_refresh()
    
    def set_threshold(self, gwei: float) -> None:
        self._threshold_gwei = max(0.0, float(gwei))
        _write_val(self._s, "threshold_gwei", self._threshold_gwei)
        self._notification_sent = False
        self._check_threshold()
    
    # --- RPC Discovery Logic ---
    
    def find_best_nodes(self):
        """Запускает процесс поиска лучших узлов."""
        self._chainlist_fetcher.start_fetch()
    
    def _on_chainlist_candidates(self, candidates: List[str]):
        if not candidates:
            # Если Chainlist недоступен, ничего не делаем (оставляем старые или дефолтные)
            return
        
        # Запускаем валидацию с сортировкой по пингу
        self._discovery_validator.validate_list(candidates, sort_by_latency=True)
    
    def _on_discovery_finished(self, success: bool, valid_urls: List[str]):
        if success and valid_urls:
            # Берем топ N самых быстрых
            top_nodes = valid_urls[:config.RPC_TOP_RESULTS]
            self._cached_best_nodes = top_nodes
            self.bestNodesFound.emit(top_nodes)
            
            # Если у пользователя не настроен кастомный RPC и нет ключа API,
            # можно автоматически применить найденные узлы (опционально).
            # Пока просто кэшируем для диалога настроек.
    
    # --- Watchdog & Timers ---
    
    def _on_watchdog_tick(self) -> None:
        if self._stopped: return
        self._heartbeat.beat()
        
        now = time.time()
        delta = now - self._last_tick_time
        self._last_tick_time = now
        
        # Если главный поток подвис более чем на 3 интервала watchdog
        if delta > (_WATCHDOG_INTERVAL_MS / 1000.0 * 3):
            self.force_refresh()
            return
        
        # Если данных нет слишком долго
        stall_threshold = max(15.0, self._interval_s * 2.5)
        if (now - self._last_data_time) > stall_threshold:
            self._request_in_flight = False
            self.force_refresh()
        
        self.watchdogRecovery.emit()
    
    def _read_rpc_url(self) -> Union[str, List[str]]:
        self._s.beginGroup("core")
        val = self._s.value("rpc_url", "")
        self._s.endGroup()
        
        if isinstance(val, list):
            # Очистка от комментариев при чтении и валидация
            clean = []
            for v in val:
                if not isinstance(v, str): continue
                clean_url = v.split('#')[0].strip()
                # Strict validation
                if clean_url and clean_url.lower().startswith(('https://', 'http://')):
                    clean.append(clean_url)
            return clean if clean else services.DEFAULT_RPC_LIST
        
        if isinstance(val, str):
            s = val.split('#')[0].strip()
            if s and s.lower().startswith(('https://', 'http://')):
                return s
            return services.DEFAULT_RPC_LIST
        return services.DEFAULT_RPC_LIST
    
    def _schedule_next(self, *, immediate: bool) -> None:
        if self._stopped: return
        self._countdown_left = self._interval_s
        ms = 0 if immediate else self._interval_s * 1000
        self._poll_timer.start(ms)
        self.countdownTick.emit(self._countdown_left)
    
    def _on_countdown_tick(self) -> None:
        if self._stopped: return
        self._countdown_left = max(0, self._countdown_left - 1)
        self.countdownTick.emit(self._countdown_left)
        
        if self._countdown_left <= 0 and not self._poll_timer.isActive() and not self._request_in_flight:
            self._schedule_next(immediate=True)
    
    def _poll_once(self) -> None:
        if self._stopped or self._request_in_flight: return
        self._rpc_url = self._read_rpc_url()
        self._request_in_flight = True
        self._requestFetch.emit(self._rpc_url, self._timeout_ms)
    
    def _on_fetch_finished(self, data: Any) -> None:
        self._request_in_flight = False
        self._last_data_time = time.time()
        self._process_data(data)
        if not self._stopped:
            self._schedule_next(immediate=False)
    
    def _extract_gwei(self, data: Any) -> float:
        if isinstance(data, dict):
            return float(data.get("propose_gwei", 0.0))
        return 0.0
    
    def _calculate_trend(self, current_price: float) -> str:
        if not self._price_history: return "flat"
        avg = sum(self._price_history) / len(self._price_history)
        threshold = avg * 0.01
        if current_price > avg + threshold:
            return "up"
        elif current_price < avg - threshold:
            return "down"
        return "flat"
    
    def _process_data(self, data: Any) -> None:
        is_valid = False
        trend = "flat"
        
        if isinstance(data, dict) and data.get("source") != "none":
            current_eth_price = float(data.get("eth_price", 0.0))
            if current_eth_price > 0:
                self._cached_eth_price = current_eth_price
            elif self._cached_eth_price > 0:
                data["eth_price"] = self._cached_eth_price
            
            gwei = self._extract_gwei(data)
            if gwei > 0:
                trend = self._calculate_trend(gwei)
                self._price_history.append(gwei)
                self._last_gwei = gwei
                self._last_valid_data = data
                data["is_stale"] = False
                data["trend"] = trend
                self.priceUpdated.emit(data)
                is_valid = True
        
        if not is_valid:
            if self._last_valid_data:
                stale_copy = self._last_valid_data.copy()
                stale_copy["is_stale"] = True
                stale_copy["trend"] = "flat"
                self.priceUpdated.emit(stale_copy)
            else:
                # Используем локализованный плейсхолдер
                placeholder = f"{TextStore.Hud.PREFIX_ETH}{TextStore.Hud.VAL_PLACEHOLDER}"
                self.priceUpdated.emit(placeholder)
        
        if is_valid:
            self._check_threshold()
    
    def _check_threshold(self) -> None:
        if self._threshold_gwei <= 0 or not self._last_gwei:
            self._notification_sent = False
            return
        if self._last_gwei <= self._threshold_gwei:
            if not self._notification_sent:
                # Используем локализованные сообщения с форматированием
                title = TextStore.Errors.NOTIFY_TITLE_THRESHOLD
                msg = TextStore.Errors.NOTIFY_MSG_THRESHOLD_FMT.format(
                    self._last_gwei, self._threshold_gwei
                )
                self.requestNotification.emit(title, msg)
                self._notification_sent = True
        else:
            self._notification_sent = False


# -------------------------------------------------------------------------
# 3. HELPERS
# -------------------------------------------------------------------------

def _read_val(settings: QSettings, key: str, default: Any, type_func: Any) -> Any:
    settings.beginGroup("core")
    val = settings.value(key, default)
    settings.endGroup()
    try:
        return type_func(val)
    except Exception:
        return default


def _write_val(settings: QSettings, key: str, value: Any) -> None:
    settings.beginGroup("core")
    settings.setValue(key, value)
    settings.endGroup()
    settings.sync()