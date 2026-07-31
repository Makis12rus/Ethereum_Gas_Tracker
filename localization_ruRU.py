from __future__ import annotations

# -*- coding: utf-8 -*-

"""
Аннотация

🧩 1. Назначение файла
- Единственный источник правды для Русской локализации (ruRU).
- Содержит только текстовые данные и шаблоны форматирования.
- Полностью заменяет старый ui_dialogs_cont.py.

🧱 2. Структура
- Locale: Корневой класс.
    - Meta: Метаданные языка.
    - Common: Общие кнопки и заголовки.
    - App: Системные строки приложения.
    - Hud: Тексты главного виджета.
    - Popup: Тексты всплывающего окна.
    - Menu: Пункты контекстного меню.
    - Wizard: Мастер настройки (бывший ApiSetup).
    - Settings: Диалоги ввода (бывший Inputs).
    - About: Окно "О программе".
    - Updates: Окно обновлений.
    - Errors: Сообщения об ошибках.

⚙️ 3. Особенности
- Отсутствие импортов логики (config, services).
- Использование {placeholder} для динамических данных.
"""


class Locale:
    """
    Хранилище текстовых констант для русской локализации.
    """
    
    class Meta:
        CODE = "ru_RU"
        NAME = "Русский"
    
    class Common:
        """Общие элементы интерфейса."""
        BTN_OK = "OK"
        BTN_CANCEL = "Отмена"
        BTN_CLOSE_X = "✕"
        
        TITLE_ERROR = "Ошибка"
        TITLE_WARNING = "ВНИМАНИЕ"
        TITLE_INFO = "Информация"
        
        ICON_INFO = "ℹ️"
        ICON_WARNING = "⚠️"
        ICON_ERROR = "⚠️"
    
    class App:
        """Системные строки приложения."""
        # Используется для заголовков окон и тултипов
        TITLE_TEMPLATE = "{name} {version}"
        DESCRIPTION_LONG = (
            "Компактный, ненавязчивый виджет для Windows, "
            "который отображает цену газа (Gwei) в реальном времени. "
        )
    
    class Hud:
        """Тексты главного виджета (Dock)."""
        PREFIX_ETH = "⛽ ETH: "
        SUFFIX_GWEI = " Gwei "
        STATUS_WAIT = "Wait..."
        # Символы трендов
        ARROW_UP = " ↗"
        ARROW_DOWN = " ↘"
        VAL_PLACEHOLDER = "-"
    
    class Popup:
        """Тексты всплывающего окна (GasDetailPopup)."""
        TITLE_LOW = "LOW"
        TITLE_AVG = "AVERAGE"
        TITLE_HIGH = "HIGH"
        
        LBL_BASE = "Base:"
        LBL_PRIO = "Prio:"
        
        PREFIX_ETH_PRICE = "ETH: $"
        LBL_UPDATED_DEFAULT = "--:--"
        
        # Шаблон футера карточки: "💵 $0.50  •  30s"
        FOOTER_TEMPLATE = "💵 ${cost:.2f}  •  {time}"
        TIME_EST_LOW = "10m"
        TIME_EST_MID = "3m"
        TIME_EST_HIGH = "30s"
    
    class Menu:
        """Пункты контекстного меню."""
        SECTION_SETTINGS = "Настройки"
        SECTION_CONFIG = "Конфигурация"
        SECTION_TASKS = "Задачи"
        
        SUBMENU_INTERVAL = "Интервал обновления"
        ITEM_THRESHOLD = "Порог уведомлений"
        ITEM_THRESHOLD_FMT = "Порог уведомлений ({0:.1f} Gwei)"
        ITEM_THRESHOLD_OFF = "Порог уведомлений (Выкл)"
        
        ITEM_RPC = "Настроить RPC..."
        ITEM_API = "Указать API ключ..."
        
        ITEM_REFRESH = "Обновить цену"
        ITEM_TEST_NOTIFY = "Тест уведомления"
        ITEM_CHECK_UPDATES = "Проверить обновления"
        
        ITEM_ABOUT = "О программе"
        ITEM_EXIT = "Выход"
        
        VAL_CUSTOM = "Произвольный..."
        
        # Названия режимов для отображения в меню
        MODE_RPC = "RPC"
        MODE_API = "Etherscan API"
    
    class Wizard:
        """Контент для Мастера настройки (ранее ApiSetup)."""
        TITLE_WINDOW = "Выбор режима работы Ethereum Gas Tracker"
        
        # Header
        ICON_HEADER = "🔑"
        LBL_HEADER_MAIN = "Выбор режима работы Ethereum Gas Tracker"
        LBL_HEADER_SUB = (
            "Для максимальной точности и скорости рекомендуем Etherscan API.\n"
            "Режим RPC подойдет для быстрого старта без регистрации в сервисе Etherscan."
        )
        
        # Card: RPC
        CARD_RPC_MODE = "rpc"
        CARD_RPC_ICON = "⚠️"
        CARD_RPC_TITLE = "RPC (Публичные узлы)"
        
        CARD_RPC_TEXT_INTRO = (
            "<div style='font-size: 9pt; color: #DDDDDD;'>"
            "Программа подключается к общедоступным узлам сети Ethereum по RPC-протоколу и получает от них данные."
            "</div>"
        )
        
        CARD_RPC_TEXT_DETAILS = (
            "<div style='font-size: 9pt; color: #DDDDDD;'>"
            "<b style='color: #FFD700;'>⚠ Важно знать:</b>"
            "<ul style='margin-left: -15px;'>"
            "<li>Публичные узлы часто перегружены.</li>"
            "<li>Данные могут <b>запаздывать на 10–20 секунд и более</b>: вы видите состояние сети 'чуть в прошлом', а не прямо сейчас.</li>"
            "<li>Скорость и качество зависят от конкретного RPC-провайдера и его нагрузки.</li>"
            "<li>Иногда возможны кратковременные ошибки и пропуски обновлений.</li>"
            "</ul>"
            
            "<b style='color: #FFD700;'>Этот режим подходит, если:</b>"
            "<ul style='margin-left: -15px;'>"
            "<li>Вы просто смотрите цену газа 'в среднем по больнице';</li>"
            "<li>Вам не критична точность до секунды;</li>"
            "<li>Вы не хотите заводить аккаунт на Etherscan и возиться с ключом.</li>"
            "</ul>"
            "</div>"
        )
        
        # Card: API
        CARD_API_MODE = "api"
        CARD_API_ICON = "🚀"
        CARD_API_TITLE = "Etherscan API"
        
        CARD_API_TEXT_INTRO = (
            "<div style='font-size: 9pt; color: #DDDDDD;'>"
            "В этом режиме приложение работает через официальный API сервиса <b>Etherscan</b> с использованием вашего личного API-ключа."
            "</div>"
        )
        
        CARD_API_TEXT_DETAILS = (
            "<div style='font-size: 9pt; color: #DDDDDD;'>"
            "<b style='color: #4A90E2;'>🚀 Что это даёт:</b>"
            "<ul style='margin-left: -15px;'>"
            "<li><b>Доступ к мемпулу</b><br>"
            "<span style='color: #AAAAAA;'>Вы видите транзакции ещё <b>до того, как они попадут в блок</b>, а значит, и цену газа более актуально.</span></li>"
            
            "<li style='margin-top: 4px;'><b>Более стабильные данные</b><br>"
            "<span style='color: #AAAAAA;'>Etherscan собирает информацию с множества узлов и агрегирует её. Это обычно надёжнее, чем случайный публичный RPC.</span></li>"
            
            "<li style='margin-top: 4px;'><b>Лучшее совпадение с интерфейсом Etherscan</b><br>"
            "<span style='color: #AAAAAA;'>Значения комиссии и газ-трекера будут максимально близки к тому, что вы видите на сайте Etherscan.</span></li>"
            "</ul>"
            
            "<b style='color: #4A90E2;'>🔑 Зачем нужен ключ:</b>"
            "<ul style='margin-left: -15px;'>"
            "<li>Ключ нужен, чтобы Etherscan понимал, кто отправляет запросы, и защищал свои сервера от злоупотреблений.</li>"
            "<li>Бесплатного ключа достаточно для нормальной работы трекера: лимита запросов хватит с запасом для обычного пользователя.</li>"
            "</ul>"
            
            "<b style='color: #4A90E2;'>✅ Этот режим подходит, если:</b>"
            "<ul style='margin-left: -15px;'>"
            "<li>Вам важна <b>максимально точная и свежая цена газа</b>;</li>"
            "<li>Вы хотите видеть картину сети ближе к реальному времени;</li>"
            "<li>Используете приложение как серьёзный инструмент, а не просто 'посмотреть одним глазом'.</li>"
            "</ul>"
            "</div>"
        )
        
        # Help Block
        HTML_HELP_BLOCK = (
            "<div style='color: #DDDDDD; font-size: 9pt; margin-top: 5px; margin-bottom: 5px;'>"
            "<b style='font-size: 10pt; color: white;'>Какой режим лучше?</b>"
            "<ul style='margin-left: -20px; margin-top: 5px;'>"
            "<li>Если вы хотите 'просто попробовать' или не хотите сейчас регистрироваться - "
            "нажмите <b>'Использовать RPC'</b>. Приложение будет работать, но данные могут немного отставать.</li>"
            "<li style='margin-top: 5px;'>Если вы хотите <b>надёжные и максимально актуальные данные</b>, "
            "рекомендуется получить бесплатный ключ на Etherscan и запустить в режиме <b>Etherscan API</b>.</li>"
            "</ul></div>"
        )
        
        # Page: RPC Action
        LBL_RPC_WARN = (
            "⚠️ Публичные RPC-узлы часто перегружены.\n"
            "Возможны задержки обновления данных и ошибки соединения."
        )
        BTN_USE_RPC = "ИСПОЛЬЗОВАТЬ RPC"
        BTN_AUTO_FIND = "⚡ Найти быстрые узлы"
        BTN_FINDING = "Поиск лучших узлов..."
        BTN_FIND_PROGRESS_FMT = "{0} / {1}"
        
        # Page: API Action
        LBL_API_PROMO = (
            "🚀 Максимальная скорость и точность данных.\n"
            "Прямой доступ к мемпулу и стабильное соединение."
        )
        PLACEHOLDER_KEY = "Вставьте ваш API-ключ Etherscan сюда..."
        LBL_SECURITY_NOTE = "Не храните этот ключ в открытом доступе. Он используется только в этой программе."
        HTML_LINK_GET_KEY = (
            "<a href='https://etherscan.io/apidashboard' style='color: #4A90E2; text-decoration: none;'>"
            "Получить бесплатный ключ на Etherscan</a>"
        )
        BTN_SAVE_AND_START = "СОХРАНИТЬ И ЗАПУСТИТЬ"
        
        # Alerts & Dialogs
        ALERT_EMPTY_KEY_MSG = (
            "Поле ключа не может быть пустым.\n"
            "Если у вас нет ключа, выберите режим RPC."
        )
        
        DIALOG_SWITCH_TITLE = "Смена режима"
        DIALOG_SWITCH_MSG = (
            "Вы удаляете API ключ. Программа переключится в режим RPC (публичные узлы). "
            "Данные могут поступать с задержкой. Продолжить?"
        )
        BTN_CONFIRM_SWITCH = "Да, переключить на RPC"
        
        # Validation Statuses
        BTN_CHECKING = "ПРОВЕРКА..."
        BTN_SUCCESS = "УСПЕШНО!"
        BTN_ERR_LIST = "ОШИБКИ В СПИСКЕ"
    
    class Settings:
        """Тексты для диалогов ввода (ранее Inputs)."""
        TITLE_INTERVAL = "Интервал"
        LBL_INTERVAL = "Введите интервал (сек):"
        
        TITLE_THRESHOLD = "Порог"
        LBL_THRESHOLD = "Gwei (0=выкл):"
    
    class About:
        """Контент для окна 'О программе'."""
        TITLE_WINDOW = "О программе"
        
        LBL_FOOTER_LOVE = "Сделано с заботой о криптанах ❤️"
        # Шаблон ссылки Donate (URL подставляется в коде)
        HTML_LINK_DONATE_TEMPLATE = (
            "<a href='{url}' style='color: #4A90E2; text-decoration: underline;'>Donate</a>"
        )
        
        # Шаблон основного текста (Цвета и размеры подставляются в коде)
        HTML_BODY_TEMPLATE = (
            "<div style='color:{color_text}; font-size:{font_size_body}pt;'>"
            "<h2 style='margin-bottom:5px; font-size:{font_size_title}pt; color:{color_text};'>"
            "⛽ {app_caption}"
            "</h2>"
            "<p>Компактный трекер цены газа Ethereum, встроенный в панель задач Windows.</p>"
            "<hr>"
            "<b>💡 Возможности:</b>"
            "<ul>"
            "<li>Мониторинг цены газа (Gwei) в реальном времени.</li>"
            "<li>Цветовая индикация нагрузки сети.</li>"
            "<li>Автоматическое переключение Etherscan API -> RPC.</li>"
            "<li>Уведомления при достижении целевой цены.</li>"
            "</ul>"
            "</div>"
        )
    
    class Updates:
        """Контент для системы обновлений."""
        TITLE_WINDOW = "Обновление"
        
        ICON_UPDATE = "⬇️"
        ICON_LATEST = "✅"
        
        LBL_FOUND_TITLE = "Доступна новая версия"
        LBL_FOUND_SUB = "Рекомендуется установить обновление для стабильной работы."
        
        LBL_LATEST_TITLE = "Версия актуальна"
        LBL_LATEST_SUB = "Обновлений не найдено. Вы используете последнюю версию."
        
        LBL_TARGET_PATH = "Путь установки:"
        LBL_SYSTEM_LOG = "Системный журнал:"
        
        BTN_DOWNLOAD = "СКАЧАТЬ И ОБНОВИТЬ"
        BTN_RESTART = "ПЕРЕЗАПУСТИТЬ"
        BTN_CLOSE = "ЗАКРЫТЬ"
        
        STATUS_CHECKING = "Связь с GitHub..."
        STATUS_DOWNLOADING = "Загрузка: {0}%"
        STATUS_INSTALLING = "Программа готова к перезапуску..."
        STATUS_ERROR = "Ошибка: {0}"
        
        LOG_RESTARTING = "Restarting..."
        LOG_READY = "Ready to restart."
    
    class Errors:
        """Сообщения об ошибках и уведомления."""
        ERR_INVALID_KEY = "Ошибка: Неверный API ключ"
        ERR_NETWORK = "Ошибка сети: Проверьте интернет"
        
        NOTIFY_TITLE_TEST = "Тест"
        NOTIFY_MSG_TEST = "Проверка системы уведомлений"
        
        NOTIFY_TITLE_THRESHOLD = "Цена газа ниже порога"
        NOTIFY_MSG_THRESHOLD_FMT = "Текущая: {0:.3f} Gwei\nПорог: {1:.3f} Gwei"
        
        SRC_ETHERSCAN = "Etherscan API"
        SRC_RPC = "RPC"
        SRC_NA = "N/A"