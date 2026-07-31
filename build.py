import os
import sys
import subprocess
import time
import shutil
import re
import importlib.util
import json  # Добавлено для парсинга списка сертификатов
from datetime import datetime


# Цветовые коды для консоли
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    WHITE = '\033[97m'


# ----------------------------------------------------------------
# ИСПРАВЛЕНИЕ ИМПОРТА КОНФИГУРАЦИИ
# ----------------------------------------------------------------
# Принудительно добавляем папку скрипта в начало путей поиска модулей.
# Это решает проблему AttributeError, если в системе есть другой модуль 'config'.
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

try:
    import config
except ImportError:
    print(f"{Colors.FAIL}❌ ОШИБКА: Файл 'config.py' не найден.{Colors.ENDC}")
    print("   Скрипт сборки должен находиться в одной папке с исходным кодом.")
    sys.exit(1)


def is_package_installed(package_name):
    """Проверяет, установлен ли пакет в текущем окружении Python."""
    return importlib.util.find_spec(package_name) is not None


def kill_existing_process(filename):
    """Принудительно завершает процесс, если он запущен."""
    print(f"{Colors.WARNING}🧹 Очистка перед сборкой...{Colors.ENDC}")
    
    # 1. Убиваем процесс
    try:
        # taskkill /F (force) /IM (image name)
        subprocess.run(f'taskkill /F /IM "{filename}"', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1)  # Даем Windows время освободить файл
    except Exception:
        pass
    
    # 2. Удаляем старый файл (на всякий случай)
    if os.path.exists(filename):
        try:
            os.remove(filename)
            print(f"   🗑️  Удален старый файл: {filename}")
        except PermissionError:
            print(f"{Colors.FAIL}❌ НЕ УДАЛОСЬ УДАЛИТЬ ФАЙЛ!{Colors.ENDC}")
            print(f"   Файл '{filename}' занят другой программой или антивирусом.")
            print("   Пожалуйста, закройте его вручную и попробуйте снова.")
            sys.exit(1)


def sign_executable(filepath):
    """
    Умная функция подписи:
    1. Ищет существующие сертификаты.
    2. Если их много — предлагает выбрать.
    3. Если нет — создает новый с правильным FriendlyName.
    """
    print(f"\n{Colors.WARNING}🔏 Наложение цифровой подписи (Self-Signed)...{Colors.ENDC}")
    
    abs_path = os.path.abspath(filepath)
    cert_org_name = str(config.ORG_NAME).replace('"', '')
    friendly_name = f"{cert_org_name} Code Signing"
    
    # --- ШАГ 1: Поиск существующих сертификатов ---
    # Получаем список в формате JSON для удобного парсинга в Python
    ps_find = f"""
    $certs = Get-ChildItem -Path Cert:\\CurrentUser\\My | Where-Object {{ $_.Subject -match "CN={cert_org_name}" }}
    $result = @()
    foreach ($c in $certs) {{
        $result += @{{
            Thumbprint = $c.Thumbprint
            Subject = $c.Subject
            NotAfter = $c.NotAfter.ToString("dd.MM.yyyy")
            FriendlyName = $c.FriendlyName
        }}
    }}
    $result | ConvertTo-Json -Depth 2
    """
    
    selected_thumbprint = None
    
    try:
        cmd_find = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_find]
        res_find = subprocess.run(cmd_find, capture_output=True, text=True)
        
        certs = []
        if res_find.stdout.strip():
            try:
                # Если сертификат один, PowerShell может вернуть объект, а не массив. Приводим к списку.
                data = json.loads(res_find.stdout)
                if isinstance(data, dict):
                    certs = [data]
                elif isinstance(data, list):
                    certs = data
            except json.JSONDecodeError:
                pass
        
        # --- ШАГ 2: Логика выбора ---
        if not certs:
            print(f"   🆕 Сертификат не найден. Создание нового...")
            
            # Создаем новый сертификат с FriendlyName
            ps_create = f"""
            $cert = New-SelfSignedCertificate -DnsName "{cert_org_name}" -FriendlyName "{friendly_name}" -CertStoreLocation "Cert:\\CurrentUser\\My" -Type CodeSigningCert -NotAfter (Get-Date).AddYears(5)
            Write-Host $cert.Thumbprint
            """
            cmd_create = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_create]
            res_create = subprocess.run(cmd_create, capture_output=True, text=True)
            
            if res_create.returncode == 0 and res_create.stdout.strip():
                selected_thumbprint = res_create.stdout.strip()
                print(f"   ✨ Создан новый сертификат: {selected_thumbprint}")
            else:
                print(f"{Colors.FAIL}❌ Не удалось создать сертификат.{Colors.ENDC}")
                return False
        
        elif len(certs) == 1:
            # Один сертификат — используем его автоматически
            c = certs[0]
            print(f"   🔄 Использование существующего сертификата:")
            print(f"      ID: {c['Thumbprint']} | До: {c['NotAfter']} | {c.get('FriendlyName', '')}")
            selected_thumbprint = c['Thumbprint']
        
        else:
            # Несколько сертификатов — предлагаем выбор
            print(f"   ⚠️  Найдено несколько сертификатов для '{cert_org_name}':")
            print(f"{Colors.CYAN}   {'-' * 60}{Colors.ENDC}")
            for idx, c in enumerate(certs):
                f_name = c.get('FriendlyName') or "<Без названия>"
                print(f"   [{idx + 1}] Дата: {c['NotAfter']} | {f_name}")
                print(f"       ID: {c['Thumbprint']}")
            print(f"{Colors.CYAN}   {'-' * 60}{Colors.ENDC}")
            
            while True:
                try:
                    choice = input(f"   👉 Выберите номер сертификата (1-{len(certs)}): ")
                    choice_idx = int(choice) - 1
                    if 0 <= choice_idx < len(certs):
                        selected_thumbprint = certs[choice_idx]['Thumbprint']
                        break
                    else:
                        print(f"   ❌ Неверный номер.")
                except ValueError:
                    print(f"   ❌ Введите число.")
    
    except Exception as e:
        print(f"{Colors.FAIL}❌ Ошибка при поиске сертификатов: {e}{Colors.ENDC}")
        return False
    
    # --- ШАГ 3: Подпись файла выбранным сертификатом ---
    if selected_thumbprint:
        ps_sign = f"""
        $cert = Get-Item -Path "Cert:\\CurrentUser\\My\\{selected_thumbprint}"
        Set-AuthenticodeSignature -Certificate $cert -FilePath "{abs_path}"
        if ($?) {{ Write-Host "SIGNATURE_SUCCESS" }}
        """
        
        try:
            cmd_sign = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_sign]
            res_sign = subprocess.run(cmd_sign, capture_output=True, text=True)
            
            if res_sign.returncode == 0 and "SIGNATURE_SUCCESS" in res_sign.stdout:
                print(f"{Colors.GREEN}✅ Файл успешно подписан сертификатом '{cert_org_name}'!{Colors.ENDC}")
                return True
            else:
                print(f"{Colors.FAIL}❌ Ошибка при наложении подписи:{Colors.ENDC}")
                print(res_sign.stderr or res_sign.stdout)
                return False
        except Exception as e:
            print(f"{Colors.FAIL}❌ Ошибка запуска PowerShell для подписи: {e}{Colors.ENDC}")
            return False
    
    return False


# ----------------------------------------------------------------
# SECURITY GATE (Двойная проверка антивирусами)
# ----------------------------------------------------------------

def _find_kaspersky_cli():
    """Ищет консольную утилиту avp.com в стандартных папках установки."""
    search_roots = [
        os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)") + r"\Kaspersky Lab",
        os.environ.get("ProgramFiles", r"C:\Program Files") + r"\Kaspersky Lab"
    ]
    
    for root in search_roots:
        if os.path.exists(root):
            # Рекурсивно ищем avp.com, так как версия папки может меняться
            for dirpath, _, filenames in os.walk(root):
                if "avp.com" in filenames:
                    return os.path.join(dirpath, "avp.com")
    return None


def run_security_gate(filepath):
    """
    Запускает комплексную проверку файла через Windows Defender и Kaspersky.
    Выводит красивый отчет (Dashboard) в консоль.
    Улучшен парсинг вывода для обработки ошибок кодировки и кодов возврата.
    """
    print(f"\n{Colors.CYAN}🛡️ ЗАПУСК КОМПЛЕКСНОЙ ПРОВЕРКИ БЕЗОПАСНОСТИ...{Colors.ENDC}")
    print(f"{Colors.CYAN}{'-' * 60}{Colors.ENDC}")
    
    # --- 1. Windows Defender ---
    def_status = "SKIPPED"
    def_msg = "Недоступен / Отключен"
    def_color = Colors.WARNING
    
    mp_cmd = r"C:\Program Files\Windows Defender\MpCmdRun.exe"
    
    if os.path.exists(mp_cmd):
        try:
            # -ScanType 3 = File Check
            cmd = [mp_cmd, "-Scan", "-ScanType", "3", "-File", filepath]
            # Timeout 45s (Defender может долго инициализироваться)
            # capture_output=True возвращает bytes, что позволяет нам декодировать их вручную
            res = subprocess.run(cmd, capture_output=True, timeout=45)
            
            # Декодируем вывод, пробуем cp866 (стандарт для русской консоли) или utf-8
            try:
                output = res.stdout.decode('cp866', errors='ignore')
            except:
                output = res.stdout.decode('utf-8', errors='ignore')
            
            if res.returncode == 0:
                def_status = "CLEAN"
                def_msg = "✅ Угроз не обнаружено"
                def_color = Colors.GREEN
            elif res.returncode == 2:
                def_status = "INFECTED"
                def_color = Colors.FAIL
                # Пытаемся найти имя угрозы: "Threat : Trojan:Win32/..."
                match = re.search(r"Threat\s+:\s+(.+)", output)
                if match:
                    threat_name = match.group(1).strip()
                    def_msg = f"❌ {threat_name}"
                else:
                    def_msg = "❌ ОБНАРУЖЕНА УГРОЗА!"
            else:
                def_status = "ERROR"
                def_msg = f"⚠️ Ошибка проверки (Code {res.returncode})"
                def_color = Colors.WARNING
        except subprocess.TimeoutExpired:
            def_status = "TIMEOUT"
            def_msg = "⏳ Время ожидания истекло"
        except Exception:
            def_status = "ERROR"
            def_msg = "⚠️ Ошибка запуска"
    
    # --- 2. Kaspersky Antivirus ---
    kav_status = "SKIPPED"
    kav_msg = "Не установлен / Не найден avp.com"
    kav_color = Colors.WARNING
    
    avp_path = _find_kaspersky_cli()
    
    if avp_path:
        try:
            # avp.com SCAN <file>
            cmd = [avp_path, "SCAN", filepath]
            # Timeout 60s
            res = subprocess.run(cmd, capture_output=True, timeout=60)
            
            try:
                # Декодируем вывод (stdout + stderr)
                output = (res.stdout + res.stderr).decode('cp866', errors='ignore')
            except:
                output = (res.stdout + res.stderr).decode('utf-8', errors='ignore')
            
            # --- Логика анализа вывода Kaspersky ---
            # Игнорируем код возврата (res.returncode), смотрим в текст.
            
            is_clean = False
            # Ищем ключевые фразы успеха
            if "Total detected: 0" in output or "Detected: 0" in output or "OK" in output:
                is_clean = True
            
            if is_clean:
                kav_status = "CLEAN"
                kav_msg = "✅ Угроз не обнаружено"
                kav_color = Colors.GREEN
            elif "Total detected" in output and "Total detected: 0" not in output:
                kav_status = "INFECTED"
                kav_msg = "❌ ОБНАРУЖЕНА УГРОЗА!"
                kav_color = Colors.FAIL
            else:
                # Если ничего не поняли из текста, но код возврата 0
                if res.returncode == 0:
                    kav_status = "CLEAN"
                    kav_msg = "✅ Проверка завершена (Clean)"
                    kav_color = Colors.GREEN
                else:
                    # Если текст странный и код ошибки (например -3)
                    kav_status = "UNKNOWN"
                    kav_msg = f"⚠️ Неясный статус (Code {res.returncode})"
        
        except subprocess.TimeoutExpired:
            kav_status = "TIMEOUT"
            kav_msg = "⏳ Время ожидания истекло"
        except Exception:
            kav_status = "ERROR"
            kav_msg = "⚠️ Ошибка запуска"
    
    # --- Вывод таблицы (Dashboard) ---
    print(f"🔍 Windows Defender   [{def_color}{def_status.center(8)}{Colors.ENDC}]  {def_msg}")
    print(f"🔍 Kaspersky          [{kav_color}{kav_status.center(8)}{Colors.ENDC}]  {kav_msg}")
    print(f"{Colors.CYAN}{'-' * 60}{Colors.ENDC}")
    
    # Итоговый вердикт
    if def_status == "INFECTED" or kav_status == "INFECTED":
        print(f"{Colors.FAIL}🛑 СБОРКА НЕБЕЗОПАСНА! Найдены угрозы.{Colors.ENDC}")
    elif def_status == "CLEAN" and kav_status == "CLEAN":
        print(f"{Colors.GREEN}🚀 ИТОГ: Файл прошел двойную проверку. Готов к релизу.{Colors.ENDC}")
    else:
        print(f"{Colors.WARNING}⚠️ ИТОГ: Проверка выполнена частично. Будьте внимательны.{Colors.ENDC}")


def _normalize_version(version_str: str) -> str:
    """
    Преобразует версию вида 'v0.9.6-beta' или '0.9.6' в строгий формат Windows '0.9.6.0'.
    """
    numbers = re.findall(r'\d+', version_str)
    if not numbers:
        return "1.0.0.0"
    parts = numbers[:4]
    while len(parts) < 4:
        parts.append('0')
    return '.'.join(parts)


def main():
    # Очистка консоли
    os.system('cls' if os.name == 'nt' else 'clear')
    
    # Подготовка данных из конфига
    # Используем getattr для безопасности, но благодаря фиксу sys.path это должно работать штатно
    app_name = str(getattr(config, 'APP_NAME_DISPLAY', 'Ethereum Gas Tracker')).strip()
    org_name = str(getattr(config, 'ORG_NAME', 'Makis Software')).strip()
    raw_version = str(getattr(config, 'APP_VERSION', '1.0.0')).strip()
    win_version = _normalize_version(raw_version)
    
    # Имя системной папки для кэша
    system_name = getattr(config, 'APP_NAME_SYSTEM', 'EthereumGasTracker')
    
    current_year = datetime.now().year
    copyright_str = f"Copyright (c) {current_year} {org_name}"
    trademarks_str = f"{app_name}™"
    
    # Метаданные
    file_description = app_name
    
    # Имя выходного файла
    output_filename = config.get_executable_filename(raw_version)
    
    # Сертификат
    cert_name = org_name.replace('"', '')
    
    # ВАЖНО: Сначала убиваем старый процесс!
    kill_existing_process(output_filename)
    
    # Путь для кэшированной распаковки
    temp_dir_spec = f"{{CACHE_DIR}}/{org_name}/{system_name}/{{VERSION}}"
    
    print(f"{Colors.HEADER}{'=' * 60}{Colors.ENDC}")
    print(f"🚀 ЗАПУСК СБОРКИ (SECURE MODE): {Colors.BOLD}{app_name} {raw_version}{Colors.ENDC}")
    print(f"{Colors.HEADER}{'=' * 60}{Colors.ENDC}")
    
    # 1. Проверка окружения
    icon_path = "icon.ico"
    icon_args = []
    
    if os.path.exists(icon_path):
        icon_args = [
            f"--windows-icon-from-ico={icon_path}",
            f"--include-data-file={icon_path}={icon_path}",
        ]
        icon_status = f"{Colors.GREEN}Найденa ({icon_path}){Colors.ENDC}"
    else:
        icon_status = f"{Colors.WARNING}Не найдена (будет стандартная){Colors.ENDC}"
    
    has_toasts = is_package_installed("windows_toasts")
    if has_toasts:
        toasts_status = f"{Colors.GREEN}Установлен{Colors.ENDC}"
    else:
        toasts_status = f"{Colors.WARNING}Не найден{Colors.ENDC}"
    
    # ----------------------------------------------------------------
    # ВЫВОД ПОЛНОЙ ИНФОРМАЦИИ (DASHBOARD)
    # ----------------------------------------------------------------
    
    # Блок 1: Метаданные файла (Windows Version Info)
    print(f"\n{Colors.CYAN}📄 Метаданные файла (Свойства -> Подробно):{Colors.ENDC}")
    print(f"   🏢 CompanyName:      {Colors.WHITE}{org_name}{Colors.ENDC}")
    print(f"   📦 ProductName:      {Colors.WHITE}{app_name}{Colors.ENDC}")
    print(f"   📄 FileDescription:  {Colors.WHITE}{file_description}{Colors.ENDC}")
    print(f"   🔢 ProductVersion:   {Colors.WHITE}{win_version}{Colors.ENDC}")
    print(f"   fv FileVersion:      {Colors.WHITE}{win_version}{Colors.ENDC}")
    print(f"   ©️ LegalCopyright:   {Colors.WHITE}{copyright_str}{Colors.ENDC}")
    print(f"   ™️ LegalTrademarks:  {Colors.WHITE}{trademarks_str}{Colors.ENDC}")
    print(f"   💾 OriginalFilename: {Colors.WHITE}{output_filename}{Colors.ENDC}")
    
    # Блок 2: Цифровая подпись (Code Signing)
    print(f"\n{Colors.CYAN}🔏 Цифровая подпись (Свойства -> Цифровые подписи):{Colors.ENDC}")
    print(f"   ✅ Status:           {Colors.GREEN}ENABLED{Colors.ENDC}")
    print(f"   👤 Certificate CN:   {Colors.BOLD}{cert_name}{Colors.ENDC}")
    print(f"   🔑 Type:             Self-Signed (With Interactive Selection)")
    print(f"   📅 Validity:         5 Years")
    print(f"   📂 Store:            Cert:\\CurrentUser\\My")
    
    # Блок 3: Настройки компилятора (Nuitka)
    print(f"\n{Colors.CYAN}⚙️ Настройки компилятора (Nuitka):{Colors.ENDC}")
    print(f"   📦 Mode:             {Colors.WHITE}Onefile (Standalone){Colors.ENDC}")
    print(f"   🖥️ Console:          {Colors.WHITE}Disabled (GUI only){Colors.ENDC}")
    print(f"   🛡️ Static LibPython: {Colors.WARNING}DISABLED{Colors.ENDC} (Not supported by standard Python)")
    print(f"   📦 UPX Compression:  {Colors.WARNING}DISABLED{Colors.ENDC} (Anti-Heuristic)")
    print(f"   📂 Temp Dir Spec:    {Colors.WHITE}{temp_dir_spec}{Colors.ENDC}")
    
    # Блок 4: Ресурсы
    print(f"\n{Colors.CYAN}📦 Ресурсы и Зависимости:{Colors.ENDC}")
    print(f"   🎨 Icon:             {icon_status}")
    print(f"   🔔 Toasts Lib:       {toasts_status}")
    
    # 3. Сборка команды Nuitka
    nuitka_cmd = [
        sys.executable, "-m", "nuitka",
        
        # --- Базовые настройки ---
        "--standalone",
        "--onefile",
        "--enable-plugin=pyside6",
        "--windows-console-mode=disable",
        "--remove-output",
        "--assume-yes-for-downloads",
        
        # --- SECURITY & STABILITY (Anti-Virus Evasion) ---
        # Флаг UPX удален, так как он вызывает ошибку в текущей версии Nuitka.
        # Если UPX не установлен в системе, сжатие не будет применяться автоматически.
        "--unstripped",  # Сохранение символов для легитимного вида
        
        # --- Оптимизация ---
        "--nofollow-import-to=pytest",
        "--nofollow-import-to=unittest",
        "--nofollow-import-to=tkinter",
        "--clean-cache=all",
        f"--onefile-tempdir-spec={temp_dir_spec}",
        
        # --- Метаданные Windows ---
        f"--windows-company-name={org_name}",
        f"--windows-product-name={app_name}",
        f"--windows-file-version={win_version}",
        f"--windows-product-version={win_version}",
        f"--windows-file-description={file_description}",
        f"--copyright={copyright_str}",
        f"--trademarks={trademarks_str}",
        
        # --- Выходной файл ---
        f"--output-filename={output_filename}",
        
        # --- Точка входа ---
        "main.py"
    ]
    
    if has_toasts:
        nuitka_cmd.append("--include-package=windows_toasts")
        nuitka_cmd.append("--include-package=winsdk")
    
    nuitka_cmd.extend(icon_args)
    
    # 4. Выполнение компиляции
    print(f"\n{Colors.BLUE}⏳ Компиляция началась...{Colors.ENDC}\n")
    
    try:
        process = subprocess.run(nuitka_cmd, stderr=subprocess.STDOUT)
        
        if process.returncode == 0:
            print(f"\n{Colors.GREEN}{'=' * 60}{Colors.ENDC}")
            print(f"{Colors.GREEN}✅ КОМПИЛЯЦИЯ ЗАВЕРШЕНА!{Colors.ENDC}")
            
            # 5. Подписание файла
            if os.path.exists(output_filename):
                sign_executable(output_filename)
            
            # 6. Удаление PDB (Очистка отладочных символов)
            pdb_file = output_filename.replace(".exe", ".pdb")
            if os.path.exists(pdb_file):
                try:
                    os.remove(pdb_file)
                    print(f"   🗑️  Удален файл символов: {pdb_file}")
                except Exception:
                    pass
            
            # 7. Комплексная проверка безопасности (Defender + Kaspersky)
            run_security_gate(output_filename)
            
            print(f"\n   Файл: {Colors.BOLD}{os.path.abspath(output_filename)}{Colors.ENDC}")
            print(f"{Colors.GREEN}{'=' * 60}{Colors.ENDC}")
        else:
            raise subprocess.CalledProcessError(process.returncode, nuitka_cmd)
    
    except subprocess.CalledProcessError:
        print(f"\n{Colors.FAIL}{'=' * 60}{Colors.ENDC}")
        print(f"{Colors.FAIL}❌ ОШИБКА СБОРКИ{Colors.ENDC}")
        print(f"{Colors.FAIL}{'=' * 60}{Colors.ENDC}")
        sys.exit(1)
    except KeyboardInterrupt:
        print(f"\n{Colors.WARNING}🛑 Сборка прервана пользователем.{Colors.ENDC}")
        sys.exit(1)


if __name__ == "__main__":
    main()