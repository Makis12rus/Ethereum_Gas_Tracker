from __future__ import annotations

# -*- coding: utf-8 -*-

"""
Аннотация

🧩 1. Назначение файла
- Основные виджеты пользовательского интерфейса (HUD).
- Содержит главный док-виджет и всплывающие окна состояния.
- Отвечает за отрисовку данных в реальном времени.

🧱 2. Компоненты
- AppUI: Главный виджет (View). Отрисовка Gwei, трея, обработка событий.
- GasDetailPopup: Всплывающее окно с детальной информацией.
- _GasCard: Карточка тарифа (Low/Mid/High).

⚙️ 3. Особенности
- Direct 2D отрисовка (QPainter) для производительности.
- Взаимодействие с win_logic для позиционирования и Z-Order.
- Интеграция с menu для управления настройками.
- Использование TextStore для локализации.
"""

import sys
from typing import Optional, Tuple, Any, Dict

from PySide6.QtCore import (
    Qt, Signal, QSettings, QTimer, QEvent, QRect, QPoint
)
from PySide6.QtGui import (
    QFont, QIcon, QPainter, QFontMetrics, QPaintEvent, QColor, QPen, QBrush
)
from PySide6.QtWidgets import (
    QApplication, QWidget, QSystemTrayIcon, QVBoxLayout,
    QHBoxLayout, QLabel, QFrame
)

# Импорты модулей проекта
import config
import win_logic
import menu
from core import TextStore  # Источник текстов


# -------------------------------------------------------------------------
# 1. POPUP COMPONENTS
# -------------------------------------------------------------------------

class _GasCard(QFrame):
    """
    Карточка с информацией о цене газа (Low/Mid/High).
    Используется внутри GasDetailPopup.
    """
    
    def __init__(self, title_text: str, card_type: str, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        self._card_type = card_type
        
        # Получаем конфигурацию из config.py
        cfg = config.get_card_config(card_type)
        accent_color = cfg["color"]
        icon = cfg["icon"]
        
        self.setStyleSheet(config.get_card_stylesheet(card_type))
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 10)
        layout.setSpacing(2)
        
        # Заголовок
        self.lbl_title = QLabel(f"{icon}  {title_text.upper()}")
        self.lbl_title.setAlignment(Qt.AlignCenter)
        self.lbl_title.setFont(config.get_popup_font('title'))
        self.lbl_title.setStyleSheet(f"color: {accent_color}; border: none; background: transparent;")
        layout.addWidget(self.lbl_title)
        
        layout.addSpacing(4)
        
        # Цена
        self.lbl_price = QLabel(TextStore.Hud.VAL_PLACEHOLDER)
        self.lbl_price.setAlignment(Qt.AlignCenter)
        self.lbl_price.setFont(config.get_popup_font('price'))
        self.lbl_price.setStyleSheet(f"color: {config.COLOR_TEXT_WHITE}; border: none; background: transparent;")
        layout.addWidget(self.lbl_price)
        
        # Детали (Base/Prio)
        # Формируем начальную строку: "Base: - | Prio: -"
        initial_details = f"{TextStore.Popup.LBL_BASE} - | {TextStore.Popup.LBL_PRIO} -"
        self.lbl_details = QLabel(initial_details)
        self.lbl_details.setAlignment(Qt.AlignCenter)
        self.lbl_details.setFont(config.get_popup_font('detail'))
        self.lbl_details.setStyleSheet(f"color: {config.COLOR_TEXT_GRAY}; border: none; background: transparent;")
        layout.addWidget(self.lbl_details)
        
        layout.addSpacing(8)
        
        # Разделитель
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Plain)
        line.setStyleSheet(f"background-color: {config.COLOR_BORDER_LIGHT}; border: none; max-height: 1px;")
        layout.addWidget(line)
        
        layout.addSpacing(6)
        
        # Футер (USD / Время)
        self.lbl_cost_time = QLabel("$ -  •  ~ -")
        self.lbl_cost_time.setAlignment(Qt.AlignCenter)
        self.lbl_cost_time.setFont(config.get_popup_font('footer'))
        self.lbl_cost_time.setStyleSheet(f"color: {config.COLOR_TEXT_LIGHT_GRAY}; border: none; background: transparent;")
        layout.addWidget(self.lbl_cost_time)
    
    def update_values(self, total: float, base: float, eth_price: float):
        self.lbl_price.setText(f"{total:.3f} GWEI")
        prio = max(0.0, total - base)
        
        # Формируем строку деталей из локализации
        details_text = f"{TextStore.Popup.LBL_BASE}{base:.3f}  {TextStore.Popup.LBL_PRIO}{prio:.3f}"
        self.lbl_details.setText(details_text)
        
        cost_usd = 0.0
        if eth_price > 0:
            cost_usd = (total * 21000 * eth_price) / 1e9
        
        time_est = "30s"
        if self._card_type == "low":
            time_est = TextStore.Popup.TIME_EST_LOW
        elif self._card_type == "mid":
            time_est = TextStore.Popup.TIME_EST_MID
        elif self._card_type == "high":
            time_est = TextStore.Popup.TIME_EST_HIGH
        
        # Используем шаблон футера из локализации
        footer_text = TextStore.Popup.FOOTER_TEMPLATE.format(cost=cost_usd, time=time_est)
        self.lbl_cost_time.setText(footer_text)


class GasDetailPopup(QWidget):
    """
    Всплывающее окно с детальной информацией.
    Появляется при наведении мыши на основной виджет.
    """
    
    def __init__(self, parent=None):
        super().__init__(parent, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 5, 0, 0)
        main_layout.setSpacing(6)
        
        # Header Frame
        self.header_frame = QFrame(self)
        self.header_frame.setStyleSheet(config.get_popup_header_stylesheet())
        
        header_layout = QHBoxLayout(self.header_frame)
        header_layout.setContentsMargins(12, 6, 12, 6)
        header_layout.setSpacing(4)
        
        self.lbl_timer = QLabel(TextStore.Hud.STATUS_WAIT)
        self.lbl_timer.setFont(config.get_popup_font('header_std'))
        self.lbl_timer.setStyleSheet(f"color: {config.COLOR_TEXT_GRAY}; border: none; background: transparent;")
        
        self.lbl_eth_price = QLabel(f"{TextStore.Popup.PREFIX_ETH_PRICE} -")
        self.lbl_eth_price.setFont(config.get_popup_font('header_bold'))
        self.lbl_eth_price.setStyleSheet(f"color: {config.COLOR_ETH_BLUE}; border: none; background: transparent;")
        self.lbl_eth_price.setAlignment(Qt.AlignCenter)
        
        self.lbl_updated = QLabel(TextStore.Popup.LBL_UPDATED_DEFAULT)
        self.lbl_updated.setFont(config.get_popup_font('header_std'))
        self.lbl_updated.setStyleSheet(f"color: {config.COLOR_TEXT_GRAY}; border: none; background: transparent;")
        self.lbl_updated.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        
        header_layout.addWidget(self.lbl_timer)
        header_layout.addStretch()
        header_layout.addWidget(self.lbl_eth_price)
        header_layout.addStretch()
        header_layout.addWidget(self.lbl_updated)
        
        main_layout.addWidget(self.header_frame)
        
        # Cards Layout
        cards_layout = QHBoxLayout()
        cards_layout.setContentsMargins(0, 0, 0, 0)
        cards_layout.setSpacing(8)
        
        # Используем локализованные заголовки
        self.card_low = _GasCard(TextStore.Popup.TITLE_LOW, "low", self)
        self.card_mid = _GasCard(TextStore.Popup.TITLE_AVG, "mid", self)
        self.card_high = _GasCard(TextStore.Popup.TITLE_HIGH, "high", self)
        
        card_width = config.POPUP_CARD_WIDTH_PX
        for c in (self.card_low, self.card_mid, self.card_high):
            c.setFixedWidth(card_width)
            cards_layout.addWidget(c)
        
        main_layout.addLayout(cards_layout)
    
    def update_data(self, data: dict):
        eth_price = float(data.get("eth_price", 0.0))
        if eth_price > 0:
            self.lbl_eth_price.setText(f"{TextStore.Popup.PREFIX_ETH_PRICE}{eth_price:,.2f}")
        
        levels = data.get("levels", {})
        if not levels: return
        
        safe = float(levels.get("safe", 0))
        propose = float(levels.get("propose", 0))
        fast = float(levels.get("fast", 0))
        base = float(data.get("suggest_base_fee_gwei", data.get("detail", {}).get("base_fee_gwei", 0)))
        
        self.card_low.update_values(safe, base, eth_price)
        self.card_mid.update_values(propose, base, eth_price)
        self.card_high.update_values(fast, base, eth_price)
        self.adjustSize()
    
    def set_countdown(self, sec: int):
        self.lbl_timer.setText(f"{sec}s")
    
    def set_data_source(self, source_text: str):
        self.lbl_updated.setText(f"{source_text}")


# -------------------------------------------------------------------------
# 2. MAIN WIDGET (AppUI)
# -------------------------------------------------------------------------

class AppUI(QWidget):
    """
    Главный виджет приложения (Dock).
    Отображается поверх панели задач, содержит основную информацию.
    """
    # Сигналы для связи с Logic (Main)
    requestSetInterval = Signal(int)
    requestTestNotify = Signal()
    requestExit = Signal()
    requestSetThreshold = Signal(float)
    requestForceRefresh = Signal()
    
    def __init__(self, *, settings: QSettings) -> None:
        # Qt.Tool: Не показывает иконку в панели задач (как отдельное окно)
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint)
        
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setMouseTracking(True)
        
        if QApplication.instance():
            QApplication.instance().setQuitOnLastWindowClosed(False)
        
        self._s = settings
        
        # State
        self._last_dock_height = 0
        self._is_menu_visible = False
        self._is_fullscreen_mode = False  # New: Track fullscreen state
        
        self._last_data: Any = None
        self._price_text = TextStore.Hud.VAL_PLACEHOLDER
        self._trend_arrow = ""
        
        # Rendering State
        self._current_font = QFont()
        self._zones: Dict[str, Tuple[int, int]] = {}
        self._total_width = 0
        
        # Paint Cache (Optimization)
        self._cached_pen_price = QPen()
        self._cached_pen_trend = QPen()
        self._cached_brush_bg = QBrush()
        self._cached_brush_flash = QBrush()
        
        # Flash Timer (мигание при обновлении)
        self._last_lvl: Optional[str] = None
        self._flash_col: Optional[QColor] = None
        self._flash_timer = QTimer(self)
        self._flash_timer.setSingleShot(True)
        self._flash_timer.timeout.connect(lambda: setattr(self, '_flash_col', None) or self.repaint())
        
        # Z-Order Watchdog (New: Aggressive Protection)
        self._z_order_watchdog = QTimer(self)
        self._z_order_watchdog.setInterval(100)
        self._z_order_watchdog.setTimerType(Qt.CoarseTimer)
        self._z_order_watchdog.timeout.connect(self._enforce_z_order)
        self._z_order_watchdog.start()
        
        # Apply Ghost Overlay Style (ToolWindow + NoActivate) immediately
        if sys.platform == "win32":
            win_logic.WindowManager.set_ghost_overlay_style(int(self.winId()))
        
        # Colors Cache
        self._col_fg = QColor(*config.PANEL_FG_RGBA)
        self._col_price = self._col_fg
        self._col_trend = self._col_fg
        
        self._cols_lvl = {
            "low": QColor(*config.GAS_PRICE_LOW_RGBA),
            "mid": QColor(*config.GAS_PRICE_MID_RGBA),
            "high": QColor(*config.GAS_PRICE_HIGH_RGBA),
            "stale": QColor(*config.GAS_PRICE_STALE_RGBA),
        }
        self._col_trend_down = QColor(*config.TREND_DOWN_RGBA)
        self._col_trend_up = QColor(*config.TREND_UP_RGBA)
        
        # Init Paint Cache
        self._update_paint_cache()
        
        self._icon_cache: Dict[str, QIcon] = {}
        self._last_tray_color_key: Optional[str] = None
        
        # Используем шаблон заголовка из локализации
        self.setWindowTitle(TextStore.App.TITLE_TEMPLATE.format(
            name=config.APP_NAME_DISPLAY, version=config.APP_VERSION
        ))
        
        # Init Font
        self._current_font = config.font_from_settings(self._s)
        self._current_font.setPointSize(9)
        self._calculate_zones()
        self._update_fixed_size()
        
        # Sub-components
        self._popup = GasDetailPopup()
        self._menu = menu.AppMenu(parent=self, settings=self._s)
        self._connect_menu_signals()
        
        self._tray = self._build_tray()
    
    def _update_paint_cache(self):
        """Обновляет кэшированные кисти и перья."""
        self._cached_pen_price = QPen(self._col_price)
        self._cached_pen_trend = QPen(self._col_trend)
        
        rgba = config.DOCK_BG_RGBA
        if rgba[3] > 0:
            self._cached_brush_bg = QBrush(QColor(*rgba))
        else:
            self._cached_brush_bg = QBrush(Qt.NoBrush)
        
        if self._flash_col:
            self._cached_brush_flash = QBrush(self._flash_col)
        else:
            self._cached_brush_flash = QBrush(Qt.NoBrush)
    
    # --- WinAPI Hook (Show Desktop Fix & Active Z-Order Guard) ---
    def nativeEvent(self, eventType, message):
        if sys.platform == "win32" and eventType == "windows_generic_MSG":
            try:
                msg = win_logic.MSG.from_address(int(message))
                
                # Level 3: Hardening against Z-Order changes (Show Desktop / Taskbar Click)
                if msg.message == win_logic.WM_WINDOWPOSCHANGING:
                    # Don't fight if we are legitimately hidden (fullscreen mode)
                    if self._is_fullscreen_mode or not self.isVisible():
                        return super().nativeEvent(eventType, message)
                    
                    wp = win_logic.WINDOWPOS.from_address(msg.lParam)
                    
                    # Active Z-Order Locking
                    # 1. Force Z-Order to TopMost
                    wp.hwndInsertAfter = win_logic.HWND_TOPMOST
                    # 2. Remove NOZORDER flag (allow Z-order change to happen)
                    wp.flags &= ~win_logic.SWP_NOZORDER
                    # 3. Add NOACTIVATE flag (prevent focus stealing which confuses Taskbar)
                    wp.flags |= win_logic.SWP_NOACTIVATE
                
                # Level 2: Focus Loss Guard (Clicking Taskbar/Start)
                elif msg.message == win_logic.WM_ACTIVATE:
                    # Low-order word of wParam is the state. 0 = WA_INACTIVE
                    state = msg.wParam & 0xFFFF
                    if state == win_logic.WA_INACTIVE:
                        # Async re-assertion immediately after focus loss
                        QTimer.singleShot(0, self._enforce_z_order)
            
            except Exception:
                pass
        return super().nativeEvent(eventType, message)
    
    def _enforce_z_order(self):
        """Принудительное восстановление статуса TopMost."""
        # 1. Synchronous check for fullscreen (Just-in-Time)
        # Это предотвращает мерцание фокуса в играх, если таймер сработал до того,
        # как фоновый поток PositionWorker успел обновить статус.
        if sys.platform == "win32" and win_logic.ShellManager.is_fullscreen_app_running():
            self._is_fullscreen_mode = True
            if self.isVisible():
                self.hide()
            self._z_order_watchdog.stop()
            return
        
        # Если мы в полноэкранном режиме (flag) или скрыты - ничего не делаем
        if self._is_fullscreen_mode or not self.isVisible() or self._is_menu_visible:
            return
        
        hwnd = int(self.winId())
        # Если открыто системное меню (Пуск), используем "Ядерный сброс" (Toggle)
        is_system_overlay = win_logic.ShellManager.is_start_menu_open()
        win_logic.WindowManager.force_top_most(hwnd, toggle=is_system_overlay)
    
    def showEvent(self, event):
        """
        Level 1: Re-assertion on Show.
        Критично для восстановления Z-порядка после Soft Reset (hide -> show).
        """
        super().showEvent(event)
        if sys.platform == "win32":
            self._enforce_z_order()
    
    def _connect_menu_signals(self):
        if not self._menu: return
        self._menu.requestSetInterval.connect(self.requestSetInterval.emit)
        self._menu.requestSetThreshold.connect(self.requestSetThreshold.emit)
        self._menu.requestForceRefresh.connect(self._trigger_refresh)
        self._menu.requestTestNotify.connect(self.requestTestNotify.emit)
        self._menu.requestExit.connect(self.requestExit.emit)
        
        # requestOpenSettings обрабатывается в main.py напрямую через ui._menu
        
        self._menu.aboutToShow.connect(lambda: setattr(self, '_is_menu_visible', True))
        self._menu.aboutToHide.connect(lambda: setattr(self, '_is_menu_visible', False))
    
    def on_position_update(self, tray_hwnd: int, tray_rect: QRect, notify_rect: QRect, is_fullscreen: bool):
        """Слот для получения координат от win_logic."""
        # Smart Watchdog Logic: Fullscreen = Hide & Sleep
        if is_fullscreen:
            if self.isVisible():
                self.hide()
            self._is_fullscreen_mode = True
            if self._z_order_watchdog.isActive():
                self._z_order_watchdog.stop()
            return
        else:
            if not self.isVisible():
                self.show()
                # Force Z-Order immediately upon showing
                if sys.platform == "win32":
                    QTimer.singleShot(0, self._enforce_z_order)
            
            self._is_fullscreen_mode = False
            if not self._z_order_watchdog.isActive():
                self._z_order_watchdog.start()
        
        hwnd = int(self.winId())
        if not hwnd: return
        
        dpr = self.devicePixelRatio()
        
        # 1. Расчет высоты
        tb_h = tray_rect.height()
        self._set_dock_height(tb_h)
        
        # 2. Расчет геометрии через win_logic
        x, y, w, h = win_logic.PositionLogic.calculate_geometry(
            tray_rect, notify_rect, self.width(), self.height(), dpr
        )
        
        # 3. Применение
        win_logic.PositionLogic.apply_position(hwnd, x, y, w, h, self._is_menu_visible)
    
    def _set_dock_height(self, height: int):
        if height <= 0: return
        if self._last_dock_height == height: return
        self._last_dock_height = height
        
        target_h = int(height * 0.35)
        f = config.font_from_settings(self._s)
        f.setPixelSize(max(8, target_h))
        if f.pixelSize() > 32: f.setPixelSize(32)
        
        self._current_font = f
        self._calculate_zones()
        self._update_fixed_size()
        self.repaint()
    
    def _calculate_zones(self):
        fm = QFontMetrics(self._current_font)
        self._zones.clear()
        
        prefix = TextStore.Hud.PREFIX_ETH
        w_prefix = fm.horizontalAdvance(prefix)
        self._zones["prefix"] = (0, w_prefix)
        
        price_tmpl = "8888.888"
        w_price = fm.horizontalAdvance(price_tmpl)
        self._zones["price"] = (w_prefix, w_price)
        
        # Suffix: " Gwei ↗"
        suffix = TextStore.Hud.SUFFIX_GWEI + TextStore.Hud.ARROW_UP
        w_suffix = fm.horizontalAdvance(suffix)
        self._zones["suffix"] = (w_prefix + w_price, w_suffix)
        
        self._total_width = w_prefix + w_price + w_suffix
    
    def _update_fixed_size(self):
        pad = 4
        w = max(self._total_width + pad * 2, 100)
        self.resize(w, self.height())
    
    def paintEvent(self, e: QPaintEvent):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        
        rect = self.rect()
        
        # Background (Cached Brush)
        if self._cached_brush_bg.style() != Qt.NoBrush:
            p.setBrush(self._cached_brush_bg)
            p.drawRect(rect)
        
        # Flash (Cached Brush)
        if self._flash_col:
            # Update flash brush only if needed (usually handled in update_paint_cache)
            p.setBrush(self._cached_brush_flash)
            p.drawRect(rect)
        
        # Text
        p.setFont(self._current_font)
        fm = QFontMetrics(self._current_font)
        
        start_x = (rect.width() - self._total_width) / 2
        y = (rect.height() + fm.ascent() - fm.descent()) / 2
        
        if "prefix" in self._zones:
            x, _ = self._zones["prefix"]
            p.setPen(self._cached_pen_price)
            p.drawText(int(start_x + x), int(y), TextStore.Hud.PREFIX_ETH)
        
        if "price" in self._zones:
            x, w = self._zones["price"]
            p.setPen(self._cached_pen_price)
            txt_w = fm.horizontalAdvance(self._price_text)
            p.drawText(int(start_x + x + w - txt_w), int(y), self._price_text)
        
        if "suffix" in self._zones:
            x, _ = self._zones["suffix"]
            p.setPen(self._cached_pen_price)
            p.drawText(int(start_x + x), int(y), TextStore.Hud.SUFFIX_GWEI)
            
            arrow_x = start_x + x + fm.horizontalAdvance(TextStore.Hud.SUFFIX_GWEI)
            p.setPen(self._cached_pen_trend)
            p.drawText(int(arrow_x), int(y), self._trend_arrow.strip())
    
    def _trigger_refresh(self):
        self._price_text = "..."
        self._trend_arrow = ""
        self.repaint()
        self.requestForceRefresh.emit()
    
    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._trigger_refresh()
            e.accept()
        else:
            super().mouseDoubleClickEvent(e)
    
    def enterEvent(self, e: QEvent):
        if isinstance(self._last_data, dict):
            self._place_popup()
            self._popup.show()
            win_logic.WindowManager.set_window_pos(int(self._popup.winId()), 0, 0, 0, 0, top_most=True, no_activate=True)
        super().enterEvent(e)
    
    def leaveEvent(self, e: QEvent):
        self._popup.hide()
        super().leaveEvent(e)
    
    def _place_popup(self):
        self._popup.adjustSize()
        sz = self._popup.size()
        global_pos = self.mapToGlobal(QPoint(0, 0))
        x = global_pos.x() + (self.width() // 2) - (sz.width() // 2)
        y = global_pos.y() - sz.height() - 10
        
        scr = self.screen().availableGeometry() if self.screen() else QRect()
        if scr.isValid():
            if y < scr.top():
                y = global_pos.y() + self.height() + 10
            if x + sz.width() > scr.right():
                x = scr.right() - sz.width()
            if x < scr.left():
                x = scr.left()
        self._popup.move(x, y)
    
    def _build_tray(self) -> Optional[QSystemTrayIcon]:
        if not QSystemTrayIcon.isSystemTrayAvailable(): return None
        t = QSystemTrayIcon(self._make_icon(), self)
        t.setToolTip(config.get_tray_tooltip())
        if self._menu: t.setContextMenu(self._menu)
        t.activated.connect(lambda r: (self.show(), self.raise_(), self.activateWindow())
        if r == QSystemTrayIcon.Trigger else None)
        t.show()
        return t
    
    def _make_icon(self, color: Optional[QColor] = None) -> QIcon:
        color = color or self._col_fg
        key = color.name(QColor.NameFormat.HexArgb)
        if key in self._icon_cache: return self._icon_cache[key]
        
        # LRU-like cache cleanup
        if len(self._icon_cache) > 50:
            # Remove first 10 items
            keys_to_remove = list(self._icon_cache.keys())[:10]
            for k in keys_to_remove:
                del self._icon_cache[k]
        
        icon = config.create_tray_icon(color)
        self._icon_cache[key] = icon
        return icon
    
    def contextMenuEvent(self, e):
        if self._menu:
            self._menu.show_context_menu(e.globalPos(), self)
    
    # Методы для PositionManager (совместимость с menu)
    def set_menu_open(self, o: bool):
        self._is_menu_visible = o
    
    def on_state_info(self, has_key: bool, is_custom_rpc: bool):
        if self._menu:
            self._menu.update_state("memory" if has_key else "none", is_custom_rpc)
    
    def on_price_updated(self, data):
        self._last_data = data
        
        if isinstance(data, dict):
            # Reactive UI: Update global theme based on actual data source
            src = data.get("source", "none")
            if src == "etherscan":
                config.set_active_mode("api")
            elif src != "none":
                config.set_active_mode("rpc")
            
            # Determine display text for source
            if src == "etherscan":
                src_display = TextStore.Errors.SRC_ETHERSCAN
            elif src != "none":
                src_display = TextStore.Errors.SRC_RPC
            else:
                src_display = TextStore.Errors.SRC_NA
            
            if self._menu: self._menu.set_active_source(src)
            self._popup.update_data(data)
            self._popup.set_data_source(src_display)
        
        val = self._extract_price_value(data)
        is_stale = isinstance(data, dict) and data.get("is_stale", False)
        trend = data.get("trend", "") if isinstance(data, dict) else ""
        
        self._apply_color(val, is_stale, trend)
        
        new_text = f"{val:.3f}" if val is not None else "-"
        new_arrow = TextStore.Hud.ARROW_UP if trend == "up" else (TextStore.Hud.ARROW_DOWN if trend == "down" else "")
        
        if self._price_text != new_text or self._trend_arrow != new_arrow:
            self._price_text = new_text
            self._trend_arrow = new_arrow
            self.repaint()
    
    def on_countdown_tick(self, sec: int):
        self._popup.set_countdown(max(0, int(sec)))
    
    def show_notification(self, title: str, msg: str):
        if self._tray: self._tray.showMessage(title, msg, QSystemTrayIcon.Information, 5000)
    
    def _extract_price_value(self, data: Any) -> Optional[float]:
        if isinstance(data, (int, float)): return float(data)
        if not isinstance(data, dict): return None
        try:
            val = data.get("levels", {}).get("propose")
            if val is not None: return float(val)
        except Exception:
            pass
        try:
            val = data.get("propose_gwei")
            if val is not None: return float(val)
        except Exception:
            pass
        return None
    
    def _apply_color(self, val: Optional[float], is_stale: bool = False, trend: str = ""):
        lvl, col = None, self._col_fg
        
        if is_stale:
            lvl = "stale"
        elif val is not None:
            if val < 0.5:
                lvl = "low"
            elif val < 1.5:
                lvl = "mid"
            else:
                lvl = "high"
        
        if lvl:
            col = self._cols_lvl[lvl]
            self._col_price = col
        else:
            self._col_price = self._col_fg
        
        if trend == "up":
            self._col_trend = self._col_trend_up
        elif trend == "down":
            self._col_trend = self._col_trend_down
        else:
            self._col_trend = self._col_price
        
        if self._tray:
            color_key = col.name(QColor.NameFormat.HexArgb)
            if color_key != self._last_tray_color_key:
                self._tray.setIcon(self._make_icon(col))
                self._last_tray_color_key = color_key
        
        if lvl and not is_stale and lvl != self._last_lvl and self._last_lvl is not None:
            fl = getattr(config, f"PANEL_FLASH_{lvl.upper()}_RGBA", None)
            if fl:
                self._flash_col = QColor(*fl)
                self._update_paint_cache()  # Update flash brush
                self.repaint()
                self._flash_timer.start(config.PANEL_FLASH_DURATION_MS)
        
        # Update pens if colors changed
        self._update_paint_cache()
        self._last_lvl = lvl
    
    def force_ui_recovery(self):
        # Метод для Watchdog, если потребуется расширение логики
        pass