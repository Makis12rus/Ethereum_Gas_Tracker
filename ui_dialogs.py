from __future__ import annotations

# -*- coding: utf-8 -*-

"""
Аннотация

🧩 1. Назначение файла
- Библиотека базовых и системных диалоговых окон.
- Содержит родительский класс RoyalDialog.
- Содержит общие диалоги: О программе, Обновление, Ввод чисел.

🧱 2. Компоненты
- RoyalDialog: Базовый класс (Frameless, Gradient, Shadow).
- RoyalNumInputDialog: Ввод чисел (интервал, порог).
- AboutDialog: Информационное окно.
- UpdateDialog: Окно проверки и установки обновлений.

⚙️ 3. Особенности
- Облегченная версия (логика настройки вынесена в ui_wizzard.py).
- Стилизация через config.py (Pixel-Perfect).
- Текстовый контент загружается из core.TextStore (SSOT).
"""

from typing import Optional, Union

from PySide6.QtCore import (
    Qt, QPoint, QSize, QTimer, QRect, QEvent, QRegularExpression
)
from PySide6.QtGui import (
    QPainter, QPainterPath, QBrush, QPen, QLinearGradient,
    QCursor, QMouseEvent, QColor, QIntValidator, QRegularExpressionValidator,
    QGuiApplication, QFontMetrics
)
from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QPlainTextEdit, QGraphicsDropShadowEffect,
    QSizePolicy, QLayout, QScrollArea, QFrame, QProgressBar, QStyle
)

import config
import services  # Для UpdateManager
import win_logic  # Для установки обновлений и открытия проводника
from core import TextStore  # Источник текстов


# -------------------------------------------------------------------------
# 1. BASE CLASS (RoyalDialog)
# -------------------------------------------------------------------------

class RoyalDialog(QDialog):
    """
    Универсальный базовый класс для всех диалоговых окон.
    - Безрамочный (Frameless).
    - Градиентный фон (Obsidian).
    - Встроенный заголовок и кнопка закрытия.
    - Поддержка перетаскивания за любую часть фона.
    - Автоматическое центрирование на экране.
    """
    
    def __init__(self, parent: Optional[QWidget] = None, title: str = ""):
        super().__init__(parent)
        
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # Тень
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(20)
        self._shadow.setXOffset(0)
        self._shadow.setYOffset(4)
        self._shadow.setColor(QColor(0, 0, 0, 160))
        self.setGraphicsEffect(self._shadow)
        
        self._drag_pos: Optional[QPoint] = None
        self._has_centered = False  # Флаг для однократного центрирования
        
        # Paint Cache
        self._cached_bg_brush: Optional[QBrush] = None
        self._cached_border_pen: Optional[QPen] = None
        
        self._setup_royal_ui(title)
    
    def _setup_royal_ui(self, title: str):
        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(15, 15, 15, 15)
        self._main_layout.setSpacing(10)
        
        # Header
        self._header_layout = QHBoxLayout()
        self._header_layout.setContentsMargins(5, 0, 5, 0)
        
        self._lbl_title = QLabel(title)
        self._lbl_title.setStyleSheet("color: #AAAAAA; font-weight: bold; font-size: 10pt;")
        self._lbl_title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        
        self._btn_close = QPushButton(TextStore.Common.BTN_CLOSE_X)
        self._btn_close.setFixedSize(30, 30)
        self._btn_close.setCursor(QCursor(Qt.PointingHandCursor))
        self._btn_close.setStyleSheet(config.get_royal_close_btn_style())
        self._btn_close.clicked.connect(self.reject)
        
        self._header_layout.addWidget(self._lbl_title)
        self._header_layout.addWidget(self._btn_close)
        
        self._main_layout.addLayout(self._header_layout)
        
        # Content
        self._content_layout = QVBoxLayout()
        self._content_layout.setContentsMargins(20, 10, 20, 20)
        self._content_layout.setSpacing(10)
        
        self._main_layout.addLayout(self._content_layout)
    
    def set_royal_title(self, text: str):
        self._lbl_title.setText(text)
    
    def add_royal_widget(self, widget: QWidget):
        self._content_layout.addWidget(widget)
    
    def add_royal_layout(self, layout: QLayout):
        self._content_layout.addLayout(layout)
    
    def showEvent(self, event):
        """
        Перехват события отображения для центрирования.
        Использует QStyle.alignedRect для точного позиционирования
        по центру основного экрана с учетом DPI.
        """
        if not self._has_centered:
            screen = QGuiApplication.primaryScreen()
            if screen:
                # Получаем геометрию основного экрана
                screen_geo = screen.geometry()
                
                # Вычисляем идеальный прямоугольник по центру экрана
                # Qt.LeftToRight - стандартное направление
                # Qt.AlignCenter - выравнивание по центру
                # self.size() - текущий размер окна
                centered_rect = QStyle.alignedRect(
                    Qt.LeftToRight,
                    Qt.AlignCenter,
                    self.size(),
                    screen_geo
                )
                
                # Перемещаем окно в вычисленную точку
                self.move(centered_rect.topLeft())
            
            self._has_centered = True
        
        super().showEvent(event)
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        rect = self.rect().adjusted(10, 10, -10, -10)
        
        path = QPainterPath()
        path.addRoundedRect(rect, 12, 12)
        
        painter.save()
        painter.setClipPath(path)
        
        # Background Gradient (Cached)
        if not self._cached_bg_brush:
            gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
            gradient.setColorAt(0.0, QColor(config.COLOR_ROYAL_BG_START))
            gradient.setColorAt(1.0, QColor(config.COLOR_ROYAL_BG_END))
            self._cached_bg_brush = QBrush(gradient)
        
        painter.setPen(Qt.NoPen)
        painter.setBrush(self._cached_bg_brush)
        painter.drawRect(rect)
        
        # Neon Glow Top Bar (Dynamic Color)
        accent_color = config.get_active_accent_color()
        
        glow_height = 20
        glow_grad = QLinearGradient(rect.x(), rect.y(), rect.x(), rect.y() + glow_height)
        c_glow_start = QColor(accent_color)
        c_glow_start.setAlpha(100)
        glow_grad.setColorAt(0.0, c_glow_start)
        glow_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        
        painter.setBrush(QBrush(glow_grad))
        painter.drawRect(rect.x(), rect.y(), rect.width(), glow_height)
        
        painter.setBrush(QColor(accent_color))
        # Используем единую константу ширины из конфига
        painter.drawRect(rect.x(), rect.y(), rect.width(), config.NEON_BORDER_WIDTH)
        
        painter.restore()
        
        # Border (Cached)
        if not self._cached_border_pen:
            pen = QPen(QColor(config.COLOR_BORDER_LIGHT))
            pen.setWidth(1)
            self._cached_border_pen = pen
        
        painter.setPen(self._cached_border_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(rect, 12, 12)
    
    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
    
    def mouseMoveEvent(self, event: QMouseEvent):
        if event.buttons() & Qt.LeftButton and self._drag_pos:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
    
    @staticmethod
    def show_royal_alert(parent: Optional[QWidget], title: str, text: str, icon_emoji: str = TextStore.Common.ICON_INFO):
        """Статический метод для быстрого показа уведомления."""
        dlg = RoyalDialog(parent, title)
        dlg.resize(400, 200)
        
        layout = QVBoxLayout()
        layout.setSpacing(15)
        
        h_layout = QHBoxLayout()
        h_layout.setSpacing(15)
        
        lbl_icon = QLabel(icon_emoji)
        lbl_icon.setStyleSheet("font-size: 32px; background: transparent;")
        lbl_icon.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        
        lbl_text = QLabel(text)
        lbl_text.setWordWrap(True)
        lbl_text.setStyleSheet(f"color: {config.COLOR_TEXT_WHITE}; font-size: 10pt; background: transparent;")
        
        h_layout.addWidget(lbl_icon)
        h_layout.addWidget(lbl_text, 1)
        layout.addLayout(h_layout)
        
        btn_ok = QPushButton(TextStore.Common.BTN_OK)
        btn_ok.setCursor(QCursor(Qt.PointingHandCursor))
        btn_ok.setStyleSheet(config.get_royal_button_style("primary"))
        btn_ok.clicked.connect(dlg.accept)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(btn_ok)
        btn_layout.addStretch()
        
        layout.addLayout(btn_layout)
        dlg.add_royal_layout(layout)
        dlg.exec()


# -------------------------------------------------------------------------
# 2. SYSTEM DIALOGS (Input, About, Update)
# -------------------------------------------------------------------------

class RoyalNumInputDialog(RoyalDialog):
    """Диалог ввода числа (int/float) с валидацией."""
    
    def __init__(self, parent, title: str, label: str,
                 value: Union[int, float], min_val: Union[int, float],
                 max_val: Union[int, float], decimals: int = 0):
        super().__init__(parent, title=title)
        self.resize(350, 200)
        self._value = value
        self._type = float if decimals > 0 else int
        
        lbl = QLabel(label)
        lbl.setStyleSheet("color: #CCCCCC; font-size: 10pt;")
        self.add_royal_widget(lbl)
        
        self.input_edit = QLineEdit()
        self.input_edit.setText(str(value))
        self.input_edit.setStyleSheet(config.get_royal_input_style())
        self.input_edit.installEventFilter(self)
        
        if decimals > 0:
            pattern = f"^-?[0-9]*[.,]?[0-9]{{0,{decimals}}}$"
            regex = QRegularExpression(pattern)
            val = QRegularExpressionValidator(regex, self)
            self.input_edit.setValidator(val)
        else:
            self.input_edit.setValidator(QIntValidator(int(min_val), int(max_val), self))
        
        self.add_royal_widget(self.input_edit)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        btn_cancel = QPushButton(TextStore.Common.BTN_CANCEL)
        btn_cancel.clicked.connect(self.reject)
        btn_cancel.setStyleSheet(config.get_royal_button_style("secondary"))
        
        btn_ok = QPushButton(TextStore.Common.BTN_OK)
        btn_ok.clicked.connect(self.accept)
        btn_ok.setStyleSheet(config.get_royal_button_style("primary"))
        
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_ok)
        self.add_royal_layout(btn_layout)
    
    def eventFilter(self, source, event):
        if source == self.input_edit and event.type() == QEvent.KeyPress:
            if event.text() == ',':
                self.input_edit.insert('.')
                return True
        return super().eventFilter(source, event)
    
    def get_value(self):
        try:
            txt = self.input_edit.text().replace(',', '.')
            if not txt: return self._value
            return self._type(txt)
        except ValueError:
            return self._value


class AboutDialog(RoyalDialog):
    """Окно 'О программе' с прокруткой и ссылками."""
    
    def __init__(self, parent=None):
        super().__init__(parent, title=TextStore.About.TITLE_WINDOW)
        
        # Получаем primaryScreen для расчета высоты
        screen = QGuiApplication.primaryScreen()
        w, h = 500, 600
        if screen:
            geo = screen.availableGeometry()
            h = min(600, int(geo.height() * 0.8))
        self.resize(w, h)
        
        c_gray = config.COLOR_TEXT_GRAY
        
        # Генерация HTML контента через SSOT (TextStore)
        scroll_txt = TextStore.About.HTML_BODY_TEMPLATE.format(
            color_text=config.COLOR_TEXT_WHITE,
            font_size_body=config.ABOUT_BODY_PT,
            font_size_title=config.ABOUT_TITLE_PT,
            app_caption=config.get_about_caption()
        )
        
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.NoFrame)
        scroll_area.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QWidget {{ background: transparent; }}
            {config.get_royal_scrollbar_style()}
        """)
        
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setContentsMargins(0, 0, 10, 0)
        
        lbl_scroll = QLabel(scroll_txt)
        lbl_scroll.setWordWrap(True)
        lbl_scroll.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse)
        lbl_scroll.setOpenExternalLinks(True)
        
        scroll_layout.addWidget(lbl_scroll)
        scroll_area.setWidget(scroll_widget)
        self.add_royal_widget(scroll_area)
        
        footer_layout = QVBoxLayout()
        footer_layout.setSpacing(2)
        
        lbl_bottom = QLabel(TextStore.About.LBL_FOOTER_LOVE)
        lbl_bottom.setStyleSheet(f"color: {c_gray}; font-size: {config.ABOUT_FOOTER_PT}pt;")
        lbl_bottom.setAlignment(Qt.AlignCenter)
        footer_layout.addWidget(lbl_bottom)
        
        if config.DONATE_URL:
            # Формируем ссылку Donate
            donate_html = TextStore.About.HTML_LINK_DONATE_TEMPLATE.format(url=config.DONATE_URL)
            lbl_donate = QLabel(donate_html)
            lbl_donate.setAlignment(Qt.AlignCenter)
            lbl_donate.setOpenExternalLinks(True)
            lbl_donate.setStyleSheet(f"font-size: {config.ABOUT_FOOTER_PT}pt;")
            footer_layout.addWidget(lbl_donate)
        
        self.add_royal_layout(footer_layout)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_ok = QPushButton(TextStore.Common.BTN_OK)
        btn_ok.setCursor(QCursor(Qt.PointingHandCursor))
        btn_ok.setStyleSheet(config.get_royal_button_style("primary"))
        btn_ok.clicked.connect(self.accept)
        btn_layout.addWidget(btn_ok)
        btn_layout.addStretch()
        self.add_royal_layout(btn_layout)


class UpdateDialog(RoyalDialog):
    """
    Окно проверки и установки обновлений.
    Показывает Release Notes, прогресс загрузки и системные логи.
    """
    
    def __init__(self, parent=None, auto_start=True):
        super().__init__(parent, TextStore.Updates.TITLE_WINDOW)
        self.resize(550, 600)  # Increased height for logs
        
        self._download_url = ""
        self._version_str = ""  # Хранение версии для передачи в загрузчик
        self._pending_update_path = ""  # Путь к скачанному файлу
        
        # --- Header ---
        header_layout = QHBoxLayout()
        header_layout.setSpacing(15)
        
        self._lbl_icon = QLabel(TextStore.Updates.ICON_UPDATE)
        self._lbl_icon.setStyleSheet("font-size: 40px; background: transparent;")
        self._lbl_icon.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        
        text_layout = QVBoxLayout()
        text_layout.setSpacing(4)
        
        self._lbl_status_title = QLabel(TextStore.Updates.STATUS_CHECKING)
        self._lbl_status_title.setStyleSheet("color: white; font-size: 14pt; font-weight: bold;")
        
        # FIX: Calculate and set fixed height to prevent jumping
        fm = QFontMetrics(self._lbl_status_title.font())
        # Height for 1 line + some padding (e.g. 1.5x line height)
        fixed_h = int(fm.height() * 1.5)
        self._lbl_status_title.setMinimumHeight(fixed_h)
        
        self._lbl_status_sub = QLabel("...")
        self._lbl_status_sub.setWordWrap(True)
        self._lbl_status_sub.setStyleSheet("color: #AAAAAA; font-size: 10pt;")
        # FIX: Set fixed width to prevent text wrapping jitter
        self._lbl_status_sub.setFixedWidth(400)
        
        text_layout.addWidget(self._lbl_status_title)
        text_layout.addWidget(self._lbl_status_sub)
        
        header_layout.addWidget(self._lbl_icon)
        header_layout.addLayout(text_layout)
        header_layout.addStretch()
        
        self.add_royal_layout(header_layout)
        
        # --- Release Notes Area ---
        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setFrameShape(QFrame.NoFrame)
        self._scroll_area.setStyleSheet(f"""
            QScrollArea {{ background: rgba(255, 255, 255, 0.05); border-radius: 6px; }}
            QWidget {{ background: transparent; }}
            {config.get_royal_scrollbar_style()}
        """)
        
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(10, 10, 10, 10)
        
        self._lbl_notes = QLabel()
        self._lbl_notes.setWordWrap(True)
        self._lbl_notes.setTextFormat(Qt.MarkdownText)
        self._lbl_notes.setStyleSheet("color: #DDDDDD; font-size: 10pt;")
        self._lbl_notes.setOpenExternalLinks(True)
        
        scroll_layout.addWidget(self._lbl_notes)
        scroll_layout.addStretch()
        
        self._scroll_area.setWidget(scroll_content)
        self._scroll_area.hide()  # Скрыто до нахождения обновления
        self.add_royal_widget(self._scroll_area)
        
        # --- Target Path Display & Open Button ---
        self._lbl_path_title = QLabel(TextStore.Updates.LBL_TARGET_PATH)
        self._lbl_path_title.setStyleSheet("color: #888888; font-size: 9pt; margin-top: 5px;")
        self._lbl_path_title.hide()
        self.add_royal_widget(self._lbl_path_title)
        
        # Container for Path + Button
        self._path_container = QWidget()
        path_layout = QHBoxLayout(self._path_container)
        path_layout.setContentsMargins(0, 0, 0, 0)
        path_layout.setSpacing(5)
        
        self._path_display = QLineEdit()
        self._path_display.setReadOnly(True)
        self._path_display.setStyleSheet(config.get_royal_input_style())
        
        self._btn_open_folder = QPushButton("📂")
        self._btn_open_folder.setCursor(QCursor(Qt.PointingHandCursor))
        self._btn_open_folder.setFixedSize(40, 36)  # Match input height roughly
        self._btn_open_folder.setToolTip("Открыть папку с файлом")
        self._btn_open_folder.setStyleSheet(config.get_royal_button_style("secondary"))
        self._btn_open_folder.clicked.connect(self._on_open_folder_clicked)
        
        path_layout.addWidget(self._path_display)
        path_layout.addWidget(self._btn_open_folder)
        
        self._path_container.hide()
        self.add_royal_widget(self._path_container)
        
        # --- Progress Bar ---
        self._progress = QProgressBar()
        self._progress.setTextVisible(False)
        self._progress.setFixedHeight(6)
        self._progress.setStyleSheet(f"""
            QProgressBar {{
                background-color: #333333;
                border-radius: 3px;
                border: none;
            }}
            QProgressBar::chunk {{
                background-color: {config.COLOR_NEON_GREEN};
                border-radius: 3px;
            }}
        """)
        self._progress.hide()
        self.add_royal_widget(self._progress)
        
        # --- System Log Console ---
        self._lbl_log_title = QLabel(TextStore.Updates.LBL_SYSTEM_LOG)
        self._lbl_log_title.setStyleSheet("color: #888888; font-size: 9pt; margin-top: 5px;")
        self._lbl_log_title.hide()
        self.add_royal_widget(self._lbl_log_title)
        
        self._log_console = QPlainTextEdit()
        self._log_console.setReadOnly(True)
        self._log_console.setFixedHeight(100)
        self._log_console.setStyleSheet("""
            QPlainTextEdit {
                background-color: #101010;
                color: #00E050;
                font-family: "Consolas", monospace;
                font-size: 9pt;
                border: 1px solid #333333;
                border-radius: 6px;
                padding: 5px;
            }
        """)
        self._log_console.hide()
        self.add_royal_widget(self._log_console)
        
        # --- Buttons ---
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self._btn_action = QPushButton(TextStore.Updates.BTN_DOWNLOAD)
        self._btn_action.setCursor(QCursor(Qt.PointingHandCursor))
        self._btn_action.setStyleSheet(config.get_royal_button_style("primary"))
        self._btn_action.clicked.connect(self._on_action_clicked)
        self._btn_action.hide()
        
        self._btn_close = QPushButton(TextStore.Updates.BTN_CLOSE)
        self._btn_close.setCursor(QCursor(Qt.PointingHandCursor))
        self._btn_close.setStyleSheet(config.get_royal_button_style("secondary"))
        self._btn_close.clicked.connect(self.reject)
        
        btn_layout.addWidget(self._btn_close)
        btn_layout.addWidget(self._btn_action)
        self.add_royal_layout(btn_layout)
        
        # --- Logic ---
        self._manager = services.UpdateManager(self)
        self._manager.updateCheckFinished.connect(self._on_check_finished)
        self._manager.downloadProgress.connect(self._on_progress)
        self._manager.downloadFinished.connect(self._on_download_finished)
        self._manager.errorOccurred.connect(self._on_error)
        
        # New Signals
        self._manager.logMessage.connect(self._append_log)
        self._manager.targetPathChanged.connect(self._update_target_path)
        
        if auto_start:
            self._start_check()
    
    def _start_check(self):
        self._manager.check_for_updates()
    
    def _append_log(self, msg: str):
        self._log_console.appendPlainText(f"> {msg}")
        # Auto-scroll
        sb = self._log_console.verticalScrollBar()
        sb.setValue(sb.maximum())
    
    def _update_target_path(self, path: str):
        self._path_display.setText(path)
    
    def _on_open_folder_clicked(self):
        """Открывает проводник с выделением файла."""
        path = self._path_display.text()
        if path:
            win_logic.show_file_in_explorer(path)
    
    def _on_check_finished(self, has_update: bool, version: str, url: str, notes: str, date_str: str):
        # Общая логика: отображаем список изменений (если есть), даже если версия актуальна
        if notes:
            self._lbl_notes.setText(notes)
            self._scroll_area.show()
        
        # Формируем строку версии с датой
        ver_info = f"Version: {version}"
        if date_str:
            ver_info += f"  -  {date_str}"
        
        if has_update:
            self._download_url = url
            self._version_str = version  # Сохраняем версию для генерации имени файла
            self._lbl_icon.setText(TextStore.Updates.ICON_UPDATE)
            self._lbl_status_title.setText(TextStore.Updates.LBL_FOUND_TITLE)
            self._lbl_status_sub.setText(f"{TextStore.Updates.LBL_FOUND_SUB}\n{ver_info}")
            
            self._btn_action.show()
            self._btn_action.setFocus()
        else:
            self._lbl_icon.setText(TextStore.Updates.ICON_LATEST)
            self._lbl_status_title.setText(TextStore.Updates.LBL_LATEST_TITLE)
            self._lbl_status_sub.setText(f"{TextStore.Updates.LBL_LATEST_SUB}\n{ver_info}")
            self._btn_close.setText(TextStore.Common.BTN_OK)
            # Кнопка скачивания остается скрытой
    
    def _on_action_clicked(self):
        # Если обновление уже скачано, кнопка работает как "Перезапустить"
        if self._pending_update_path:
            self._btn_action.setEnabled(False)
            self._btn_close.setEnabled(False)
            self._append_log(TextStore.Updates.LOG_RESTARTING)
            win_logic.UpdateInstaller.restart_and_cleanup(self._pending_update_path)
            return
        
        # Иначе - начинаем скачивание
        self._btn_action.setEnabled(False)
        self._btn_close.setEnabled(False)
        
        # Show technical widgets
        self._progress.setValue(0)
        self._progress.show()
        self._lbl_path_title.show()
        self._path_container.show()  # Show container instead of just input
        self._lbl_log_title.show()
        self._log_console.show()
        
        self._lbl_status_title.setText(TextStore.Updates.STATUS_DOWNLOADING.format(0))
        
        # Передаем версию в менеджер загрузки
        self._manager.download_update(self._download_url, self._version_str)
    
    def _format_bytes(self, size: int) -> str:
        """Форматирует байты в читаемый вид (KB, MB)."""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.2f} {unit}"
            size /= 1024
        return f"{size:.2f} TB"
    
    def _on_progress(self, percent: int, received: int, total: int):
        self._progress.setValue(percent)
        
        # Базовый текст из констант (например, "Загрузка: 36%")
        base_text = TextStore.Updates.STATUS_DOWNLOADING.format(percent)
        
        # Форматирование размера
        rec_str = self._format_bytes(received)
        tot_str = self._format_bytes(total)
        
        # Добавляем информацию о размере серым цветом и меньшим шрифтом
        final_text = f"{base_text} <span style='font-size: 10pt; color: #AAAAAA;'>({rec_str} / {tot_str})</span>"
        
        self._lbl_status_title.setText(final_text)
    
    def _on_download_finished(self, path: str):
        self._lbl_status_title.setText(TextStore.Updates.STATUS_INSTALLING)
        self._progress.setValue(100)
        self._append_log(TextStore.Updates.LOG_READY)
        
        # Сохраняем путь для последующего перезапуска
        self._pending_update_path = path
        
        # Активируем кнопку для ручного перезапуска
        self._btn_action.setText(TextStore.Updates.BTN_RESTART)
        self._btn_action.setEnabled(True)
        self._btn_action.setFocus()
        
        # Разрешаем закрыть окно (если пользователь хочет отложить)
        self._btn_close.setEnabled(True)
    
    def _on_error(self, msg: str):
        self._lbl_icon.setText(TextStore.Common.ICON_ERROR)
        self._lbl_status_title.setText(TextStore.Common.TITLE_ERROR)
        self._lbl_status_sub.setText(TextStore.Updates.STATUS_ERROR.format(msg))
        
        self._progress.hide()
        self._btn_action.setEnabled(True)
        self._btn_close.setEnabled(True)