from __future__ import annotations

# -*- coding: utf-8 -*-

"""
Аннотация

🧩 1. Назначение файла
- Модуль "Мастера настройки" (Wizard).
- Содержит логику первоначальной настройки и выбора режима работы.
- Вынесен из ui_dialogs.py для облегчения структуры проекта.

🧱 2. Компоненты
- ApiKeySetupDialog: Главное окно настройки (API vs RPC).
- _OnboardingCard: Интерактивные карточки выбора режима.
- LineNumberEditor: Специализированный редактор списка RPC.

⚙️ 3. Особенности
- Наследуется от RoyalDialog (из ui_dialogs).
- Использует services для валидации ключей и поиска узлов.
- Использует TextStore для локализации.
"""

import re
from typing import Optional, List, Tuple

from PySide6.QtCore import (
    Qt, QEvent, QTimer, QRect, QSettings, Signal, QSize
)
from PySide6.QtGui import (
    QPainter, QPainterPath, QBrush, QPen, QColor, QCursor,
    QTextFormat, QGuiApplication
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QPlainTextEdit, QTextEdit, QSizePolicy,
    QScrollArea, QFrame, QStackedWidget, QDialog, QStyle
)

import config
import services  # Подключение слоя сервисов (вместо core)
from core import TextStore  # Источник текстов
from ui_dialogs import RoyalDialog  # Наследование от базового класса


# -------------------------------------------------------------------------
# 1. CUSTOM WIDGETS (LineNumberEditor & PingLatencyArea)
# -------------------------------------------------------------------------

class LineNumberArea(QWidget):
    """Вспомогательный виджет для отрисовки номеров строк (Слева)."""
    
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
    
    def sizeHint(self):
        return QSize(self.editor.lineNumberAreaWidth(), 0)
    
    def paintEvent(self, event):
        self.editor.lineNumberAreaPaintEvent(event)


class PingLatencyArea(QWidget):
    """Вспомогательный виджет для отрисовки пинга (Справа)."""
    
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
    
    def sizeHint(self):
        return QSize(self.editor.pingLatencyAreaWidth(), 0)
    
    def paintEvent(self, event):
        self.editor.pingLatencyAreaPaintEvent(event)


class LineNumberEditor(QPlainTextEdit):
    """
    Текстовый редактор с нумерацией строк и столбцом пинга.
    Используется для редактирования списка RPC.
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.lineNumberArea = LineNumberArea(self)
        self.pingLatencyArea = PingLatencyArea(self)
        
        self._line_statuses = {}  # {line_number: status_str}
        self._line_latencies = {}  # {line_number: latency_ms}
        
        self.blockCountChanged.connect(self.updateLineNumberAreaWidth)
        self.updateRequest.connect(self.updateLineNumberArea)
        self.cursorPositionChanged.connect(self.highlightCurrentLine)
        self.textChanged.connect(self.clear_statuses)  # Сброс статусов при редактировании
        
        self.updateLineNumberAreaWidth(0)
        self.highlightCurrentLine()
        
        # Применяем стиль Royal Input
        self.setStyleSheet(config.get_royal_input_style())
    
    def set_line_status(self, line_idx: int, status: str):
        """Установка статуса для конкретной строки (0-based index)."""
        self._line_statuses[line_idx] = status
        self.lineNumberArea.update()
    
    def set_line_latency(self, line_idx: int, latency: int):
        """Установка пинга для конкретной строки."""
        self._line_latencies[line_idx] = latency
        self.pingLatencyArea.update()
    
    def clear_statuses(self):
        """Очистка всех статусов и пингов."""
        if self._line_statuses or self._line_latencies:
            self._line_statuses.clear()
            self._line_latencies.clear()
            self.lineNumberArea.update()
            self.pingLatencyArea.update()
    
    def lineNumberAreaWidth(self):
        digits = 1
        max_val = max(1, self.blockCount())
        while max_val >= 10:
            max_val //= 10
            digits += 1
        
        # Ширина: иконка (20) + отступ (10) + ширина цифр
        space = 20 + 10 + self.fontMetrics().horizontalAdvance('9') * digits
        return space
    
    def pingLatencyAreaWidth(self):
        """Фиксированная ширина для столбца пинга."""
        return 70
    
    def updateLineNumberAreaWidth(self, _):
        # Устанавливаем отступы: Слева для номеров, Справа для пинга
        self.setViewportMargins(self.lineNumberAreaWidth(), 0, self.pingLatencyAreaWidth(), 0)
    
    def updateLineNumberArea(self, rect, dy):
        if dy:
            self.lineNumberArea.scroll(0, dy)
            self.pingLatencyArea.scroll(0, dy)
        else:
            self.lineNumberArea.update(0, rect.y(), self.lineNumberArea.width(), rect.height())
            self.pingLatencyArea.update(0, rect.y(), self.pingLatencyArea.width(), rect.height())
        
        if rect.contains(self.viewport().rect()):
            self.updateLineNumberAreaWidth(0)
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        
        # Позиционирование левой области
        self.lineNumberArea.setGeometry(QRect(cr.left(), cr.top(), self.lineNumberAreaWidth(), cr.height()))
        
        # Позиционирование правой области
        rw = self.pingLatencyAreaWidth()
        self.pingLatencyArea.setGeometry(QRect(cr.right() - rw + 1, cr.top(), rw, cr.height()))
    
    def highlightCurrentLine(self):
        extraSelections = []
        if not self.isReadOnly():
            selection = QTextEdit.ExtraSelection()
            lineColor = QColor(config.get_active_accent_color())
            lineColor.setAlpha(20)
            selection.format.setBackground(lineColor)
            selection.format.setProperty(
                QTextFormat.FullWidthSelection, True
            )
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            extraSelections.append(selection)
        self.setExtraSelections(extraSelections)
    
    def lineNumberAreaPaintEvent(self, event):
        painter = QPainter(self.lineNumberArea)
        painter.fillRect(event.rect(), QColor(config.COLOR_ROYAL_INPUT_BG))
        
        block = self.firstVisibleBlock()
        blockNumber = block.blockNumber()
        top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())
        
        height = self.fontMetrics().height()
        
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                # 1. Draw Status Icon
                status = self._line_statuses.get(blockNumber)
                if status:
                    icon = config.get_status_icon(status)
                    icon_y = top + (height - 14) // 2
                    icon.paint(painter, 4, icon_y, 14, 14)
                
                # 2. Draw Line Number
                number = str(blockNumber + 1)
                painter.setPen(QColor(config.COLOR_TEXT_GRAY))
                painter.setFont(self.font())
                painter.drawText(0, top, self.lineNumberArea.width() - 5, height, Qt.AlignRight, number)
            
            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            blockNumber += 1
    
    def pingLatencyAreaPaintEvent(self, event):
        painter = QPainter(self.pingLatencyArea)
        # Фон такой же как у редактора, чтобы сливалось
        painter.fillRect(event.rect(), QColor(config.COLOR_ROYAL_INPUT_BG))
        
        block = self.firstVisibleBlock()
        blockNumber = block.blockNumber()
        top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())
        
        height = self.fontMetrics().height()
        
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                latency = self._line_latencies.get(blockNumber)
                if latency is not None:
                    # Color Logic
                    if latency < 250:
                        col = QColor(config.COLOR_NEON_GREEN)
                    elif latency < 600:
                        col = QColor(config.COLOR_NEON_ORANGE)
                    else:
                        col = QColor(config.COLOR_NEON_RED)
                    
                    text = f"{latency} ms"
                    painter.setPen(col)
                    painter.setFont(self.font())
                    # Рисуем с отступом справа
                    painter.drawText(0, top, self.pingLatencyArea.width() - 10, height, Qt.AlignRight, text)
            
            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            blockNumber += 1


# -------------------------------------------------------------------------
# 2. WIZARD COMPONENTS (_OnboardingCard & ApiKeySetupDialog)
# -------------------------------------------------------------------------

class _OnboardingCard(QFrame):
    """
    Интерактивная карточка для выбора режима (RPC/API).
    Поддерживает состояния Active/Inactive, Hover и Neon Glow.
    """
    clicked = Signal(str)  # Emits 'api' or 'rpc'
    
    def __init__(self, mode: str, icon: str, title: str, text_intro: str, text_details: str, parent=None):
        super().__init__(parent)
        self._mode = mode
        self._is_active = False
        self._is_hovered = False
        
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        # Учитываем ширину свечения в отступах, чтобы контент не прилипал к краям
        gw = config.CARD_GLOW_WIDTH
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15 + gw, 20 + gw, 15 + gw, 20 + gw)
        layout.setSpacing(10)
        
        # --- Header (Horizontal: Icon + Title) ---
        header_layout = QHBoxLayout()
        header_layout.setSpacing(10)
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        # Icon (Reduced size)
        lbl_icon = QLabel(icon)
        lbl_icon.setAlignment(Qt.AlignCenter)
        lbl_icon.setStyleSheet("font-size: 28px; background: transparent;")
        lbl_icon.setFixedWidth(40)
        
        # Title (Left aligned)
        lbl_title = QLabel(title)
        lbl_title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        lbl_title.setWordWrap(True)
        lbl_title.setStyleSheet(f"color: {config.COLOR_TEXT_WHITE}; font-size: 11pt; font-weight: bold; background: transparent;")
        
        header_layout.addWidget(lbl_icon)
        header_layout.addWidget(lbl_title)
        layout.addLayout(header_layout)
        
        # Divider
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet(f"background: {config.COLOR_BORDER_LIGHT}; max-height: 1px;")
        layout.addWidget(line)
        
        # --- Intro Text (Fixed, Non-scrollable) ---
        lbl_intro = QLabel(text_intro)
        lbl_intro.setWordWrap(True)
        lbl_intro.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        lbl_intro.setStyleSheet(f"color: #CCCCCC; font-size: 9pt; line-height: 130%; background: transparent;")
        layout.addWidget(lbl_intro)
        
        # --- Scrollable Body (Details) ---
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        # Transparent background + Royal Scrollbar
        scroll_area.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QWidget {{ background: transparent; }}
            {config.get_royal_scrollbar_style()}
        """)
        
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 5, 0)  # Right margin for scrollbar
        scroll_layout.setSpacing(0)
        
        # Text Details
        lbl_details = QLabel(text_details)
        lbl_details.setWordWrap(True)
        lbl_details.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        lbl_details.setStyleSheet(f"color: #CCCCCC; font-size: 9pt; line-height: 130%; background: transparent;")
        
        scroll_layout.addWidget(lbl_details)
        scroll_layout.addStretch()  # Push text to top
        
        scroll_area.setWidget(scroll_content)
        layout.addWidget(scroll_area)
    
    def set_active(self, active: bool):
        self._is_active = active
        self.update()
    
    def enterEvent(self, event):
        self._is_hovered = True
        self.update()
        super().enterEvent(event)
    
    def leaveEvent(self, event):
        self._is_hovered = False
        self.update()
        super().leaveEvent(event)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self._mode)
        super().mousePressEvent(event)
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Основные параметры
        glow_width = config.CARD_GLOW_WIDTH
        
        # Уменьшаем визуальный прямоугольник, чтобы оставить место для свечения внутри виджета
        rect = self.rect().adjusted(glow_width, glow_width, -glow_width, -glow_width)
        
        # Определение цветов
        if self._mode == 'api':
            base_col = QColor(config.COLOR_CARD_BORDER_API)
            bg_col = QColor(config.COLOR_CARD_BG_API)
            glow_col = QColor(config.COLOR_CARD_GLOW_API)
        else:
            base_col = QColor(config.COLOR_CARD_BORDER_RPC)
            bg_col = QColor(config.COLOR_CARD_BG_RPC)
            glow_col = QColor(config.COLOR_CARD_GLOW_RPC)
        
        # Логика состояний
        draw_glow = False
        max_alpha = config.CARD_GLOW_ALPHA_MAX
        
        if self._is_active:
            border_col = base_col
            border_width = 2
            draw_glow = True
        else:
            border_col = QColor(config.COLOR_CARD_BORDER_DEFAULT)
            bg_col = QColor(config.COLOR_CARD_BG_DEFAULT)
            border_width = 1
            
            if self._is_hovered:
                # При наведении на неактивную карточку - легкая подсветка
                bg_col = QColor(255, 255, 255, 15)
                border_col = QColor(150, 150, 150)
                draw_glow = True
                max_alpha = int(max_alpha / 2)  # Свечение слабее
        
        # 1. Отрисовка свечения (Multi-pass with Quadratic Falloff)
        if draw_glow:
            painter.save()
            glow_c = QColor(glow_col)
            
            # Рисуем несколько полупрозрачных контуров, расширяясь наружу
            for i in range(1, glow_width + 1):
                progress = i / glow_width
                # Квадратичное затухание для мягкости (Soft Glow)
                alpha = int(max_alpha * ((1.0 - progress) ** 2))
                
                glow_c.setAlpha(alpha)
                painter.setPen(QPen(glow_c, 1))
                painter.setBrush(Qt.NoBrush)
                
                # Расширяем прямоугольник на i пикселей во все стороны
                g_rect = rect.adjusted(-i, -i, i, i)
                painter.drawRoundedRect(g_rect, 10, 10)
            
            painter.restore()
        
        # 2. Фон
        path = QPainterPath()
        path.addRoundedRect(rect, 10, 10)
        painter.fillPath(path, bg_col)
        
        # 3. Граница
        pen = QPen(border_col)
        pen.setWidth(border_width)
        painter.setPen(pen)
        painter.drawPath(path)


class ApiKeySetupDialog(RoyalDialog):
    """
    Единый центр настроек (Wizard + Settings).
    Позволяет пользователю выбрать между режимом RPC и API.
    """
    
    def __init__(self, parent=None, start_mode='api', current_key='', current_rpc_list=None):
        super().__init__(parent, title=TextStore.Wizard.TITLE_WINDOW)
        self.resize(720, 620)
        self._selected_mode = TextStore.Wizard.CARD_API_MODE  # Default
        self._is_error_state = False
        self._initial_key_exists = bool(current_key)  # Запоминаем, был ли ключ при открытии
        
        # Переменные для отслеживания прогресса
        self._discovery_total = 0
        self._discovery_current = 0
        
        # --- Header (Centered with Icon) ---
        header_container = QWidget()
        header_layout_h = QHBoxLayout(header_container)
        header_layout_h.setContentsMargins(0, 0, 0, 0)
        header_layout_h.setSpacing(15)
        
        # Icon
        lbl_icon = QLabel(TextStore.Wizard.ICON_HEADER)
        lbl_icon.setAlignment(Qt.AlignCenter)
        lbl_icon.setStyleSheet("font-size: 48px; background: transparent;")
        
        # Text Column
        text_col_layout = QVBoxLayout()
        text_col_layout.setSpacing(2)
        
        lbl_main = QLabel(TextStore.Wizard.LBL_HEADER_MAIN)
        lbl_main.setStyleSheet("color: white; font-size: 16pt; font-weight: bold;")
        
        lbl_sub = QLabel(TextStore.Wizard.LBL_HEADER_SUB)
        lbl_sub.setStyleSheet("color: #AAAAAA; font-size: 10pt;")
        
        text_col_layout.addWidget(lbl_main)
        text_col_layout.addWidget(lbl_sub)
        
        # Assemble Header
        header_layout_h.addStretch()
        header_layout_h.addWidget(lbl_icon)
        header_layout_h.addLayout(text_col_layout)
        header_layout_h.addStretch()
        
        self.add_royal_widget(header_container)
        
        # --- Cards Area ---
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(15)  # Расстояние между карточками = отступу окна
        cards_layout.setContentsMargins(0, 5, 0, 10)
        
        # RPC Card Content
        self.card_rpc = _OnboardingCard(
            TextStore.Wizard.CARD_RPC_MODE,
            TextStore.Wizard.CARD_RPC_ICON,
            TextStore.Wizard.CARD_RPC_TITLE,
            TextStore.Wizard.CARD_RPC_TEXT_INTRO,
            TextStore.Wizard.CARD_RPC_TEXT_DETAILS
        )
        
        # API Card Content
        self.card_api = _OnboardingCard(
            TextStore.Wizard.CARD_API_MODE,
            TextStore.Wizard.CARD_API_ICON,
            TextStore.Wizard.CARD_API_TITLE,
            TextStore.Wizard.CARD_API_TEXT_INTRO,
            TextStore.Wizard.CARD_API_TEXT_DETAILS
        )
        
        # Connect signals
        self.card_rpc.clicked.connect(self._on_card_clicked)
        self.card_api.clicked.connect(self._on_card_clicked)
        
        # Добавляем карточки с stretch=1, чтобы они делили ширину поровну
        cards_layout.addWidget(self.card_rpc, 1)
        cards_layout.addWidget(self.card_api, 1)
        self.add_royal_layout(cards_layout)
        
        # --- Info Block "Which to choose?" ---
        lbl_help = QLabel(TextStore.Wizard.HTML_HELP_BLOCK)
        lbl_help.setWordWrap(True)
        lbl_help.setStyleSheet("background: transparent;")
        self.add_royal_widget(lbl_help)
        
        # --- Dynamic Bottom Area ---
        self.stack = QStackedWidget()
        self.stack.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.stack.setFixedHeight(220)  # Fixed height for symmetry
        
        # Page 1: RPC Action
        page_rpc = QWidget()
        layout_rpc = QVBoxLayout(page_rpc)
        layout_rpc.setContentsMargins(0, 0, 0, 0)
        layout_rpc.setSpacing(15)  # Increased spacing for symmetry
        
        # Top Spring
        layout_rpc.addStretch(1)
        
        lbl_rpc_warn = QLabel(TextStore.Wizard.LBL_RPC_WARN)
        lbl_rpc_warn.setAlignment(Qt.AlignCenter)
        lbl_rpc_warn.setWordWrap(True)
        lbl_rpc_warn.setStyleSheet(f"color: {config.COLOR_ROYAL_GOLD}; font-size: 9pt; margin-bottom: 5px;")
        layout_rpc.addWidget(lbl_rpc_warn)
        
        # --- NEW: Auto Find Button (Moved to bottom row) ---
        self.btn_auto_find = QPushButton(TextStore.Wizard.BTN_AUTO_FIND)
        self.btn_auto_find.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_auto_find.setMinimumHeight(40)  # Match height with other buttons
        # Removed fixed width to allow flexible layout in HBox
        self.btn_auto_find.setStyleSheet(config.get_royal_button_style("secondary", color_override=config.COLOR_ROYAL_GOLD))
        self.btn_auto_find.clicked.connect(self._on_auto_find_clicked)
        
        # --- RPC Editor with Line Numbers ---
        self.rpc_editor = LineNumberEditor()
        # Pre-fill RPC List
        if current_rpc_list:
            # Add empty line at the end
            text = "\n".join(current_rpc_list) + "\n"
            self.rpc_editor.setPlainText(text)
        else:
            # Если список по умолчанию пуст (для безопасности), оставляем поле пустым.
            # Автопоиск запустится ниже.
            if services.DEFAULT_RPC_LIST:
                text = "\n".join(services.DEFAULT_RPC_LIST) + "\n"
                self.rpc_editor.setPlainText(text)
            else:
                self.rpc_editor.setPlainText("")
        
        # Reduced height to balance layout
        self.rpc_editor.setFixedHeight(100)
        layout_rpc.addWidget(self.rpc_editor)
        
        # Bottom Spring (to center label in the empty space)
        layout_rpc.addStretch(1)
        
        self.btn_rpc = QPushButton(TextStore.Wizard.BTN_USE_RPC)
        self.btn_rpc.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_rpc.setMinimumHeight(40)
        self.btn_rpc.setStyleSheet(config.get_royal_button_style("secondary", color_override=config.COLOR_ROYAL_GOLD))
        # Changed connection to custom handler
        self.btn_rpc.clicked.connect(self._on_use_rpc_clicked)
        
        # --- Bottom Buttons Layout (Horizontal) ---
        btns_layout = QHBoxLayout()
        btns_layout.addWidget(self.btn_auto_find)
        btns_layout.addSpacing(10)
        btns_layout.addWidget(self.btn_rpc)
        
        layout_rpc.addLayout(btns_layout)
        
        # Page 2: API Action
        page_api = QWidget()
        layout_api = QVBoxLayout(page_api)
        layout_api.setContentsMargins(0, 0, 0, 0)
        layout_api.addStretch(1)
        
        # NEW: API Promo Label
        lbl_api_promo = QLabel(TextStore.Wizard.LBL_API_PROMO)
        lbl_api_promo.setAlignment(Qt.AlignCenter)
        lbl_api_promo.setWordWrap(True)
        lbl_api_promo.setStyleSheet(f"color: {config.COLOR_ROYAL_BLUE_NEON}; font-size: 9pt; margin-bottom: 5px;")
        layout_api.addWidget(lbl_api_promo)
        
        self.input_key = QLineEdit()
        self.input_key.setPlaceholderText(TextStore.Wizard.PLACEHOLDER_KEY)
        self.input_key.setEchoMode(QLineEdit.Password)
        self.input_key.setStyleSheet(config.get_royal_input_style())
        self.input_key.installEventFilter(self)
        
        # Pre-fill Key
        if current_key:
            self.input_key.setText(current_key)
        
        lbl_security = QLabel(TextStore.Wizard.LBL_SECURITY_NOTE)
        lbl_security.setWordWrap(True)
        lbl_security.setStyleSheet("color: #666666; font-size: 8pt; margin-top: 2px;")
        
        lbl_link = QLabel(TextStore.Wizard.HTML_LINK_GET_KEY)
        lbl_link.setAlignment(Qt.AlignCenter)
        lbl_link.setOpenExternalLinks(True)
        lbl_link.setStyleSheet("margin-top: 5px; margin-bottom: 5px;")
        
        self.btn_save = QPushButton(TextStore.Wizard.BTN_SAVE_AND_START)
        self.btn_save.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_save.setMinimumHeight(40)
        self.btn_save.setStyleSheet(config.get_royal_button_style("primary", color_override=config.COLOR_ROYAL_BLUE_NEON))
        self.btn_save.clicked.connect(self._on_save_api)
        
        layout_api.addWidget(self.input_key)
        layout_api.addWidget(lbl_security)
        layout_api.addWidget(lbl_link)
        layout_api.addStretch(1)  # Push buttons to bottom
        layout_api.addWidget(self.btn_save)
        
        self.stack.addWidget(page_rpc)  # Index 0
        self.stack.addWidget(page_api)  # Index 1
        
        self.add_royal_widget(self.stack)
        
        # Validator Setup
        self._validator = services.ApiKeyValidator(self)
        self._validator.validationSuccess.connect(self._on_validation_success)
        self._validator.validationError.connect(self._on_validation_error)
        
        # RPC Validator (Manual)
        self._rpc_validator = services.RpcBatchValidator(self)
        self._rpc_validator.itemStatusChanged.connect(self._on_rpc_item_status)
        self._rpc_validator.finished.connect(self._on_rpc_finished)
        
        # Discovery Services (Auto)
        self._chainlist_fetcher = services.ChainlistFetcher(self)
        self._chainlist_fetcher.finished.connect(self._on_chainlist_candidates)
        
        self._discovery_validator = services.RpcBatchValidator(self)
        self._discovery_validator.finished.connect(self._on_discovery_finished)
        self._discovery_validator.itemStatusChanged.connect(self._on_discovery_item_status)
        
        # Init State based on start_mode
        self._selected_mode = TextStore.Wizard.CARD_API_MODE if start_mode == 'api' else TextStore.Wizard.CARD_RPC_MODE
        self._update_ui_state()
        
        # Equalize heights and fix stack height after layout
        QTimer.singleShot(0, self._finalize_layout)
        
        # Auto-start discovery if list is empty or default
        is_default = (not current_rpc_list) or (current_rpc_list == services.DEFAULT_RPC_LIST)
        if is_default:
            QTimer.singleShot(500, self._on_auto_find_clicked)
    
    def eventFilter(self, source, event):
        if source == self.input_key and self._is_error_state:
            if event.type() in (QEvent.FocusIn, QEvent.MouseButtonPress):
                self._reset_input_state()
        return super().eventFilter(source, event)
    
    def _reset_input_state(self):
        """Сброс состояния ошибки при взаимодействии."""
        self.input_key.clear()
        self.input_key.setEchoMode(QLineEdit.Password)
        self.input_key.setStyleSheet(config.get_royal_input_style(error=False))
        self.input_key.setEnabled(True)
        self.btn_save.setEnabled(True)
        self.btn_save.setText(TextStore.Wizard.BTN_SAVE_AND_START)
        self._is_error_state = False
    
    def _finalize_layout(self):
        """Финальная настройка макета после отрисовки."""
        self._equalize_card_heights()
        
        # 1. Фиксируем ширину, чтобы adjustSize() работал только по вертикали
        current_width = self.width()
        self.setFixedWidth(current_width)
        
        # 2. Принудительный пересчет макета и размеров
        if self.layout():
            self.layout().activate()
        self.adjustSize()
        
        # 3. Принудительная перецентровка с учетом финальных размеров
        screen = QGuiApplication.primaryScreen()
        if screen:
            rect = QStyle.alignedRect(
                Qt.LeftToRight,
                Qt.AlignCenter,
                self.size(),
                screen.geometry()
            )
            self.move(rect.topLeft())
        
        # 4. Снимаем блокировку ширины (возвращаем стандартное поведение)
        self.setMinimumWidth(0)
        self.setMaximumWidth(16777215)  # QWIDGETSIZE_MAX
    
    def _equalize_card_heights(self):
        """Принудительно устанавливает одинаковую высоту для обеих карточек."""
        # Фиксированная высота для компактности, как просил пользователь
        target_h = 400
        self.card_rpc.setFixedHeight(target_h)
        self.card_api.setFixedHeight(target_h)
    
    def _on_card_clicked(self, mode: str):
        self._selected_mode = mode
        self._update_ui_state()
    
    def _update_ui_state(self):
        is_api = (self._selected_mode == TextStore.Wizard.CARD_API_MODE)
        
        # Update Cards Visuals
        self.card_api.set_active(is_api)
        self.card_rpc.set_active(not is_api)
        
        # Switch Bottom Stack
        self.stack.setCurrentIndex(1 if is_api else 0)
    
    # --- Auto Discovery Logic ---
    
    def _on_auto_find_clicked(self):
        """Запуск автоматического поиска узлов."""
        # Блокируем кнопки
        self.btn_auto_find.setEnabled(False)
        self.btn_rpc.setEnabled(False)
        
        # Меняем текст и стиль на "Серый/Нейтральный"
        self.btn_auto_find.setText(TextStore.Wizard.BTN_FINDING)
        
        disabled_style = """
            QPushButton {
                background: transparent;
                color: #666666;
                border: 1px solid #666666;
                border-radius: 6px;
                font-family: "Segoe UI";
                font-size: 10pt;
                font-weight: bold;
                padding: 6px 12px;
            }
        """
        self.btn_auto_find.setStyleSheet(disabled_style)
        self.btn_rpc.setStyleSheet(disabled_style)
        
        # Запускаем процесс
        self._chainlist_fetcher.start_fetch()
    
    def _on_chainlist_candidates(self, candidates: List[str]):
        if not candidates:
            # Если не удалось скачать, восстанавливаем состояние
            self._restore_rpc_buttons()
            return
        
        # Инициализация прогресса
        self._discovery_total = len(candidates)
        self._discovery_current = 0
        
        # Переводим кнопку в режим прогресс-бара
        self.btn_auto_find.setText(TextStore.Wizard.BTN_FIND_PROGRESS_FMT.format(0, self._discovery_total))
        self.btn_auto_find.setStyleSheet(config.get_progress_button_style(0))
        
        # Запускаем валидацию с сортировкой
        self._discovery_validator.validate_list(candidates, sort_by_latency=True)
    
    def _on_discovery_item_status(self, index: int, status: str):
        """Обновление кнопки-прогресса при проверке каждого узла."""
        # Игнорируем статус 'loading', чтобы прогресс не заполнялся мгновенно
        if status == 'loading':
            return
        
        # Увеличиваем прогресс только по завершению проверки (ok или error)
        self._discovery_current += 1
        
        # Вычисляем процент и обновляем кнопку
        if self._discovery_total > 0:
            percent = (self._discovery_current / self._discovery_total) * 100
            self.btn_auto_find.setText(TextStore.Wizard.BTN_FIND_PROGRESS_FMT.format(self._discovery_current, self._discovery_total))
            self.btn_auto_find.setStyleSheet(config.get_progress_button_style(percent))
    
    def _on_discovery_finished(self, success: bool, valid_urls: List[Tuple[str, int]]):
        if success and valid_urls:
            # Берем топ N. valid_urls теперь список кортежей (url, latency)
            top_nodes = valid_urls[:config.RPC_TOP_RESULTS]
            
            # Вставляем только URL в редактор
            urls = [item[0] for item in top_nodes]
            # Add empty line at the end
            text = "\n".join(urls) + "\n"
            self.rpc_editor.setPlainText(text)
            
            # Обновляем пинги в боковой панели
            self.rpc_editor.clear_statuses()
            for i, (_, latency) in enumerate(top_nodes):
                self.rpc_editor.set_line_latency(i, latency)
        
        # Восстанавливаем кнопки
        self._restore_rpc_buttons()
    
    def _restore_rpc_buttons(self):
        """Восстанавливает активное состояние кнопок RPC."""
        self.btn_auto_find.setEnabled(True)
        self.btn_rpc.setEnabled(True)
        
        self.btn_auto_find.setText(TextStore.Wizard.BTN_AUTO_FIND)
        
        # Восстанавливаем "Золотой" стиль
        gold_style = config.get_royal_button_style("secondary", color_override=config.COLOR_ROYAL_GOLD)
        self.btn_auto_find.setStyleSheet(gold_style)
        self.btn_rpc.setStyleSheet(gold_style)
    
    # --- Manual RPC Logic ---
    
    def _on_use_rpc_clicked(self):
        """Запуск валидации списка RPC с умным парсингом (Smart Extraction)."""
        text = self.rpc_editor.toPlainText()
        
        # 1. Smart Regex Extraction & Cleaning
        # Решает проблему склеенных строк (напр. ".../fasthttps://...")
        # Вставляем разделитель перед протоколами, если они в середине текста
        clean_text = re.sub(r'(?i)(?<!^)(https?://)', r'\n\1', text)
        
        # Разбиваем по пробельным символам и фильтруем мусор
        raw_tokens = clean_text.split()
        unique_lines = []
        seen = set()
        
        for token in raw_tokens:
            token = token.strip()
            # Базовая проверка структуры URL
            if re.match(r'^https?://[a-zA-Z0-9.-]+', token):
                if token not in seen:
                    unique_lines.append(token)
                    seen.add(token)
        
        # Если список пуст, просто закрываем (используем дефолтные настройки)
        if not unique_lines:
            self.accept()
            return
        
        # 2. Обновляем редактор (визуальная санитизация для пользователя)
        # Пользователь увидит, что его "каша" превратилась в аккуратный список
        formatted_text = "\n".join(unique_lines)
        if text != formatted_text:
            self.rpc_editor.setPlainText(formatted_text)
        
        # 3. Блокируем UI
        self.rpc_editor.setReadOnly(True)
        self.rpc_editor.clear_statuses()
        self.btn_rpc.setEnabled(False)
        self.btn_rpc.setText(TextStore.Wizard.BTN_CHECKING)
        
        # 4. Запуск валидации
        self._rpc_validator.validate_list(unique_lines)
    
    def _on_rpc_item_status(self, index: int, status: str):
        self.rpc_editor.set_line_status(index, status)
    
    def _on_rpc_finished(self, success: bool, valid_urls: List[Tuple[str, int]]):
        if success:
            # Сохраняем валидные URL (только строки, без пинга)
            urls_to_save = [item[0] for item in valid_urls]
            s = QSettings()
            s.setValue("core/rpc_url", urls_to_save)
            s.sync()
            
            # Обновляем пинги в UI для красоты перед закрытием
            for i, (_, latency) in enumerate(valid_urls):
                self.rpc_editor.set_line_latency(i, latency)
            
            self.btn_rpc.setText(TextStore.Wizard.BTN_SUCCESS)
            self.btn_rpc.setStyleSheet("""
                QPushButton {
                    background: #00E050;
                    color: white;
                    border: none;
                    border-radius: 6px;
                    font-family: "Segoe UI";
                    font-size: 10pt;
                    font-weight: bold;
                    padding: 6px 12px;
                }
            """)
            QTimer.singleShot(800, self.accept)
        else:
            self.btn_rpc.setText(TextStore.Wizard.BTN_ERR_LIST)
            self.btn_rpc.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    color: #FF453A;
                    border: 1px solid #FF453A;
                    border-radius: 6px;
                    font-family: "Segoe UI";
                    font-size: 10pt;
                    font-weight: bold;
                    padding: 6px 12px;
                }
                QPushButton:hover { background: rgba(255, 69, 58, 0.1); }
            """)
            self.btn_rpc.setEnabled(True)
            self.rpc_editor.setReadOnly(False)
    
    def _on_save_api(self):
        text = self.input_key.text().strip()
        
        # Сценарий 1: Ключ введен -> Валидация
        if text:
            self._start_validation(text)
            return
        
        # Сценарий 2: Поле пустое, но ключ был сохранен ранее -> Предложить удаление
        if self._initial_key_exists:
            self._show_deletion_warning()
            return
        
        # Сценарий 3: Поле пустое и ключа не было -> Ошибка
        RoyalDialog.show_royal_alert(
            self, TextStore.Common.TITLE_ERROR,
            TextStore.Wizard.ALERT_EMPTY_KEY_MSG,
            TextStore.Common.ICON_WARNING
        )
    
    def _show_deletion_warning(self):
        """Показывает диалог подтверждения удаления ключа и перехода на RPC."""
        dlg = RoyalDialog(self, TextStore.Wizard.DIALOG_SWITCH_TITLE)
        dlg.resize(400, 220)
        
        layout = QVBoxLayout()
        layout.setSpacing(15)
        
        h_layout = QHBoxLayout()
        h_layout.setSpacing(15)
        
        lbl_icon = QLabel(TextStore.Common.ICON_WARNING)
        lbl_icon.setStyleSheet("font-size: 32px; background: transparent;")
        lbl_icon.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        
        # Текст предупреждения
        lbl_text = QLabel(TextStore.Wizard.DIALOG_SWITCH_MSG)
        lbl_text.setWordWrap(True)
        lbl_text.setStyleSheet(f"color: {config.COLOR_TEXT_WHITE}; font-size: 10pt; background: transparent;")
        
        h_layout.addWidget(lbl_icon)
        h_layout.addWidget(lbl_text, 1)
        layout.addLayout(h_layout)
        
        # Кнопки
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        btn_cancel = QPushButton(TextStore.Common.BTN_CANCEL)
        btn_cancel.setCursor(QCursor(Qt.PointingHandCursor))
        btn_cancel.setStyleSheet(config.get_royal_button_style("secondary"))
        btn_cancel.clicked.connect(dlg.reject)
        
        btn_confirm = QPushButton(TextStore.Wizard.BTN_CONFIRM_SWITCH)
        btn_confirm.setCursor(QCursor(Qt.PointingHandCursor))
        # Используем стиль Warning (или Primary с оранжевым оттенком, если есть, но Primary подойдет)
        btn_confirm.setStyleSheet(config.get_royal_button_style("primary"))
        btn_confirm.clicked.connect(dlg.accept)
        
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_confirm)
        
        layout.addLayout(btn_layout)
        dlg.add_royal_layout(layout)
        
        if dlg.exec() == QDialog.Accepted:
            # Пользователь подтвердил удаление
            self._selected_mode = TextStore.Wizard.CARD_RPC_MODE
            self.input_key.setText("")  # Гарантируем пустоту
            self.accept()
    
    def _start_validation(self, key: str):
        """Блокирует UI и запускает проверку ключа."""
        # Защита от дребезга (если кнопка уже заблокирована, не запускаем повторно)
        if not self.btn_save.isEnabled():
            return
        
        self.input_key.setEnabled(False)
        self.btn_save.setEnabled(False)
        self.btn_save.setText(TextStore.Wizard.BTN_CHECKING)
        self._validator.validate_key(key)
    
    def _on_validation_success(self):
        """Обработка успешной валидации."""
        self.btn_save.setText(TextStore.Wizard.BTN_SUCCESS)
        # Зеленый стиль для успеха
        self.btn_save.setStyleSheet("""
            QPushButton {
                background: #00E050;
                color: white;
                border: none;
                border-radius: 6px;
                font-family: "Segoe UI";
                font-size: 10pt;
                font-weight: bold;
                padding: 6px 12px;
            }
        """)
        QTimer.singleShot(800, self.accept)
    
    def _on_validation_error(self, error_type: str):
        """Обработка ошибки валидации."""
        # Если кнопка активна, значит пользователь уже сбросил состояние или отменил
        if self.btn_save.isEnabled():
            return
        
        self.input_key.setEnabled(True)
        self.btn_save.setEnabled(True)
        self.btn_save.setText(TextStore.Wizard.BTN_SAVE_AND_START)
        self.btn_save.setStyleSheet(config.get_royal_button_style("primary", color_override=config.COLOR_ROYAL_BLUE_NEON))
        
        msg = TextStore.Errors.ERR_NETWORK if error_type == "network" else TextStore.Errors.ERR_INVALID_KEY
        
        # Переход в режим ошибки (In-place Error Feedback)
        self._is_error_state = True
        self.input_key.setEchoMode(QLineEdit.Normal)
        self.input_key.setText(msg)
        self.input_key.setStyleSheet(config.get_royal_input_style(error=True))
        self.input_key.clearFocus()  # Снимаем фокус, чтобы состояние ошибки зафиксировалось
    
    def get_key(self) -> str:
        # Возвращает текст ключа всегда, независимо от режима
        return self.input_key.text().strip()
    
    def get_selected_mode(self) -> str:
        # Возвращает 'api' или 'rpc' в зависимости от активной вкладки
        return 'api' if self._selected_mode == TextStore.Wizard.CARD_API_MODE else 'rpc'