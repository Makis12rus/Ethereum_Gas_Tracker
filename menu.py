from typing import Optional

from PySide6.QtCore import Qt, Signal, QSettings
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QLabel, QWidgetAction, QDialog

import config
import win_logic
import ui_dialogs  # Модуль с диалоговыми окнами
from core import TextStore  # Источник текстов


class AppMenu(QMenu):
    """
    Контекстное меню приложения.
    Отвечает за настройки, обновление и выход.
    """
    
    # Сигналы для контроллера (AppLogic) и UI
    requestSetInterval = Signal(int)
    requestSetThreshold = Signal(float)
    requestOpenSettings = Signal(str)  # 'api' or 'rpc'
    requestForceRefresh = Signal()
    requestTestNotify = Signal()
    requestCheckUpdates = Signal()  # Новый сигнал для проверки обновлений
    requestExit = Signal()
    
    def __init__(self, parent=None, settings: Optional[QSettings] = None):
        super().__init__(parent)
        self._s = settings or QSettings()
        
        # Внутреннее состояние для отображения галочек/статусов
        self._key_storage_method = "none"
        self._is_custom_rpc = False
        self._current_source = "none"
        
        self._act_rpc: Optional[QAction] = None
        self._act_apikey: Optional[QAction] = None
        self._act_threshold: Optional[QAction] = None
        self._menu_interval: Optional[QMenu] = None
        
        # Настройка внешнего вида
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet(config.MENU_STYLESHEET)
        
        self._build_ui()
        self.aboutToShow.connect(self._on_about_to_show)
    
    def update_state(self, storage_method: str, is_custom_rpc: bool):
        """Обновляет информацию о состоянии (для иконок меню)."""
        self._key_storage_method = storage_method
        self._is_custom_rpc = is_custom_rpc
    
    def set_active_source(self, source: str):
        """Обновляет текущий источник данных."""
        self._current_source = str(source).lower()
    
    def show_context_menu(self, global_pos, position_manager=None):
        """
        Отображает меню с учетом Z-порядка Windows.
        position_manager: Ссылка на объект, управляющий позицией дока (для блокировки скрытия).
        """
        # Сообщаем менеджеру позиции, что меню открыто (чтобы док не прятался)
        if position_manager and hasattr(position_manager, "set_menu_open"):
            position_manager.set_menu_open(True)
            self.aboutToHide.connect(lambda: position_manager.set_menu_open(False), Qt.SingleShotConnection)
        
        # WinAPI Force TopMost: Гарантируем, что меню будет поверх всего
        try:
            hwnd = int(self.winId())
            win_logic.WindowManager.set_window_pos(hwnd, 0, 0, 0, 0, top_most=True, no_activate=True)
        except Exception:
            pass
        
        self.activateWindow()
        self.raise_()
        self.exec(global_pos)
    
    def _add_section_header(self, text: str):
        """Добавляет некликабельный заголовок секции."""
        lbl = QLabel(text)
        lbl.setStyleSheet(config.MENU_HEADER_STYLESHEET)
        act = QWidgetAction(self)
        act.setDefaultWidget(lbl)
        act.setEnabled(False)
        self.addAction(act)
    
    def _build_ui(self):
        """Сборка структуры меню."""
        self._add_section_header(TextStore.Menu.SECTION_SETTINGS)
        
        # Подменю интервала
        self._menu_interval = QMenu(TextStore.Menu.SUBMENU_INTERVAL, self)
        self._menu_interval.setWindowFlags(self._menu_interval.windowFlags() | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self._menu_interval.setAttribute(Qt.WA_TranslucentBackground)
        self._menu_interval.setStyleSheet(config.MENU_STYLESHEET)
        self._menu_interval.setIcon(config.create_menu_emoji_icon("⏱️"))
        
        presets = [("5 сек", 5), ("15 сек", 15), ("30 сек", 30), ("60 сек", 60)]
        for t, s in presets:
            a = QAction(t, self._menu_interval)
            a.setData(s)
            a.setIcon(config.create_menu_status_icon(False))
            a.triggered.connect(lambda c, val=s: self.requestSetInterval.emit(val))
            self._menu_interval.addAction(a)
        
        self._menu_interval.addSeparator()
        act_custom = self._menu_interval.addAction(TextStore.Menu.VAL_CUSTOM, self._ask_custom_interval)
        act_custom.setData("custom")
        act_custom.setIcon(config.create_menu_status_icon(False))
        self._menu_interval.aboutToShow.connect(self._update_interval_menu_icons)
        self.addMenu(self._menu_interval)
        
        # Порог уведомлений
        self._act_threshold = self.addAction(TextStore.Menu.ITEM_THRESHOLD, self._ask_threshold)
        self._act_threshold.setIcon(config.create_menu_emoji_icon("🔔"))
        
        self.addSeparator()
        self._add_section_header(TextStore.Menu.SECTION_CONFIG)
        
        # RPC (Открывает единое окно на вкладке RPC)
        self._act_rpc = self.addAction(TextStore.Menu.ITEM_RPC, lambda: self.requestOpenSettings.emit('rpc'))
        self._act_rpc.setIcon(config.create_menu_status_icon(False))
        
        # API Key (Открывает единое окно на вкладке API)
        self._act_apikey = self.addAction(TextStore.Menu.ITEM_API, lambda: self.requestOpenSettings.emit('api'))
        self._act_apikey.setIcon(config.create_menu_status_icon(False))
        
        self.addSeparator()
        self._add_section_header(TextStore.Menu.SECTION_TASKS)
        
        # Действия
        act_refresh = self.addAction(TextStore.Menu.ITEM_REFRESH, self.requestForceRefresh.emit)
        act_refresh.setIcon(config.create_menu_emoji_icon("🔄"))
        
        act_test = self.addAction(TextStore.Menu.ITEM_TEST_NOTIFY, self.requestTestNotify.emit)
        act_test.setIcon(config.create_menu_emoji_icon("💬"))
        
        # Проверка обновлений
        act_update = self.addAction(TextStore.Menu.ITEM_CHECK_UPDATES, self.requestCheckUpdates.emit)
        act_update.setIcon(config.create_menu_emoji_icon("⬇️"))
        
        self.addSeparator()
        
        # Инфо и Выход
        act_about = self.addAction(TextStore.Menu.ITEM_ABOUT, self._show_about)
        act_about.setIcon(config.create_menu_emoji_icon("ℹ️"))
        
        act_exit = self.addAction(TextStore.Menu.ITEM_EXIT, self.requestExit.emit)
        act_exit.setIcon(config.create_menu_emoji_icon("✖️"))
    
    def _on_about_to_show(self):
        """Обновление текстов и иконок перед показом."""
        # Reactive UI: Индикация зависит от реального режима работы (цветовой темы),
        # который устанавливается в ui_widgets.py на основе источника данных.
        active_mode = config._ACTIVE_MODE
        is_api_active = (active_mode == "api")
        is_rpc_active = (active_mode == "rpc")
        
        # Логика стиля (тема) теперь берется из глобального конфига (State-Driven)
        current_style = config.get_menu_stylesheet()
        self.setStyleSheet(current_style)
        if self._menu_interval:
            self._menu_interval.setStyleSheet(current_style)
        
        if self._act_rpc:
            self._act_rpc.setText(TextStore.Menu.MODE_RPC)
            self._act_rpc.setIcon(config.create_menu_status_icon(is_rpc_active))
        
        if self._act_apikey:
            self._act_apikey.setText(TextStore.Menu.MODE_API)
            self._act_apikey.setIcon(config.create_menu_status_icon(is_api_active))
        
        if self._act_threshold:
            val = float(self._s.value("core/threshold_gwei", 0.0))
            if val > 0:
                txt = TextStore.Menu.ITEM_THRESHOLD_FMT.format(val)
            else:
                txt = TextStore.Menu.ITEM_THRESHOLD_OFF
            self._act_threshold.setText(txt)
        
        # Гарантируем, что меню останется поверх всех окон
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
    
    def _update_interval_menu_icons(self):
        """Обновление галочек в подменю интервалов."""
        if not self._menu_interval: return
        cur = int(self._s.value("core/poll_interval_s", 30))
        presets = [5, 15, 30, 60]
        is_custom = cur not in presets
        
        for action in self._menu_interval.actions():
            data = action.data()
            if data is None: continue
            is_active = (data == "custom" and is_custom) or (isinstance(data, int) and data == cur)
            action.setIcon(config.create_menu_status_icon(is_active))
    
    # --- Dialog Launchers ---
    
    def _ask_custom_interval(self):
        dlg = ui_dialogs.RoyalNumInputDialog(
            self,
            TextStore.Settings.TITLE_INTERVAL,
            TextStore.Settings.LBL_INTERVAL,
            30, 5, 3600, 0
        )
        if dlg.exec() == QDialog.Accepted:
            self.requestSetInterval.emit(int(dlg.get_value()))
    
    def _ask_threshold(self):
        cur = float(self._s.value("core/threshold_gwei", 0.0))
        dlg = ui_dialogs.RoyalNumInputDialog(
            self,
            TextStore.Settings.TITLE_THRESHOLD,
            TextStore.Settings.LBL_THRESHOLD,
            cur, 0, 100000, 3
        )
        if dlg.exec() == QDialog.Accepted:
            val = dlg.get_value()
            self._s.setValue("core/threshold_gwei", float(val))
            self.requestSetThreshold.emit(float(val))
    
    def _show_about(self):
        dlg = ui_dialogs.AboutDialog(self)
        dlg.exec()