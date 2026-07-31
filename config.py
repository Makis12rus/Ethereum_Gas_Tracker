from __future__ import annotations

# -*- coding: utf-8 -*-

"""
Аннотация

🧩 1. Назначение файла
- Единый источник конфигурации (SSOT) для всего приложения.
- Содержит метаданные, константы, настройки шрифтов и цветовую палитру.
- Отвечает за генерацию графических ассетов (иконки) и стилей (QSS).

🧱 2. Компоненты
- Metadata: Версии, ID, User-Agent, Генератор имени файла.
- Palette: Цвета для темной темы (Obsidian/Neon/Gold).
- Asset Factory: Генерация иконок (QPixmap) и QSS стилей.
- Font Manager: Управление шрифтами и масштабированием.

⚙️ 3. Особенности
- Отсутствие зависимостей от логики приложения.
- Чистые функции для генерации графики и стилей.
- Гарантия неизменности внешнего вида (Pixel Perfect).
"""

import os
import platform
from typing import Tuple, Optional, Set, Dict

from PySide6.QtCore import Qt, QRect, QSettings
from PySide6.QtGui import (
    QColor, QFont, QFontDatabase, QPainter, QPixmap,
    QIcon, QBrush, QLinearGradient, QPalette, QRadialGradient, QPen
)
from PySide6.QtWidgets import QApplication

# -------------------------------------------------------------------------
# 1. МЕТАДАННЫЕ (Metadata & System ID)
# -------------------------------------------------------------------------

# Версия приложения
APP_VERSION = "0.9.10"

# Названия
APP_NAME_SYSTEM = "Ethereum Gas Tracker"
APP_NAME_DISPLAY = "Ethereum Gas Tracker"
ORG_NAME = "Makis's Software"

# Подробное описание для метаданных EXE
APP_DESCRIPTION_LONG = (
    "Компактный, ненавязчивый виджет для Windows, "
    "который отображает цену газа (Gwei) в реальном времени. "
)

# Ссылки
DONATE_URL = "https://etherscan.io/address/0x0b628838aeddfc8279879e94af8c8002039d7056"

# Системные идентификаторы (Windows)
APP_AUMID = "EthereumGasTracker.GasTracker"
LOCK_FILE_NAME = "ethereum_gas_tracker.lock"


def get_executable_filename(version: str = APP_VERSION) -> str:
    """
    Генерирует стандартизированное имя исполняемого файла.
    Формат: EthereumGasTracker_v0.9.0.exe
    Используется в build.py и core.py для Side-by-Side обновлений.
    """
    safe_name = APP_NAME_SYSTEM.replace(" ", "")
    return f"{safe_name}_v{version}.exe"


def _generate_user_agent() -> bytes:
    """
    Генерирует User-Agent для HTTP запросов.
    Формат: AppName/Version (NetworkLib; OS)
    """
    try:
        os_info = f"{platform.system()} {platform.release()}"
        ua_string = f"{APP_NAME_SYSTEM}/{APP_VERSION} (QtNetwork; {os_info})"
        return ua_string.encode("utf-8")
    except Exception:
        return b"Ethereum Gas Tracker (QtNetwork)"


# Готовый байтовый заголовок для QNetworkRequest
NETWORK_USER_AGENT = _generate_user_agent()


# Хелперы для заголовков окон
def get_window_title() -> str:
    return APP_NAME_DISPLAY


def get_about_caption() -> str:
    return f"{APP_NAME_DISPLAY} {APP_VERSION}"


def get_tray_tooltip() -> str:
    return f"{APP_NAME_DISPLAY} {APP_VERSION}"


# -------------------------------------------------------------------------
# 2. ЦВЕТОВАЯ ПАЛИТРА (Colors & Palette)
# -------------------------------------------------------------------------

def _blend_colors(fg_hex: str, bg_hex: str, ratio: float) -> str:
    """Смешивает два цвета (HEX) в заданной пропорции."""
    c_fg = QColor(fg_hex)
    c_bg = QColor(bg_hex)
    r = int(c_fg.red() * ratio + c_bg.red() * (1 - ratio))
    g = int(c_fg.green() * ratio + c_bg.green() * (1 - ratio))
    b = int(c_fg.blue() * ratio + c_bg.blue() * (1 - ratio))
    return QColor(r, g, b).name()


# Основные цвета панели (Dock Mode) - RGBA для QPainter
PANEL_FG_RGBA: Tuple[int, int, int, int] = (240, 240, 240, 255)
DOCK_BG_RGBA: Tuple[int, int, int, int] = (0, 0, 0, 1)  # Alpha=1 для кликабельности
DOCK_MARGIN_RIGHT_PX: int = 4

# Индикация цены (Traffic Light)
GAS_PRICE_LOW_RGBA: Tuple[int, int, int, int] = (0, 255, 0, 255)
GAS_PRICE_MID_RGBA: Tuple[int, int, int, int] = (255, 165, 0, 255)
GAS_PRICE_HIGH_RGBA: Tuple[int, int, int, int] = (255, 0, 0, 255)
GAS_PRICE_STALE_RGBA: Tuple[int, int, int, int] = (150, 150, 150, 255)

# Тренды
TREND_UP_RGBA: Tuple[int, int, int, int] = (255, 0, 0, 255)
TREND_DOWN_RGBA: Tuple[int, int, int, int] = (0, 255, 0, 255)

# Вспышки (Flash)
PANEL_FLASH_DURATION_MS: int = 500
PANEL_FLASH_LOW_RGBA: Tuple[int, int, int, int] = (0, 255, 0, 255)
PANEL_FLASH_MID_RGBA: Tuple[int, int, int, int] = (255, 165, 0, 255)
PANEL_FLASH_HIGH_RGBA: Tuple[int, int, int, int] = (255, 0, 0, 255)

# Neon & Obsidian Palette (Popup & UI) - HEX Strings
COLOR_NEON_GREEN: str = "#00E050"
COLOR_NEON_ORANGE: str = "#FFA500"
COLOR_NEON_RED: str = "#FF453A"
COLOR_ETH_BLUE: str = "#4A90E2"

COLOR_OBSIDIAN_BG_START: str = "#2b2b2b"
COLOR_OBSIDIAN_BG_END: str = "#1a1a1a"
COLOR_BORDER_LIGHT: str = "rgba(255, 255, 255, 0.1)"

COLOR_TEXT_WHITE: str = "#FFFFFF"
COLOR_TEXT_GRAY: str = "#888888"
COLOR_TEXT_LIGHT_GRAY: str = "#AAAAAA"

COLOR_HEADER_BG: str = "#1e1e1e"
COLOR_HEADER_BORDER: str = "#333333"

# Royal Palette (Dialogs)
COLOR_ROYAL_BG_START: str = "#2b2b2b"
COLOR_ROYAL_BG_END: str = "#151515"
COLOR_ROYAL_GOLD: str = "#FFD700"
COLOR_ROYAL_BLUE_NEON: str = "#4A90E2"
COLOR_ROYAL_INPUT_BG: str = "#101010"
COLOR_ROYAL_BORDER: str = "#333333"

# Onboarding Cards (Wizard)
COLOR_CARD_BORDER_DEFAULT: str = "#444444"
COLOR_CARD_BG_DEFAULT: str = "rgba(255, 255, 255, 0.03)"

COLOR_CARD_BORDER_API: str = COLOR_ROYAL_BLUE_NEON  # #4A90E2
COLOR_CARD_BG_API: str = "rgba(74, 144, 226, 0.1)"
COLOR_CARD_GLOW_API: str = COLOR_ROYAL_BLUE_NEON

COLOR_CARD_BORDER_RPC: str = COLOR_ROYAL_GOLD  # #FFD700
COLOR_CARD_BG_RPC: str = "rgba(255, 215, 0, 0.1)"
COLOR_CARD_GLOW_RPC: str = COLOR_ROYAL_GOLD

# Glow Settings
CARD_GLOW_WIDTH: int = 12
CARD_GLOW_ALPHA_MAX: int = 50

# Иконки (Unicode Emoji)
ICON_LOW: str = "🐢"
ICON_MID: str = "🙂"
ICON_HIGH: str = "🚀"

# -------------------------------------------------------------------------
# GLOBAL THEME STATE (State-Driven Styling)
# -------------------------------------------------------------------------

_ACTIVE_MODE = "api"  # 'api' or 'rpc'


def set_active_mode(mode: str) -> None:
    """Устанавливает активный режим для глобальной темы."""
    global _ACTIVE_MODE
    _ACTIVE_MODE = mode


def reset_active_mode() -> None:
    """Сбрасывает активный режим в значение по умолчанию (для Soft Reset)."""
    global _ACTIVE_MODE
    _ACTIVE_MODE = "api"


def get_active_accent_color() -> str:
    """Возвращает акцентный цвет в зависимости от текущего режима."""
    return COLOR_ROYAL_BLUE_NEON if _ACTIVE_MODE == "api" else COLOR_ROYAL_GOLD


# -------------------------------------------------------------------------
# 3. ШРИФТЫ И ГЕОМЕТРИЯ (Fonts & Geometry)
# -------------------------------------------------------------------------

POPUP_CARD_WIDTH_PX: int = 160
NEON_BORDER_WIDTH: int = 3

ABOUT_TITLE_PT: int = 14
ABOUT_BODY_PT: int = 10
ABOUT_FOOTER_PT: int = 8

DEFAULT_FONT_FAMILY: str = "Consolas"
DEFAULT_FONT_PT: int = 11
SEGOE_FONT_FAMILY: str = "Segoe UI"

# Кэш доступных шрифтов
_AVAILABLE_FONTS_CACHE: Optional[Set[str]] = None


def _get_cached_fonts() -> Set[str]:
    global _AVAILABLE_FONTS_CACHE
    if _AVAILABLE_FONTS_CACHE is None:
        _AVAILABLE_FONTS_CACHE = {f.lower() for f in QFontDatabase.families()}
    return _AVAILABLE_FONTS_CACHE


def _resolve_font_family(raw_family: Optional[str]) -> str:
    """Выбирает наиболее подходящий шрифт из доступных в системе."""
    fam = (raw_family or "").strip()
    if not fam or fam.lower() == "segoe ui":
        fam = DEFAULT_FONT_FAMILY
    
    cached = _get_cached_fonts()
    if fam.lower() in cached:
        return fam
    if DEFAULT_FONT_FAMILY.lower() in cached:
        return DEFAULT_FONT_FAMILY
    return QFont().defaultFamily()


def font_from_settings(settings: Optional[QSettings]) -> QFont:
    """Создает QFont для основного виджета на основе настроек."""
    family = DEFAULT_FONT_FAMILY
    size = DEFAULT_FONT_PT
    
    if settings:
        settings.beginGroup("core")
        f_val = settings.value("font_family", DEFAULT_FONT_FAMILY)
        s_val = settings.value("font_size_pt", DEFAULT_FONT_PT)
        settings.endGroup()
        
        family = _resolve_font_family(str(f_val))
        try:
            size = int(s_val)
        except (ValueError, TypeError):
            size = DEFAULT_FONT_PT
    
    f = QFont(family, max(6, min(size, 72)))
    f.setStyleStrategy(QFont.PreferAntialias)
    return f


def get_popup_font(role: str) -> QFont:
    """Фабрика шрифтов для элементов попапа."""
    f = QFont(SEGOE_FONT_FAMILY, 9)
    if role == 'title':
        f.setPointSize(9)
        f.setBold(True)
        f.setLetterSpacing(QFont.AbsoluteSpacing, 1.0)
    elif role == 'price':
        f.setPointSize(14)
        f.setBold(True)
    elif role == 'detail':
        f.setPointSize(8)
    elif role == 'footer':
        f.setPointSize(8)
        f.setBold(True)
    elif role == 'header_std':
        f.setPointSize(9)
    elif role == 'header_bold':
        f.setPointSize(9)
        f.setBold(True)
    return f


# -------------------------------------------------------------------------
# 4. ФАБРИКА АССЕТОВ (Asset Factory)
# -------------------------------------------------------------------------

def create_tray_icon(color: QColor) -> QIcon:
    """Создает иконку для трея (цветной круг)."""
    pm = QPixmap(32, 32)
    pm.fill(Qt.transparent)
    with QPainter(pm) as p:
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(color)
        p.setPen(Qt.NoPen)
        p.drawEllipse(2, 2, 28, 28)
    return QIcon(pm)


def create_menu_emoji_icon(emoji: str) -> QIcon:
    """Создает иконку меню из эмодзи."""
    size = 24
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    with QPainter(pixmap) as painter:
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        font = QFont("Segoe UI Emoji", 14)
        painter.setFont(font)
        painter.drawText(QRect(0, 0, size, size), Qt.AlignCenter, emoji)
    return QIcon(pixmap)


def create_menu_status_icon(active: bool) -> QIcon:
    """Создает иконку статуса (цветная точка с эффектом свечения)."""
    size = 16
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    
    with QPainter(pixmap) as painter:
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        
        if active:
            # Radial Gradient for Glow Effect
            # Center (8, 8), Radius 8
            grad = QRadialGradient(8, 8, 6)
            c = QColor(COLOR_NEON_GREEN)
            
            # Core (Solid)
            grad.setColorAt(0.0, c)
            grad.setColorAt(0.5, c)  # Hard core (matches inactive size)
            
            # Glow (Fade out)
            c_transparent = QColor(c)
            c_transparent.setAlpha(0)
            grad.setColorAt(1.0, c_transparent)
            
            painter.setBrush(QBrush(grad))
            painter.drawEllipse(0, 0, 16, 16)
        else:
            # Inactive (Gray Flat)
            painter.setBrush(QBrush(QColor("#666666")))
            painter.drawEllipse(4, 4, 8, 8)
    
    return QIcon(pixmap)


def get_status_icon(status_type: str) -> QIcon:
    """Генерирует иконку статуса валидации (Loading/OK/Error)."""
    size = 14  # Чуть меньше строки
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    
    with QPainter(pixmap) as p:
        p.setRenderHint(QPainter.Antialiasing)
        
        if status_type == "loading":
            # Желтое кольцо
            pen = QPen(QColor(COLOR_ROYAL_GOLD))
            pen.setWidth(2)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(2, 2, 10, 10)
        
        elif status_type == "ok":
            # Зеленая галочка
            pen = QPen(QColor(COLOR_NEON_GREEN))
            pen.setWidth(2)
            p.setPen(pen)
            p.drawLine(3, 7, 6, 10)
            p.drawLine(6, 10, 11, 3)
        
        elif status_type == "error":
            # Красный крестик
            pen = QPen(QColor(COLOR_NEON_RED))
            pen.setWidth(2)
            p.setPen(pen)
            p.drawLine(3, 3, 11, 11)
            p.drawLine(11, 3, 3, 11)
    
    return QIcon(pixmap)


# -------------------------------------------------------------------------
# 5. STYLESHEETS (QSS Generators)
# -------------------------------------------------------------------------

def get_menu_stylesheet(is_api_mode: bool = False) -> str:
    """
    Генерирует QSS для меню с цветовым кодированием режима.
    RPC (Default) = Gold/Yellow
    API (Secure)  = Blue (Etherscan)
    """
    # Игнорируем аргумент, используем глобальное состояние
    is_api = (_ACTIVE_MODE == "api")
    
    # Динамически вычисляем акцентный цвет и фон
    accent = get_active_accent_color()
    menu_tinted_bg = _blend_colors(accent, COLOR_OBSIDIAN_BG_START, 0.20)
    
    if is_api:
        # API Mode: Blue Accents (Etherscan Style)
        sel_bg_start = "rgba(74, 144, 226, 0.15)"
        sel_bg_end = "rgba(74, 144, 226, 0.02)"
        sel_border = "rgba(74, 144, 226, 0.3)"
        top_border_col = COLOR_ETH_BLUE
    else:
        # RPC Mode: Gold Accents (Default)
        sel_bg_start = "rgba(255, 215, 0, 0.15)"
        sel_bg_end = "rgba(255, 215, 0, 0.02)"
        sel_border = "rgba(255, 215, 0, 0.3)"
        top_border_col = COLOR_ROYAL_GOLD
    
    return f"""
        QMenu {{
            background: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 {menu_tinted_bg},
                stop:0.1 {COLOR_OBSIDIAN_BG_START},
                stop:1 {COLOR_OBSIDIAN_BG_END}
            );
            border: 1px solid {COLOR_BORDER_LIGHT};
            border-top: {NEON_BORDER_WIDTH}px solid {top_border_col};
            border-radius: 8px;
            padding: 4px;
            color: {COLOR_TEXT_WHITE};
            min-width: 240px;
        }}
        QMenu::item {{
            background-color: transparent;
            padding: 6px 16px 6px 30px;
            border-radius: 6px;
            margin: 2px 6px;
            border: 1px solid transparent;
            color: {COLOR_TEXT_WHITE};
            font-family: "{SEGOE_FONT_FAMILY}", sans-serif;
            font-size: 10pt;
        }}
        QMenu::item:selected {{
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:1,
                stop:0 {sel_bg_start},
                stop:1 {sel_bg_end}
            );
            border: 1px solid {sel_border};
        }}
        QMenu::item:disabled {{ color: #666666; }}
        QMenu::separator {{
            height: 1px;
            background-color: #454545;
            margin: 4px 0px;
        }}
        QMenu::icon {{ left: 4px; }}
    """


# Сохраняем константу для обратной совместимости (по умолчанию RPC/Gold)
MENU_STYLESHEET = get_menu_stylesheet(is_api_mode=False)

MENU_HEADER_STYLESHEET = f"""
    QLabel {{
        color: #aaaaaa;
        font-family: "{SEGOE_FONT_FAMILY}", sans-serif;
        font-size: 9pt;
        font-weight: normal;
        padding: 4px 12px;
        background: transparent;
    }}
"""


def get_card_config(card_type: str) -> Dict[str, str]:
    """Возвращает цвет и иконку для карточки газа."""
    if card_type == "low":
        return {"color": COLOR_NEON_GREEN, "icon": ICON_LOW}
    elif card_type == "mid":
        return {"color": COLOR_NEON_ORANGE, "icon": ICON_MID}
    else:
        return {"color": COLOR_NEON_RED, "icon": ICON_HIGH}


def get_card_stylesheet(card_type: str) -> str:
    """QSS для карточки газа (Obsidian + Neon Accent)."""
    cfg = get_card_config(card_type)
    accent_hex = cfg["color"]
    tinted_bg = _blend_colors(accent_hex, COLOR_OBSIDIAN_BG_START, 0.15)
    
    return f"""
        QFrame {{
            background: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 {tinted_bg},
                stop:0.3 {COLOR_OBSIDIAN_BG_START},
                stop:1 {COLOR_OBSIDIAN_BG_END}
            );
            border: 1px solid {COLOR_BORDER_LIGHT};
            border-radius: 8px;
            border-top: 2px solid {accent_hex};
        }}
    """


def get_popup_header_stylesheet() -> str:
    return f"""
        background-color: {COLOR_HEADER_BG};
        border-radius: 8px;
        border: 1px solid {COLOR_HEADER_BORDER};
    """


def get_royal_button_style(role: str = "primary", color_override: Optional[str] = None) -> str:
    """QSS для кнопок (Primary/Secondary) с динамической темой."""
    # Unified Ghost Style for both roles
    accent = color_override if color_override else get_active_accent_color()
    c_accent = QColor(accent)
    r, g, b = c_accent.red(), c_accent.green(), c_accent.blue()
    
    return f"""
        QPushButton {{
            background: transparent;
            color: {accent};
            border: 1px solid {accent};
            border-radius: 6px;
            font-family: "{SEGOE_FONT_FAMILY}";
            font-size: 10pt;
            font-weight: bold;
            padding: 6px 12px;
        }}
        QPushButton:hover {{ background: rgba({r}, {g}, {b}, 0.1); }}
        QPushButton:pressed {{ background: rgba({r}, {g}, {b}, 0.2); }}
    """


def get_royal_input_style(error: bool = False) -> str:
    accent = get_active_accent_color()
    border_col = COLOR_NEON_RED if error else COLOR_ROYAL_BORDER
    focus_col = COLOR_NEON_RED if error else accent
    
    return f"""
        QLineEdit, QPlainTextEdit {{
            background-color: {COLOR_ROYAL_INPUT_BG};
            color: white;
            border: 1px solid {border_col};
            border-radius: 6px;
            padding: 8px;
            font-family: "Consolas", monospace;
            font-size: 10pt;
            selection-background-color: {accent};
        }}
        QLineEdit:focus, QPlainTextEdit:focus {{
            border: 1px solid {focus_col};
        }}
    """


def get_royal_close_btn_style() -> str:
    return """
        QPushButton {
            background: transparent;
            color: #888888;
            border: none;
            font-weight: bold;
            font-size: 12pt;
        }
        QPushButton:hover { color: #FF453A; }
    """


def get_royal_scrollbar_style() -> str:
    accent = get_active_accent_color()
    return f"""
        QScrollBar:vertical {{
            border: none;
            background: {COLOR_ROYAL_BG_END};
            width: 8px;
            margin: 0px 0px 0px 0px;
            border-radius: 4px;
        }}
        QScrollBar::handle:vertical {{
            background: #444444;
            min-height: 20px;
            border-radius: 4px;
        }}
        QScrollBar::handle:vertical:hover {{ background: {accent}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
    """


def get_progress_button_style(percent: int) -> str:
    """
    Генерирует QSS для кнопки с эффектом прогресс-бара.
    Фон заливается цветом (Gold) слева направо в зависимости от процента.
    """
    # Ограничиваем процент от 0 до 100
    p = max(0, min(100, int(percent)))
    
    # Цвет прогресса (полупрозрачный золотой)
    prog_color = "rgba(255, 215, 0, 0.2)"
    # Цвет остатка (прозрачный)
    base_color = "transparent"
    
    # Резкий переход градиента для создания четкой границы
    stop1 = f"{p / 100.0:.4f}"
    stop2 = f"{(p + 0.1) / 100.0:.4f}"  # Небольшой сдвиг для анти-алиасинга
    
    return f"""
        QPushButton {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop: 0 {prog_color},
                stop: {stop1} {prog_color},
                stop: {stop2} {base_color},
                stop: 1 {base_color}
            );
            color: {COLOR_ROYAL_GOLD};
            border: 1px solid {COLOR_ROYAL_GOLD};
            border-radius: 6px;
            font-family: "{SEGOE_FONT_FAMILY}";
            font-size: 10pt;
            font-weight: bold;
            padding: 6px 12px;
        }}
    """


def apply_app_palette(app: QApplication, *, dark: bool = True) -> None:
    """Применяет профессиональную темную палитру к приложению."""
    if not dark:
        app.setPalette(app.style().standardPalette())
        return
    
    pal = QPalette()
    c_bg = QColor(24, 24, 24)
    c_text = QColor(235, 235, 235)
    c_base = QColor(30, 30, 30)
    
    pal.setColor(QPalette.Window, c_bg)
    pal.setColor(QPalette.WindowText, c_text)
    pal.setColor(QPalette.Base, c_base)
    pal.setColor(QPalette.AlternateBase, QColor(38, 38, 38))
    pal.setColor(QPalette.ToolTipBase, c_base)
    pal.setColor(QPalette.ToolTipText, c_text)
    pal.setColor(QPalette.Text, c_text)
    pal.setColor(QPalette.Button, QColor(45, 45, 45))
    pal.setColor(QPalette.ButtonText, c_text)
    pal.setColor(QPalette.Highlight, QColor(0, 120, 215))
    pal.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    
    app.setPalette(pal)


# -------------------------------------------------------------------------
# 6. NETWORK & RPC CONFIGURATION
# -------------------------------------------------------------------------

# Список зеркал для загрузки списка узлов (Fallback)
CHAINLIST_URLS = [
    "https://chainlist.org/rpcs.json",
    "https://raw.githubusercontent.com/DefiLlama/chainlist/main/constants/extraRpcs.js",  # Fallback 1
    "https://eth.llama.nodes.com/rpc"  # Fallback 2 (Direct RPC, not list, handled in logic)
]

# Параметры поиска узлов
RPC_CANDIDATE_SAMPLE = 30  # Количество случайных узлов для проверки
RPC_PING_TIMEOUT_MS = 2000  # Абсолютный таймаут на проверку одного узла (Latency)
RPC_TOP_RESULTS = 5  # Количество сохраняемых быстрых узлов

# Параметры адаптивного таймаута (Adaptive Timeout / Cutoff)
# Логика: Если найдено TARGET_COUNT узлов, остальные отсекаются через (Time_Nth + Buffer)
RPC_ADAPTIVE_TARGET_COUNT = 5  # Сколько узлов нужно найти, чтобы включить таймер смерти
RPC_ADAPTIVE_BUFFER_BASE_MS = 200  # Минимальный запас времени (мс)
RPC_ADAPTIVE_BUFFER_FACTOR = 0.2  # Динамический запас (20% от времени 5-го узла)