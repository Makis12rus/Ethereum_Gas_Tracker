from __future__ import annotations

# -*- coding: utf-8 -*-

"""
Аннотация

🧩 1. Назначение файла
- Точка входа (Entry Point).
- Оркестрация модулей: Core <-> UI <-> System.
- Управление жизненным циклом приложения.

🧱 2. Компоненты
- Single Instance Lock: Защита от повторного запуска (Адаптивная).
- Handover Logic: Обработка аргументов для автообновления и очистки.
- Startup Wizard: Запуск диалога настройки при отсутствии ключа.
- Signal Wiring: Связывание бизнес-логики, интерфейса и системных событий.

⚙️ 3. Особенности
- Чистая архитектура: Модули не знают друг о друге, main.py их знакомит.
- High-DPI поддержка (PassThrough).
- Корректная очистка ресурсов при выходе.
- Использование TextStore для локализации.
"""

import os
import sys
import time
import ctypes
import tempfile
import threading
from typing import Optional

from PySide6.QtCore import (
    QSettings, Qt, QCoreApplication, QTranslator, QLocale,
    QLibraryInfo, QTimer, QLockFile
)
from PySide6.QtWidgets import QApplication, QDialog, QWidget
from PySide6.QtGui import QIcon

# Импорты модулей новой архитектуры
import config
import core
from core import TextStore  # Источник текстов
import services  # Подключение слоя сервисов
import win_logic
import ui_widgets  # Основной интерфейс (HUD)
import ui_dialogs  # Базовые и системные диалоги
import ui_wizzard  # Мастер настройки и выбора режима


# -------------------------------
# Утилиты инициализации
# -------------------------------

def _get_resource_path(relative_path: str) -> str:
    """Получение пути к ресурсам (поддержка PyInstaller/Nuitka)."""
    if getattr(sys, 'frozen', False) or hasattr(sys, "__compiled__"):
        base_path = os.path.dirname(sys.executable)
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)


def _setup_localization(app: QApplication) -> None:
    """Установка русской локали для стандартных диалогов Qt."""
    try:
        QLocale.setDefault(QLocale(QLocale.Russian, QLocale.Russia))
        path = QLibraryInfo.path(QLibraryInfo.TranslationsPath)
        for name in ("qt_ru", "qtbase_ru"):
            t = QTranslator(app)
            if t.load(name, path):
                app.installTranslator(t)
    except Exception:
        pass


def _setup_settings() -> QSettings:
    """Инициализация настроек по умолчанию."""
    QSettings.setDefaultFormat(QSettings.NativeFormat)
    QCoreApplication.setOrganizationName(config.ORG_NAME)
    QCoreApplication.setApplicationName(config.APP_NAME_SYSTEM)
    
    s = QSettings()
    s.beginGroup("core")
    
    defaults = {
        "poll_interval_s": 30,
        "request_timeout_ms": 3000,
        "threshold_gwei": 0.0,
        "round_digits": 3,
        "always_on_top": True,
        "rpc_url": "",
        "active_mode": "api",  # 'api' or 'rpc'
    }
    
    for k, v in defaults.items():
        if not s.contains(k):
            s.setValue(k, v)
    
    if not s.contains("font_family"):
        s.setValue("font_family", config.DEFAULT_FONT_FAMILY)
        s.setValue("font_size_pt", int(config.DEFAULT_FONT_PT))
    
    s.endGroup()
    s.sync()
    return s


def _ensure_api_key() -> None:
    """
    Загружает ключ из SecretStorage.
    Активирует его в env только если выбран режим API.
    """
    s = QSettings()
    mode = s.value("core/active_mode", "api")
    
    key, method = win_logic.SecretStorage.get_key()
    if key:
        # Метод хранения нужен UI для отображения статуса (Keyring/DPAPI)
        os.environ["_KEY_STORAGE_METHOD"] = method
        
        # Экспортируем ключ для Core только в режиме API
        if mode == "api":
            os.environ["ETHERSCAN_API_KEY"] = key


def _open_settings_dialog(parent_widget: Optional[QWidget], logic_instance: core.AppLogic, settings: QSettings, start_mode: str = 'api') -> None:
    """
    Открывает единое окно настроек (ApiKeySetupDialog).
    Обрабатывает сохранение ключа, выбор режима и обновление конфигурации.
    """
    # 1. Получаем текущие данные
    current_key, _ = win_logic.SecretStorage.get_key()
    
    settings.beginGroup("core")
    rpc_val = settings.value("rpc_url", "")
    settings.endGroup()
    
    current_rpc = []
    if isinstance(rpc_val, list):
        current_rpc = [str(u) for u in rpc_val if u]
    elif isinstance(rpc_val, str) and rpc_val:
        current_rpc = [rpc_val]
    
    # 2. Запускаем диалог (Используем ui_wizzard)
    dlg = ui_wizzard.ApiKeySetupDialog(
        parent_widget,
        start_mode=start_mode,
        current_key=current_key or "",
        current_rpc_list=current_rpc
    )
    
    if dlg.exec() != QDialog.Accepted:
        return
    
    # 3. Обрабатываем результат
    new_key = dlg.get_key()
    selected_mode = dlg.get_selected_mode()
    
    # Обновляем глобальную тему (State-Driven Styling)
    config.set_active_mode(selected_mode)
    
    # Сохраняем ключ в хранилище ВСЕГДА, если он введен (даже если выбран RPC)
    if new_key:
        method = win_logic.SecretStorage.save_key(new_key)
        os.environ["_KEY_STORAGE_METHOD"] = method
    else:
        # Если поле пустое - очищаем хранилище
        win_logic.SecretStorage.save_key("")
        os.environ["_KEY_STORAGE_METHOD"] = "none"
    
    # Сохраняем выбранный режим
    settings.setValue("core/active_mode", selected_mode)
    
    # Обновляем переменные окружения для Core
    if selected_mode == "api" and new_key:
        os.environ["ETHERSCAN_API_KEY"] = new_key
    else:
        # В режиме RPC или при отсутствии ключа удаляем переменную
        if "ETHERSCAN_API_KEY" in os.environ:
            del os.environ["ETHERSCAN_API_KEY"]
    
    # 4. Обновляем логику
    if logic_instance:
        logic_instance.refresh_state_info()
        logic_instance.force_refresh()


def _open_update_dialog(parent_widget: Optional[QWidget], auto_start: bool = True) -> None:
    """Открывает диалог проверки обновлений."""
    # UpdateDialog остался в ui_dialogs
    dlg = ui_dialogs.UpdateDialog(parent_widget, auto_start=auto_start)
    dlg.exec()


def _cleanup_tray(ui_instance: Optional[ui_widgets.AppUI]):
    """Скрывает иконку трея при выходе."""
    if ui_instance and hasattr(ui_instance, "_tray") and ui_instance._tray:
        ui_instance._tray.hide()


# -------------------------------
# Main Entry Point
# -------------------------------

def main() -> int:
    # 0.1. Handover & Cleanup Logic (Auto-Update Support)
    # Проверяем аргументы командной строки на наличие флагов очистки
    cleanup_pid = 0
    cleanup_path = ""
    
    try:
        if "--cleanup-pid" in sys.argv:
            idx = sys.argv.index("--cleanup-pid")
            if idx + 1 < len(sys.argv):
                cleanup_pid = int(sys.argv[idx + 1])
        
        if "--cleanup-path" in sys.argv:
            idx = sys.argv.index("--cleanup-path")
            if idx + 1 < len(sys.argv):
                cleanup_path = sys.argv[idx + 1]
    except Exception:
        pass
    
    # Если это запуск после обновления, запускаем фоновый поток для удаления старого файла
    if cleanup_pid > 0 and cleanup_path:
        cleanup_thread = threading.Thread(
            target=win_logic.wait_for_pid_and_delete,
            args=(cleanup_pid, cleanup_path),
            daemon=True
        )
        cleanup_thread.start()
    
    # 0.2. Single Instance Check (Adaptive)
    lock_path = os.path.join(tempfile.gettempdir(), config.LOCK_FILE_NAME)
    lock = QLockFile(lock_path)
    
    is_locked = False
    
    if cleanup_pid > 0:
        # Режим обновления: Старый процесс еще может быть жив и держать лок.
        # Пытаемся захватить лок в течение 10 секунд (20 попыток по 500мс).
        for _ in range(20):
            if lock.tryLock(500):
                is_locked = True
                break
    else:
        # Обычный запуск: Быстрая проверка (защита от случайного двойного клика).
        for _ in range(10):
            if lock.tryLock(100):
                is_locked = True
                break
    
    if not is_locked:
        return 0
    
    # 0.3. AUMID Registration (Critical for Notifications)
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(config.APP_AUMID)
    except Exception:
        pass
    
    # 1. App Init
    if hasattr(Qt, "HighDpiScaleFactorRoundingPolicy"):
        QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    
    app = QApplication(sys.argv)
    
    icon_path = _get_resource_path("icon.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    
    config.apply_app_palette(app, dark=True)
    _setup_localization(app)
    
    # 2. Settings & Env
    settings = _setup_settings()
    _ensure_api_key()
    
    # Инициализация глобальной темы на основе сохраненных настроек
    initial_mode = settings.value("core/active_mode", "api")
    config.set_active_mode(initial_mode)
    
    # --- CLEANUP LEGACY AUTOSTART ---
    win_logic.purge_legacy_autostart()
    # -------------------------------
    
    # 3. Startup Wizard
    # Запускаем только если режим API (по умолчанию) и ключ не установлен.
    active_mode = settings.value("core/active_mode", "api")
    
    if active_mode == "api" and not os.environ.get("ETHERSCAN_API_KEY"):
        # Используем ui_wizzard для стартового диалога
        dlg = ui_wizzard.ApiKeySetupDialog(start_mode='rpc')
        if dlg.exec() == QDialog.Accepted:
            new_key = dlg.get_key()
            selected_mode = dlg.get_selected_mode()
            
            config.set_active_mode(selected_mode)
            
            if new_key:
                method = win_logic.SecretStorage.save_key(new_key)
                os.environ["_KEY_STORAGE_METHOD"] = method
            
            settings.setValue("core/active_mode", selected_mode)
            
            if selected_mode == "api" and new_key:
                os.environ["ETHERSCAN_API_KEY"] = new_key
    
    # 4. Services Initialization
    
    # System Logic (Positioning & Notifications)
    pos_logic = win_logic.PositionLogic()
    
    # UI Reference Holder (для замыканий)
    ui_ref = [None]
    
    def fallback_notify_handler(t: str, m: str):
        if ui_ref[0]: ui_ref[0].show_notification(t, m)
    
    notifier = win_logic.Notifier(
        app_id=config.APP_AUMID,
        display_name=config.APP_NAME_DISPLAY,
        on_fallback=fallback_notify_handler
    )
    
    # Core Logic
    logic = core.AppLogic(settings=settings)
    
    # UI (Используем ui_widgets)
    ui = ui_widgets.AppUI(settings=settings)
    ui_ref[0] = ui
    
    # 5. Signal Wiring (Связывание компонентов)
    
    # WinLogic -> UI (Позиционирование)
    pos_logic.worker_signal.connect(ui.on_position_update)
    
    # Core -> UI (Данные)
    logic.priceUpdated.connect(ui.on_price_updated)
    logic.countdownTick.connect(ui.on_countdown_tick)
    logic.stateInfo.connect(ui.on_state_info)
    logic.watchdogRecovery.connect(ui.force_ui_recovery)
    
    # Core -> System (Уведомления)
    logic.requestNotification.connect(lambda t, m: notifier.toast(t, m))
    
    # UI -> Core (Управление)
    ui.requestSetInterval.connect(logic.set_poll_interval)
    ui.requestSetThreshold.connect(logic.set_threshold)
    ui.requestForceRefresh.connect(logic.force_refresh)
    
    # UI Menu -> System/Core (Единое окно настроек)
    if hasattr(ui, "_menu") and ui._menu:
        ui._menu.requestOpenSettings.connect(
            lambda mode: QTimer.singleShot(0, lambda: _open_settings_dialog(ui, logic, settings, mode))
        )
        ui._menu.requestCheckUpdates.connect(
            lambda: _open_update_dialog(ui, auto_start=True)
        )
    
    # UI -> System (Тесты и Выход)
    ui.requestTestNotify.connect(
        lambda: notifier.toast(TextStore.Errors.NOTIFY_TITLE_TEST, TextStore.Errors.NOTIFY_MSG_TEST)
    )
    ui.requestExit.connect(app.quit)
    
    # 5.1 Silent Update Check (Startup)
    # Используем services.UpdateManager вместо core.UpdateManager
    startup_updater = services.UpdateManager()
    
    def on_startup_check(has_update, ver, url, notes):
        if has_update:
            _open_update_dialog(ui, auto_start=True)
    
    startup_updater.updateCheckFinished.connect(on_startup_check)
    QTimer.singleShot(3000, startup_updater.check_for_updates)
    
    # 6. Launch
    pos_logic.start()
    logic.start()
    ui.show()
    
    ret = app.exec()
    
    # Cleanup
    _cleanup_tray(ui)
    pos_logic.stop()
    logic.stop()
    lock.unlock()
    
    return ret


if __name__ == "__main__":
    sys.exit(main())