import sys
import os
import ctypes

os.environ.setdefault(
    "QTWEBENGINE_CHROMIUM_FLAGS",
    "--enable-smooth-scrolling --disable-frame-rate-limit --disable-gpu-vsync --ignore-gpu-blocklist --enable-gpu-rasterization --enable-zero-copy",
)

import json
import platform
import re
import socket
import urllib.request
import uuid
import subprocess
import tempfile
import threading
import time
from datetime import datetime

import psutil
from PyQt6.QtCore import (
    Qt,
    QUrl,
    QObject,
    QThread,
    QMetaObject,
    QCoreApplication,
    QEvent,
    pyqtSlot,
    pyqtSignal,
    QPropertyAnimation,
    QEasingCurve,
    QTimer,
)
from PyQt6.QtGui import QDesktopServices, QIcon, QColor
from PyQt6.QtWidgets import QApplication, QMainWindow, QMessageBox, QFileDialog
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineSettings
from PyQt6.QtWebChannel import QWebChannel

IS_WINDOWS = platform.system() == "Windows"
IS_FROZEN = getattr(sys, "frozen", False)

if IS_WINDOWS:
    try:
        import wmi
    except ImportError:
        wmi = None
else:
    wmi = None

_cpu_state_lock = threading.Lock()
_cpu_state = {"total": 0.0, "percpu": []}


def _cpu_monitor_loop():
    while True:
        try:
            percpu = psutil.cpu_percent(interval=1, percpu=True)
        except Exception:
            time.sleep(1)
            continue
        total = sum(percpu) / len(percpu) if percpu else 0.0
        with _cpu_state_lock:
            _cpu_state["total"] = total
            _cpu_state["percpu"] = percpu


def start_cpu_monitor():
    thread = threading.Thread(target=_cpu_monitor_loop, daemon=True)
    thread.start()
    return thread


def get_cpu_usage_snapshot():
    with _cpu_state_lock:
        return _cpu_state["total"], list(_cpu_state["percpu"])


APP_NAME = "SYS IO"
APP_VERSION = "0.0.5 (Beta)"
APP_AUTHOR = "Arch"
APP_AUTHOR_HANDLE = "@xarchfx"
APP_AUTHOR_URL = "https://xarchfx.lol"
UPDATE_REPO = "xarchfx/SYS-IO"
UPDATE_RELEASES_API_URL = f"https://api.github.com/repos/{UPDATE_REPO}/releases"
UPDATE_TAGS_PAGE_URL = f"https://github.com/{UPDATE_REPO}/tags"


def get_base_dir():
    if IS_FROZEN:
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def get_resource_dir():
    if IS_FROZEN:
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


BASE_DIR = get_base_dir()
RESOURCE_DIR = get_resource_dir()
LOGO_PATH = os.path.join(RESOURCE_DIR, "assets", "SYS IO - Logo.ico")
LOGO_URI = QUrl.fromLocalFile(LOGO_PATH).toString() if os.path.exists(LOGO_PATH) else ""
BASE_URL = QUrl.fromLocalFile(BASE_DIR + os.sep)

REQUIRED_ASSETS = {
    "SYS IO - Logo.ico": LOGO_PATH,
}
UPDATE_LATEST_RELEASE_URL = f"https://github.com/{UPDATE_REPO}/releases/latest"


def get_settings_dir():
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        base = os.path.join(os.path.expanduser("~"), "AppData", "Local")
    return os.path.join(base, "SYS IO")


SETTINGS_DIR = get_settings_dir()
SETTINGS_PATH = os.path.join(SETTINGS_DIR, "settings.json")

DEFAULT_SETTINGS = {
    "theme": "dark",
    "refresh_mode": "normal",
    "refresh_custom_seconds": 3,
    "window_mode": "default",
    "start_as_admin": True,
}

RESTART_REQUIRED_KEYS = {"window_mode", "start_as_admin"}
VALID_THEMES = {"dark", "light", "halloween"}
VALID_REFRESH_MODES = {"fast", "normal", "slow", "custom"}
VALID_WINDOW_MODES = {"default", "custom"}


def validate_imported_settings(data):
    if not isinstance(data, dict):
        return {}
    result = {}
    if data.get("theme") in VALID_THEMES:
        result["theme"] = data["theme"]
    if data.get("refresh_mode") in VALID_REFRESH_MODES:
        result["refresh_mode"] = data["refresh_mode"]
    if "refresh_custom_seconds" in data:
        try:
            seconds = int(data["refresh_custom_seconds"])
            if seconds >= 0:
                result["refresh_custom_seconds"] = seconds
        except (TypeError, ValueError):
            pass
    if data.get("window_mode") in VALID_WINDOW_MODES:
        result["window_mode"] = data["window_mode"]
    if isinstance(data.get("start_as_admin"), bool):
        result["start_as_admin"] = data["start_as_admin"]
    return result


def load_settings():
    data = dict(DEFAULT_SETTINGS)
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            saved = json.load(f)
        if isinstance(saved, dict):
            data.update(saved)
    except Exception:
        pass
    return data


def save_settings(data):
    try:
        os.makedirs(SETTINGS_DIR, exist_ok=True)
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


SETTINGS = load_settings()


def is_admin():
    if not IS_WINDOWS:
        return True
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def show_admin_required_dialog():
    try:
        MB_OK = 0x0
        MB_ICONWARNING = 0x30
        ctypes.windll.user32.MessageBoxW(
            None,
            f'{APP_NAME} needs administrator rights to run.\n\nRight-click "{APP_NAME}.exe" and choose "Run as administrator", then start it again.',
            APP_NAME,
            MB_OK | MB_ICONWARNING,
        )
    except Exception:
        pass


def get_missing_assets():
    return [name for name, path in REQUIRED_ASSETS.items() if not os.path.exists(path)]


def show_missing_assets_dialog(missing_names):
    listed = "\n".join(f"- {name}" for name in missing_names)
    message = (
        f"{APP_NAME} is missing required files:\n\n{listed}\n\n"
        "The installation appears to be incomplete or damaged.\n"
        "It is recommended to reinstall the app using the latest release (.rar) from GitHub."
    )
    box = QMessageBox()
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle(APP_NAME)
    box.setText(message)
    if os.path.exists(LOGO_PATH):
        box.setWindowIcon(QIcon(LOGO_PATH))
    open_button = box.addButton("Open Latest Release", QMessageBox.ButtonRole.ActionRole)
    box.addButton("Continue Anyway", QMessageBox.ButtonRole.RejectRole)
    box.exec()
    if box.clickedButton() == open_button:
        try:
            QDesktopServices.openUrl(QUrl(UPDATE_LATEST_RELEASE_URL))
        except Exception:
            pass


class _SHELLEXECUTEINFOW(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_uint32),
        ("fMask", ctypes.c_ulong),
        ("hwnd", ctypes.c_void_p),
        ("lpVerb", ctypes.c_wchar_p),
        ("lpFile", ctypes.c_wchar_p),
        ("lpParameters", ctypes.c_wchar_p),
        ("lpDirectory", ctypes.c_wchar_p),
        ("nShow", ctypes.c_int),
        ("hInstApp", ctypes.c_void_p),
        ("lpIDList", ctypes.c_void_p),
        ("lpClass", ctypes.c_wchar_p),
        ("hkeyClass", ctypes.c_void_p),
        ("dwHotKey", ctypes.c_uint32),
        ("hIconOrMonitor", ctypes.c_void_p),
        ("hProcess", ctypes.c_void_p),
    ]


def relaunch_as_admin():
    if not IS_WINDOWS:
        return False
    try:
        executable = sys.executable
        if IS_FROZEN:
            params = subprocess.list2cmdline(sys.argv[1:])
        else:
            pythonw = os.path.join(os.path.dirname(executable), "pythonw.exe")
            if os.path.exists(pythonw):
                executable = pythonw
            params = subprocess.list2cmdline([os.path.abspath(sys.argv[0])] + sys.argv[1:])
        SW_SHOWNORMAL = 1
        SEE_MASK_NOCLOSEPROCESS = 0x00000040
        info = _SHELLEXECUTEINFOW()
        info.cbSize = ctypes.sizeof(_SHELLEXECUTEINFOW)
        info.fMask = SEE_MASK_NOCLOSEPROCESS
        info.lpVerb = "runas"
        info.lpFile = executable
        info.lpParameters = params
        info.lpDirectory = BASE_DIR
        info.nShow = SW_SHOWNORMAL
        succeeded = bool(ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(info)))
        if succeeded and info.hProcess:
            ctypes.windll.kernel32.CloseHandle(info.hProcess)
        return succeeded
    except Exception:
        return False


def write_restart_script(executable, args, pid):
    script_path = os.path.join(tempfile.gettempdir(), "restart.bat")
    command = subprocess.list2cmdline([executable] + args)
    content = (
        "@echo off\r\n"
        "setlocal\r\n"
        f"set PID={pid}\r\n"
        "set COUNT=0\r\n"
        ":wait\r\n"
        'tasklist /fi "PID eq %PID%" 2>nul | find "%PID%" >nul\r\n'
        "if errorlevel 1 goto launch\r\n"
        "set /a COUNT+=1\r\n"
        "if %COUNT% geq 50 goto launch\r\n"
        "ping -n 1 -w 100 127.0.0.1 >nul\r\n"
        "goto wait\r\n"
        ":launch\r\n"
        f'start "" {command}\r\n'
        'del "%~f0"\r\n'
    )
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(content)
    return script_path


def relaunch_self():
    try:
        executable = sys.executable
        if IS_FROZEN:
            args = sys.argv[1:]
        else:
            if IS_WINDOWS:
                pythonw = os.path.join(os.path.dirname(executable), "pythonw.exe")
                if os.path.exists(pythonw):
                    executable = pythonw
            args = [os.path.abspath(sys.argv[0])] + sys.argv[1:]
        relaunch_env = dict(os.environ)
        relaunch_env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
        if IS_WINDOWS:
            script_path = write_restart_script(executable, args, os.getpid())
            subprocess.Popen(
                ["cmd.exe", "/c", script_path],
                creationflags=subprocess.CREATE_NO_WINDOW,
                cwd=BASE_DIR,
                env=relaunch_env,
            )
            return True
        subprocess.Popen([executable] + args, cwd=BASE_DIR, env=relaunch_env)
        return True
    except Exception:
        return False


def bytes_to_readable(num):
    try:
        num = float(num)
    except (TypeError, ValueError):
        return "N/A"
    step = 1024.0
    for unit in ["B", "KB", "MB", "GB", "TB", "PB"]:
        if abs(num) < step:
            return f"{num:.2f} {unit}"
        num /= step
    return f"{num:.2f} EB"


def safe(value, fallback="N/A"):
    if value is None:
        return fallback
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text if text else fallback


def format_wmi_datetime(value):
    if not value:
        return None
    try:
        text = str(value).strip()
        dt = datetime.strptime(text[:14], "%Y%m%d%H%M%S")
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def live_uptime_value(boot_epoch, include_seconds=False):
    return {"live": "uptime", "epoch": boot_epoch, "seconds": include_seconds}


def live_clock_value(epoch=None):
    if epoch is None:
        epoch = datetime.now().timestamp()
    return {"live": "clock", "epoch": epoch}


def wmi_connect(namespace=None):
    if not (IS_WINDOWS and wmi):
        return None
    try:
        return wmi.WMI(namespace=namespace) if namespace else wmi.WMI()
    except Exception:
        return None


def wmi_first(conn, class_name):
    if conn is None:
        return None
    try:
        items = getattr(conn, class_name)()
        return items[0] if items else None
    except Exception:
        return None


def wmi_all(conn, class_name):
    if conn is None:
        return []
    try:
        return list(getattr(conn, class_name)())
    except Exception:
        return []


PLACEHOLDER_WMI_VALUES = {
    "default string",
    "to be filled by o.e.m.",
    "to be filled by oem",
    "fill by oem",
    "fill by o.e.m.",
    "system serial number",
    "system version",
    "system manufacturer",
    "system product name",
    "system name",
    "system sku number",
    "system family",
    "base board manufacturer",
    "base board product name",
    "base board version",
    "base board serial number",
    "base board asset tag",
    "base board asset tag#",
    "chassis manufacturer",
    "chassis manufacture",
    "chassis version",
    "chassis serial number",
    "chassis asset tag",
    "default version",
    "default manufacturer",
    "not specified",
    "not applicable",
    "not available",
    "none",
    "empty",
    "unknown",
    "undefined",
    "invalid",
    "o.e.m.",
    "oem",
    "n/a",
    "na",
    "0123456789",
    "1234567890",
    "00000000-0000-0000-0000-000000000000",
    "ffffffff-ffff-ffff-ffff-ffffffffffff",
    "03000200-0400-0500-0006-000700080009",
}


def is_placeholder_value(text):
    return str(text).strip().lower() in PLACEHOLDER_WMI_VALUES


MEMORY_TYPE_LABELS = {20: "DDR", 21: "DDR2", 24: "DDR3", 26: "DDR4", 34: "DDR5"}

DISK_MEDIA_TYPE_LABELS = {0: "Unknown", 3: "HDD", 4: "SSD", 5: "SCM"}

DISK_BUS_TYPE_LABELS = {
    1: "SCSI", 2: "ATAPI", 3: "ATA", 4: "1394", 5: "SSA", 6: "Fibre Channel",
    7: "USB", 8: "RAID", 9: "iSCSI", 10: "SAS", 11: "SATA", 12: "SD",
    13: "MMC", 14: "Virtual", 15: "File Backed Virtual", 16: "Storage Spaces", 17: "NVMe",
}


def wmi_attr(obj, attr, fallback="N/A"):
    if obj is None:
        return fallback
    try:
        value = safe(getattr(obj, attr, None), fallback)
    except Exception:
        return fallback
    if value != fallback and is_placeholder_value(value):
        return fallback
    return value


def get_gpu_vram_registry():
    entries = []
    if not IS_WINDOWS:
        return entries
    try:
        import winreg
        base_path = r"SYSTEM\CurrentControlSet\Control\Video"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base_path) as base_key:
            index = 0
            while True:
                try:
                    guid = winreg.EnumKey(base_key, index)
                except OSError:
                    break
                index += 1
                if not guid.startswith("{"):
                    continue
                sub_index = 0
                while True:
                    sub_path = f"{base_path}\\{guid}\\{sub_index:04d}"
                    try:
                        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, sub_path) as sub_key:
                            try:
                                size_value, _ = winreg.QueryValueEx(sub_key, "HardwareInformation.qwMemorySize")
                            except OSError:
                                size_value = None
                            try:
                                desc_value, _ = winreg.QueryValueEx(sub_key, "DriverDesc")
                            except OSError:
                                desc_value = None
                    except OSError:
                        break
                    sub_index += 1
                    if isinstance(size_value, int) and size_value > 0 and desc_value:
                        entries.append((str(desc_value).strip(), int(size_value)))
    except Exception:
        pass
    return entries


def match_registry_vram(name, registry_groups):
    if not name or name == "N/A":
        return None
    key = name.strip().lower()
    bucket = registry_groups.get(key)
    if not bucket:
        return None
    return bucket.pop(0)


def normalize_vram_bytes(adapter_ram):
    if adapter_ram is None:
        return None
    try:
        value = int(adapter_ram)
    except (TypeError, ValueError):
        return None
    if value < 0:
        value += 1 << 32
    return value if value > 0 else None


def collect_gpu_details(conn=None):
    details = []
    try:
        gpus = list(wmi_all(conn or wmi_connect(), "Win32_VideoController"))
        registry_groups = {}
        for desc, size in get_gpu_vram_registry():
            key = desc.strip().lower()
            registry_groups.setdefault(key, []).append(size)
        for bucket in registry_groups.values():
            bucket.sort(reverse=True)
        for gpu in gpus:
            try:
                name = wmi_attr(gpu, "Name")
                driver = wmi_attr(gpu, "DriverVersion")
                horizontal = wmi_attr(gpu, "CurrentHorizontalResolution")
                vertical = wmi_attr(gpu, "CurrentVerticalResolution")
                refresh = wmi_attr(gpu, "CurrentRefreshRate")
                vram = normalize_vram_bytes(gpu.AdapterRAM)
                registry_vram = match_registry_vram(name, registry_groups)
                if registry_vram is not None and registry_vram > (vram or 0):
                    vram = registry_vram
                vram_text = bytes_to_readable(vram) if vram else "N/A"
                fields = (name, vram_text, driver, horizontal, vertical, refresh)
                if any(field == "N/A" for field in fields):
                    continue
                details.append({
                    "Name": name,
                    "VRAM": vram_text,
                    "Driver Version": driver,
                    "Resolution": f"{horizontal} x {vertical}",
                    "Refresh Rate": f"{refresh} Hz",
                })
            except Exception:
                continue
    except Exception:
        pass
    return details


def get_cpu_name(conn=None):
    cpu = wmi_first(conn or wmi_connect(), "Win32_Processor")
    return wmi_attr(cpu, "Name", safe(platform.processor()))


def get_motherboard_name(conn=None):
    board = wmi_first(conn or wmi_connect(), "Win32_BaseBoard")
    manufacturer = wmi_attr(board, "Manufacturer")
    product = wmi_attr(board, "Product")
    if manufacturer != "N/A" and product != "N/A":
        if manufacturer.lower() in product.lower():
            return product
        return f"{manufacturer} {product}"
    if product != "N/A":
        return product
    return manufacturer


def format_counted_names(names):
    if not names:
        return "N/A"
    counts = {}
    order = []
    for name in names:
        if name not in counts:
            counts[name] = 0
            order.append(name)
        counts[name] += 1
    parts = [f"{counts[name]}x {name}" if counts[name] > 1 else name for name in order]
    return ", ".join(parts)


def collect_ram_names(conn=None):
    names = []
    for mod in wmi_all(conn or wmi_connect(), "Win32_PhysicalMemory"):
        try:
            manufacturer = wmi_attr(mod, "Manufacturer")
            part_number = wmi_attr(mod, "PartNumber")
            parts = []
            if manufacturer != "N/A":
                parts.append(manufacturer)
            if part_number != "N/A" and part_number not in parts:
                parts.append(part_number)
            if parts:
                names.append(" ".join(parts))
        except Exception:
            continue
    return names


def get_overview():
    conn = wmi_connect()
    cpu_name = get_cpu_name(conn)
    gpu_names = [gpu["Name"] for gpu in collect_gpu_details(conn)]
    motherboard_name = get_motherboard_name(conn)
    ram_name = format_counted_names(collect_ram_names(conn))
    os_info = wmi_first(conn, "Win32_OperatingSystem")
    os_name = wmi_attr(os_info, "Caption", safe(f"{platform.system()} {platform.release()}"))
    boot_ts = psutil.boot_time()
    vm = psutil.virtual_memory()
    total_cpu, _ = get_cpu_usage_snapshot()
    hardware = {
        "Motherboard": motherboard_name,
        "Processor": cpu_name,
        "Graphics Card": ", ".join(gpu_names) if gpu_names else "N/A",
        "Memory": ram_name,
    }
    return {
        "System": {
            "Operating System": os_name,
            "Hostname": safe(socket.gethostname()),
            "Architecture": safe(platform.machine()),
            "Uptime": live_uptime_value(boot_ts, include_seconds=True),
        },
        "Hardware": hardware,
        "Usage": {
            "Processor Usage": f"{total_cpu:.1f}%",
            "Graphics Card Usage": get_overview_gpu_usage(),
            "Memory Usage": f"{vm.percent}%",
            "Processes": safe(len(psutil.pids())),
        },
    }


def get_os_info():
    uname = platform.uname()
    boot_ts = psutil.boot_time()
    boot_time = datetime.fromtimestamp(boot_ts).strftime("%Y-%m-%d %H:%M:%S")
    general = {
        "OS Name": safe(uname.system),
        "Version": safe(uname.version),
        "Release": safe(uname.release),
        "Build": safe(uname.version),
        "Architecture": safe(platform.machine()),
    }
    system = {
        "Hostname": safe(socket.gethostname()),
        "Current User": safe(os.environ.get("USERNAME")),
        "Boot Time": boot_time,
        "Uptime": live_uptime_value(boot_ts, include_seconds=True),
    }
    info = wmi_first(wmi_connect(), "Win32_OperatingSystem")
    if info is not None:
        general["OS Name"] = wmi_attr(info, "Caption", general["OS Name"])
        general["Build"] = wmi_attr(info, "BuildNumber", general["Build"])
        try:
            general["Install Date"] = safe(format_wmi_datetime(info.InstallDate))
        except Exception:
            pass
        system["System Drive"] = wmi_attr(info, "SystemDrive")
        system["Serial Number"] = wmi_attr(info, "SerialNumber")
    return {"General": general, "System": system}


def get_motherboard():
    general = {
        "Manufacturer": "N/A",
        "Product": "N/A",
        "Version": "N/A",
        "Serial Number": "N/A",
    }
    bios = {
        "BIOS Vendor": "N/A",
        "BIOS Version": "N/A",
        "BIOS Release Date": "N/A",
    }
    conn = wmi_connect()
    board = wmi_first(conn, "Win32_BaseBoard")
    general["Manufacturer"] = wmi_attr(board, "Manufacturer")
    general["Product"] = wmi_attr(board, "Product")
    general["Version"] = wmi_attr(board, "Version")
    general["Serial Number"] = wmi_attr(board, "SerialNumber")
    bios_info = wmi_first(conn, "Win32_BIOS")
    bios["BIOS Vendor"] = wmi_attr(bios_info, "Manufacturer")
    bios["BIOS Version"] = wmi_attr(bios_info, "SMBIOSBIOSVersion")
    if bios_info is not None:
        try:
            bios["BIOS Release Date"] = safe(format_wmi_datetime(bios_info.ReleaseDate))
        except Exception:
            pass
    return {"General": general, "BIOS": bios}


def get_cpu_cache_sizes(conn, cpu):
    l1_bytes = l2_bytes = l3_bytes = 0
    try:
        for cache in wmi_all(conn, "Win32_CacheMemory"):
            level = int(getattr(cache, "Level", 0) or 0)
            size = getattr(cache, "MaxCacheSize", None) or getattr(cache, "InstalledSize", None)
            if not size:
                continue
            size_bytes = int(size) * 1024
            if level == 3:
                l1_bytes += size_bytes
            elif level == 4:
                l2_bytes += size_bytes
            elif level == 5:
                l3_bytes += size_bytes
    except Exception:
        pass
    if not l2_bytes and cpu is not None:
        try:
            l2_bytes = int(cpu.L2CacheSize) * 1024 if cpu.L2CacheSize else 0
        except Exception:
            pass
    if not l3_bytes and cpu is not None:
        try:
            l3_bytes = int(cpu.L3CacheSize) * 1024 if cpu.L3CacheSize else 0
        except Exception:
            pass
    return l1_bytes, l2_bytes, l3_bytes


def get_processor():
    conn = wmi_connect()
    cpu = wmi_first(conn, "Win32_Processor")
    manufacturer = wmi_attr(cpu, "Manufacturer")
    socket_name = wmi_attr(cpu, "SocketDesignation")
    threads = wmi_attr(cpu, "ThreadCount")
    if threads == "N/A":
        threads = safe(psutil.cpu_count(logical=True))
    l1_bytes, l2_bytes, l3_bytes = get_cpu_cache_sizes(conn, cpu)
    general = {
        "Name": get_cpu_name(conn),
        "Manufacturer": manufacturer,
        "Architecture": safe(platform.machine()),
        "Socket": socket_name,
        "Physical Cores": safe(psutil.cpu_count(logical=False)),
        "Logical Cores": safe(psutil.cpu_count(logical=True)),
        "Threads": threads,
        "L1 Cache": bytes_to_readable(l1_bytes) if l1_bytes else "N/A",
        "L2 Cache": bytes_to_readable(l2_bytes) if l2_bytes else "N/A",
        "L3 Cache": bytes_to_readable(l3_bytes) if l3_bytes else "N/A",
    }
    total_cpu, per_core = get_cpu_usage_snapshot()
    usage = {"Total Usage": f"{total_cpu:.1f}%"}
    cores = {}
    for idx, core_usage in enumerate(per_core):
        cores[f"Core {idx + 1}"] = f"{core_usage:.1f}%"
    return {"General": general, "Usage": usage, "Core Usage": cores}


def get_graphics():
    groups = {}
    collected = collect_gpu_details()
    multiple = len(collected) > 1
    for idx, entry in enumerate(collected):
        label = f"GPU {idx + 1}" if multiple else "GPU"
        groups[label] = entry
    if not groups:
        groups["GPU"] = {"Name": "N/A"}
    return groups


def get_memory():
    vm = psutil.virtual_memory()
    sm = psutil.swap_memory()
    general = {
        "Total": bytes_to_readable(vm.total),
        "Used": bytes_to_readable(vm.used),
        "Available": bytes_to_readable(vm.available),
        "Usage": f"{vm.percent}%",
        "Swap Total": bytes_to_readable(sm.total),
        "Swap Used": bytes_to_readable(sm.used),
    }
    groups = {"General": general}

    def resolve_memory_type(mod):
        label = MEMORY_TYPE_LABELS.get(getattr(mod, "SMBIOSMemoryType", None))
        if label:
            return label
        label = MEMORY_TYPE_LABELS.get(getattr(mod, "MemoryType", None))
        return label or "Unknown"

    for idx, mod in enumerate(wmi_all(wmi_connect(), "Win32_PhysicalMemory")):
        try:
            configured_speed = getattr(mod, "ConfiguredClockSpeed", None)
            speed = configured_speed if configured_speed else getattr(mod, "Speed", None)
            groups[f"Module {idx + 1}"] = {
                "Capacity": bytes_to_readable(int(mod.Capacity)) if mod.Capacity else "N/A",
                "Speed": f"{safe(speed)} MHz",
                "Type": resolve_memory_type(mod),
                "Manufacturer": wmi_attr(mod, "Manufacturer"),
                "Part Number": wmi_attr(mod, "PartNumber"),
            }
        except Exception:
            continue
    return groups


def get_disk_media_types():
    media_types = {}
    bus_types = {}
    try:
        storage = wmi_connect(namespace="root\\Microsoft\\Windows\\Storage")
        for disk in wmi_all(storage, "MSFT_PhysicalDisk"):
            device_id = str(disk.DeviceId)
            media_types[device_id] = DISK_MEDIA_TYPE_LABELS.get(disk.MediaType, "Unknown")
            bus_label = DISK_BUS_TYPE_LABELS.get(getattr(disk, "BusType", None))
            if bus_label:
                bus_types[device_id] = bus_label
    except Exception:
        pass
    return media_types, bus_types


def get_storage():
    groups = {}
    try:
        partitions = psutil.disk_partitions(all=False)
    except Exception:
        partitions = []

    drives = {}
    drive_order = []
    for part in partitions:
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except Exception:
            continue
        device_name = part.device.rstrip("\\")
        key = device_name.rstrip(":").upper()
        label = f"Drive {device_name}"
        drives[key] = {
            "label": label,
            "disk": {},
            "partition": {
                "Filesystem": safe(part.fstype),
                "Total": bytes_to_readable(usage.total),
                "Used": bytes_to_readable(usage.used),
                "Free": bytes_to_readable(usage.free),
                "Usage": f"{usage.percent}%",
            },
        }
        drive_order.append(key)

    unmatched = []
    media_types, bus_types = get_disk_media_types()
    unmatched_index = 1
    for disk in wmi_all(wmi_connect(), "Win32_DiskDrive"):
        try:
            size = disk.Size
            disk_index = str(disk.Index)
            disk_details = {
                "Disk Model": safe(disk.Model),
                "Disk Type": media_types.get(disk_index, "Unknown"),
                "Interface": bus_types.get(disk_index) or safe(disk.InterfaceType),
                "Disk Size": bytes_to_readable(int(size)) if size else "N/A",
                "Health Status": safe(disk.Status),
                "Serial Number": safe(disk.SerialNumber),
            }
        except Exception:
            continue
        matched = False
        try:
            for partition in disk.associators("Win32_DiskDriveToDiskPartition"):
                for logical in partition.associators("Win32_LogicalDiskToPartition"):
                    logical_key = safe(logical.DeviceID).rstrip(":").upper()
                    if logical_key in drives:
                        drives[logical_key]["disk"] = disk_details
                        matched = True
        except Exception:
            pass
        if not matched:
            unmatched.append((f"Disk {unmatched_index} ({safe(disk.Model)})", disk_details))
            unmatched_index += 1

    for key in drive_order:
        entry = drives[key]
        merged = dict(entry["disk"])
        merged.update(entry["partition"])
        groups[entry["label"]] = merged
    for label, details in unmatched:
        groups[label] = details

    return groups


_nvidia_smi_available = None
_nvidia_smi_lock = threading.Lock()
NVIDIA_SMI_CACHE_SECONDS = 2.0
_nvidia_smi_cache = {
    "temperature.gpu": {"timestamp": 0.0, "data": {}},
    "utilization.gpu": {"timestamp": 0.0, "data": {}},
}


def _query_nvidia_smi(field):
    global _nvidia_smi_available
    values = {}
    try:
        run_kwargs = {"capture_output": True, "text": True, "timeout": 3}
        if IS_WINDOWS:
            run_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        result = subprocess.run(
            ["nvidia-smi", f"--query-gpu=name,{field}", "--format=csv,noheader,nounits"],
            **run_kwargs,
        )
        _nvidia_smi_available = True
        if result.returncode == 0 and result.stdout.strip():
            for line in result.stdout.strip().splitlines():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 2:
                    values[parts[0]] = parts[1]
    except FileNotFoundError:
        _nvidia_smi_available = False
    except Exception:
        pass
    return values


def _cached_nvidia_smi(field):
    if _nvidia_smi_available is False:
        return {}
    now = time.monotonic()
    with _nvidia_smi_lock:
        cache = _nvidia_smi_cache[field]
        if now - cache["timestamp"] < NVIDIA_SMI_CACHE_SECONDS:
            return dict(cache["data"])
        data = _query_nvidia_smi(field)
        cache["timestamp"] = now
        cache["data"] = data
        return dict(data)


def get_nvidia_gpu_temps():
    return {name: f"{value} °C" for name, value in _cached_nvidia_smi("temperature.gpu").items()}


def get_nvidia_gpu_usage():
    return _cached_nvidia_smi("utilization.gpu")


def get_overview_gpu_usage():
    usage = get_nvidia_gpu_usage()
    values = []
    for raw in usage.values():
        try:
            values.append(float(raw))
        except (TypeError, ValueError):
            continue
    if not values:
        return "N/A"
    return f"{sum(values) / len(values):.1f}%"


def get_temperatures():
    cpu_group = {}
    other_group = {}
    conn = wmi_connect()
    cpu_name = get_cpu_name(conn)
    zones = wmi_all(wmi_connect(namespace="root\\wmi"), "MSAcpi_ThermalZoneTemperature")
    for idx, zone in enumerate(zones):
        try:
            kelvin = zone.CurrentTemperature / 10.0
            celsius = kelvin - 273.15
            label = f"{cpu_name} (Zone {idx + 1})" if len(zones) > 1 else cpu_name
            cpu_group[label] = f"{celsius:.1f} °C"
        except Exception:
            continue
    gpu_group = get_nvidia_gpu_temps()
    if not gpu_group:
        for gpu in collect_gpu_details(conn):
            gpu_group[gpu["Name"]] = "N/A"
    if hasattr(psutil, "sensors_temperatures"):
        try:
            temps = psutil.sensors_temperatures()
            for name, entries in temps.items():
                for idx, entry in enumerate(entries):
                    label = safe(entry.label) if entry.label else f"{name} {idx + 1}"
                    other_group[label] = f"{entry.current:.1f} °C"
        except Exception:
            pass
    groups = {}
    if cpu_group:
        groups["CPU"] = cpu_group
    if gpu_group:
        groups["GPU"] = gpu_group
    if other_group:
        groups["Other Sensors"] = other_group
    if not groups:
        groups["Status"] = {"Sensors": "No temperature sensors detected"}
    return groups


def get_machine_guid():
    if not IS_WINDOWS:
        return "N/A"
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography")
        value, _ = winreg.QueryValueEx(key, "MachineGuid")
        return safe(value)
    except Exception:
        return "N/A"


def get_volume_serial(drive="C:\\"):
    if not IS_WINDOWS:
        return "N/A"
    try:
        serial = ctypes.c_uint32(0)
        max_component = ctypes.c_uint32(0)
        flags = ctypes.c_uint32(0)
        ok = ctypes.windll.kernel32.GetVolumeInformationW(
            ctypes.c_wchar_p(drive),
            None,
            0,
            ctypes.byref(serial),
            ctypes.byref(max_component),
            ctypes.byref(flags),
            None,
            0,
        )
        if not ok:
            return "N/A"
        value = serial.value
        return f"{(value >> 16) & 0xFFFF:04X}-{value & 0xFFFF:04X}"
    except Exception:
        return "N/A"


def get_network():
    try:
        addrs = psutil.net_if_addrs()
    except Exception:
        addrs = {}
    try:
        stats = psutil.net_if_stats()
    except Exception:
        stats = {}
    try:
        counters = psutil.net_io_counters(pernic=True)
    except Exception:
        counters = {}
    entries = []
    for iface, iface_addrs in addrs.items():
        ipv4 = "N/A"
        mac = "N/A"
        for entry in iface_addrs:
            family = getattr(entry, "family", None)
            if family == socket.AF_INET:
                ipv4 = entry.address
            is_link = family == psutil.AF_LINK or str(family).endswith("AF_LINK")
            if is_link and entry.address and entry.address not in ("00:00:00:00:00:00", ""):
                mac = entry.address.upper()
        stat = stats.get(iface)
        counter = counters.get(iface)
        is_up = stat is not None and stat.isup
        details = {
            "IPv4 Address": safe(ipv4),
            "MAC Address": safe(mac),
            "Status": "Up" if is_up else "Down",
        }
        if stat is not None:
            details["Link Speed"] = f"{stat.speed} Mbps" if stat.speed else "N/A"
        if counter is not None:
            details["Sent"] = bytes_to_readable(counter.bytes_sent)
            details["Received"] = bytes_to_readable(counter.bytes_recv)
        entries.append((iface, details, is_up))
    entries.sort(key=lambda item: not item[2])
    groups = {iface: details for iface, details, _ in entries}
    if not groups:
        groups["Status"] = {"Adapters": "No network adapters detected"}
    return groups


def get_hardware_ids():
    mac = ":".join(["{:02x}".format((uuid.getnode() >> ele) & 0xff) for ele in range(40, -1, -8)]).upper()
    groups = {"General": {"MAC Address": mac, "Machine GUID": get_machine_guid()}}
    conn = wmi_connect()
    cpu = wmi_first(conn, "Win32_Processor")
    groups["Processor"] = {"Processor ID": wmi_attr(cpu, "ProcessorId")}
    board = wmi_first(conn, "Win32_BaseBoard")
    groups["Motherboard"] = {"Motherboard Serial": wmi_attr(board, "SerialNumber")}
    bios = wmi_first(conn, "Win32_BIOS")
    groups["BIOS"] = {"BIOS Serial": wmi_attr(bios, "SerialNumber")}
    product = wmi_first(conn, "Win32_ComputerSystemProduct")
    os_info = wmi_first(conn, "Win32_OperatingSystem")
    groups["System"] = {
        "System UUID": wmi_attr(product, "UUID"),
        "Windows Product ID": wmi_attr(os_info, "SerialNumber"),
    }
    try:
        disk_group = {}
        for idx, disk in enumerate(wmi_all(conn, "Win32_DiskDrive")):
            disk_group[f"Disk {idx + 1}"] = safe(disk.SerialNumber)
        if disk_group:
            groups["Disks"] = disk_group
    except Exception:
        pass
    groups["System Drive"] = {"Volume Serial": get_volume_serial()}
    return groups


def get_miscellaneous():
    general = {
        "App Name": APP_NAME,
        "App Version": APP_VERSION,
        "Developed by": f"{APP_AUTHOR} ({APP_AUTHOR_HANDLE})",
        "Dev's Website": APP_AUTHOR_URL,
    }
    runtime = {
        "Processes Running": safe(len(psutil.pids())),
        "Running as Administrator": "Yes" if is_admin() else "No",
        "Current Time": live_clock_value(),
    }
    return {"General": general, "Runtime": runtime}


def parse_version_tuple(value):
    if not value:
        return None
    match = re.search(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?", value)
    if not match:
        return None
    return tuple(int(part) if part else 0 for part in match.groups())


STRICT_TAG_VERSION_RE = re.compile(r"^[vV](\d+)\.(\d+)\.(\d+)$")


def parse_strict_tag_version(name):
    if not name:
        return None
    match = STRICT_TAG_VERSION_RE.match(name.strip())
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


WHATS_NEW_HEADING_RE = re.compile(r"^#{1,6}[^\n]*what.?s?\s+changed[^\n]*$", re.IGNORECASE | re.MULTILINE)


def extract_whats_new(body):
    if not body:
        return []
    heading_match = WHATS_NEW_HEADING_RE.search(body)
    if not heading_match:
        return []
    items = []
    for line in body[heading_match.end():].splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            break
        if stripped.lower().startswith("**full changelog"):
            break
        if stripped.startswith("- ") or stripped.startswith("* ") or stripped in ("-", "*"):
            text = stripped[1:].strip()
            if text:
                items.append(text)
        elif items:
            break
    return items


def fetch_latest_release():
    request = urllib.request.Request(
        UPDATE_RELEASES_API_URL,
        headers={"User-Agent": f"{APP_NAME}/{APP_VERSION}", "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(request, timeout=6) as response:
        data = json.loads(response.read().decode("utf-8"))
    if not isinstance(data, list) or not data:
        return None
    best_release = None
    best_tuple = None
    for release in data:
        if not isinstance(release, dict) or release.get("draft"):
            continue
        version_tuple = parse_strict_tag_version(release.get("tag_name"))
        if version_tuple is None:
            continue
        if best_tuple is None or version_tuple > best_tuple:
            best_tuple = version_tuple
            best_release = release
    return best_release


def find_exe_asset(release):
    if not release:
        return None
    for asset in release.get("assets") or []:
        name = asset.get("name") or ""
        if name.lower().endswith(".exe"):
            return {
                "name": name,
                "url": asset.get("browser_download_url"),
                "size": asset.get("size") or 0,
            }
    return None


PROVIDERS = {
    "overview": get_overview,
    "os": get_os_info,
    "motherboard": get_motherboard,
    "processor": get_processor,
    "graphics": get_graphics,
    "memory": get_memory,
    "storage": get_storage,
    "network": get_network,
    "temperatures": get_temperatures,
    "hwid": get_hardware_ids,
    "misc": get_miscellaneous,
}


class DetectionWorker(QObject):
    resultReady = pyqtSignal(str, str)
    resultFailed = pyqtSignal(str, str)

    def __init__(self, category):
        super().__init__()
        self.category = category
        self._com_ready = False

    def _ensure_com(self):
        if not IS_WINDOWS or self._com_ready:
            return
        try:
            import pythoncom
            pythoncom.CoInitialize()
            self._com_ready = True
        except Exception:
            pass

    @pyqtSlot()
    def process(self):
        self._ensure_com()
        func = PROVIDERS.get(self.category)
        try:
            result = func() if func else {}
            self.resultReady.emit(self.category, json.dumps(result))
        except Exception as exc:
            self.resultFailed.emit(self.category, str(exc))

    @pyqtSlot()
    def teardown(self):
        if not self._com_ready:
            return
        try:
            import pythoncom
            pythoncom.CoUninitialize()
        except Exception:
            pass
        self._com_ready = False


class UpdateCheckWorker(QThread):
    finishedCheck = pyqtSignal(str)

    def run(self):
        current = APP_VERSION
        try:
            release = fetch_latest_release()
        except Exception as exc:
            self.finishedCheck.emit(json.dumps({
                "current": current,
                "latest": None,
                "available": False,
                "error": str(exc),
                "url": UPDATE_TAGS_PAGE_URL,
                "download_url": None,
                "asset_name": None,
                "asset_size": 0,
            }))
            return
        if not release:
            self.finishedCheck.emit(json.dumps({
                "current": current,
                "latest": None,
                "available": False,
                "error": "No releases found",
                "url": UPDATE_TAGS_PAGE_URL,
                "download_url": None,
                "asset_name": None,
                "asset_size": 0,
            }))
            return
        latest = (release.get("tag_name") or "").strip().lstrip("vV")
        current_tuple = parse_version_tuple(current)
        latest_tuple = parse_version_tuple(latest)
        if current_tuple is not None and latest_tuple is not None:
            available = latest_tuple > current_tuple
        else:
            available = latest.strip().lstrip("vV") != current.strip().lstrip("vV")
        asset = find_exe_asset(release)
        self.finishedCheck.emit(json.dumps({
            "current": current,
            "latest": latest,
            "available": available,
            "error": None,
            "url": release.get("html_url") or UPDATE_TAGS_PAGE_URL,
            "download_url": asset["url"] if asset else None,
            "asset_name": asset["name"] if asset else None,
            "asset_size": asset["size"] if asset else 0,
            "whats_new": extract_whats_new(release.get("body")) if available else [],
        }))


class UpdateDownloadWorker(QThread):
    progress = pyqtSignal(int, int)
    finishedDownload = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, url, target_path):
        super().__init__()
        self.url = url
        self.target_path = target_path

    def run(self):
        try:
            request = urllib.request.Request(
                self.url,
                headers={"User-Agent": f"{APP_NAME}/{APP_VERSION}"},
            )
            with urllib.request.urlopen(request, timeout=15) as response:
                total = int(response.headers.get("Content-Length") or 0)
                received = 0
                with open(self.target_path, "wb") as out_file:
                    while True:
                        chunk = response.read(262144)
                        if not chunk:
                            break
                        out_file.write(chunk)
                        received += len(chunk)
                        self.progress.emit(received, total)
            self.finishedDownload.emit(self.target_path)
        except Exception as exc:
            try:
                if os.path.exists(self.target_path):
                    os.remove(self.target_path)
            except Exception:
                pass
            self.failed.emit(str(exc))


def write_update_script(target_path, source_path, pid):
    script_path = os.path.join(SETTINGS_DIR, "sys_io_update.bat")
    old_path = target_path + ".old"
    content = (
        "@echo off\r\n"
        ":wait\r\n"
        f'tasklist /FI "PID eq {pid}" | find "{pid}" >nul\r\n'
        "if not errorlevel 1 (\r\n"
        "  timeout /t 1 /nobreak >nul\r\n"
        "  goto wait\r\n"
        ")\r\n"
        f'if exist "{old_path}" del /f /q "{old_path}" >nul 2>&1\r\n'
        ":swapout\r\n"
        f'move /y "{target_path}" "{old_path}" >nul 2>&1\r\n'
        "if errorlevel 1 (\r\n"
        "  timeout /t 1 /nobreak >nul\r\n"
        "  goto swapout\r\n"
        ")\r\n"
        ":swapin\r\n"
        f'move /y "{source_path}" "{target_path}" >nul 2>&1\r\n'
        "if errorlevel 1 (\r\n"
        "  timeout /t 1 /nobreak >nul\r\n"
        "  goto swapin\r\n"
        ")\r\n"
        f'del /f /q "{old_path}" >nul 2>&1\r\n'
        f'start "" "{target_path}"\r\n'
        'del "%~f0"\r\n'
    )
    os.makedirs(SETTINGS_DIR, exist_ok=True)
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(content)
    return script_path


class Bridge(QObject):
    categoryData = pyqtSignal(str, str)
    categoryError = pyqtSignal(str, str)
    restartRequired = pyqtSignal()
    updateCheckResult = pyqtSignal(str)
    updateDownloadProgress = pyqtSignal(int, int)
    updateDownloadReady = pyqtSignal()
    updateDownloadError = pyqtSignal(str)
    windowMaximizedChanged = pyqtSignal(bool)
    windowMinimizedChanged = pyqtSignal(bool)
    settingsExported = pyqtSignal(bool, str)
    settingsImported = pyqtSignal(bool, str)

    EDGE_FLAGS = {
        "top": Qt.Edge.TopEdge,
        "bottom": Qt.Edge.BottomEdge,
        "left": Qt.Edge.LeftEdge,
        "right": Qt.Edge.RightEdge,
    }

    def __init__(self, window):
        super().__init__()
        self.window = window
        self.update_worker = None
        self.download_worker = None
        self._category_threads = {}
        self._category_workers = {}
        self._category_busy = set()
        self._category_pending = set()
        self._restart_pending = False
        self._start_category_workers()

    def _start_category_workers(self):
        for category in PROVIDERS:
            thread = QThread(self)
            worker = DetectionWorker(category)
            worker.moveToThread(thread)
            worker.resultReady.connect(self._onFinished)
            worker.resultFailed.connect(self._onFailed)
            thread.start()
            self._category_threads[category] = thread
            self._category_workers[category] = worker

    def shutdownCategoryWorkers(self):
        for category, worker in self._category_workers.items():
            QMetaObject.invokeMethod(worker, "teardown", Qt.ConnectionType.BlockingQueuedConnection)
        for thread in self._category_threads.values():
            thread.quit()
            thread.wait(2000)

    @pyqtSlot(str)
    def requestCategory(self, category):
        worker = self._category_workers.get(category)
        if worker is None:
            return
        if category in self._category_busy:
            self._category_pending.add(category)
            return
        self._category_busy.add(category)
        QMetaObject.invokeMethod(worker, "process", Qt.ConnectionType.QueuedConnection)

    def _onFinished(self, category, payload):
        self._category_busy.discard(category)
        self.categoryData.emit(category, payload)
        if category in self._category_pending:
            self._category_pending.discard(category)
            self.requestCategory(category)

    def _onFailed(self, category, message):
        self._category_busy.discard(category)
        self.categoryError.emit(category, message)
        if category in self._category_pending:
            self._category_pending.discard(category)
            self.requestCategory(category)

    @pyqtSlot()
    def checkForUpdates(self):
        if self.update_worker and self.update_worker.isRunning():
            return
        worker = UpdateCheckWorker()
        worker.finishedCheck.connect(self._onUpdateCheckFinished)
        worker.finished.connect(lambda: setattr(self, "update_worker", None))
        self.update_worker = worker
        worker.start()

    def _onUpdateCheckFinished(self, payload):
        self.updateCheckResult.emit(payload)

    @pyqtSlot(str, str)
    def downloadUpdate(self, url, asset_name):
        if not url:
            self.updateDownloadError.emit("No downloadable file found for this release.")
            return
        if self.download_worker and self.download_worker.isRunning():
            return
        try:
            os.makedirs(SETTINGS_DIR, exist_ok=True)
        except Exception:
            pass
        download_path = os.path.join(SETTINGS_DIR, asset_name or "sys_io_update.exe")
        worker = UpdateDownloadWorker(url, download_path)
        worker.progress.connect(self._onDownloadProgress)
        worker.finishedDownload.connect(self._onDownloadFinished)
        worker.failed.connect(self._onDownloadFailed)
        worker.finished.connect(lambda: setattr(self, "download_worker", None))
        self.download_worker = worker
        worker.start()

    def _onDownloadProgress(self, received, total):
        self.updateDownloadProgress.emit(received, total)

    def _onDownloadFinished(self, path):
        if not (IS_WINDOWS and IS_FROZEN):
            self.updateDownloadError.emit("Automatic install is only available in the packaged Windows build.")
            return
        try:
            script_path = write_update_script(sys.executable, path, os.getpid())
            relaunch_env = dict(os.environ)
            relaunch_env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
            subprocess.Popen(
                ["cmd.exe", "/c", script_path],
                creationflags=subprocess.CREATE_NO_WINDOW,
                cwd=BASE_DIR,
                env=relaunch_env,
            )
        except Exception as exc:
            self.updateDownloadError.emit(str(exc))
            return
        self.updateDownloadReady.emit()
        QApplication.instance().quit()

    def _onDownloadFailed(self, message):
        self.updateDownloadError.emit(message)

    @pyqtSlot(str)
    def openExternalUrl(self, url):
        try:
            QDesktopServices.openUrl(QUrl(url))
        except Exception:
            pass

    @pyqtSlot(str)
    def updateSetting(self, payload):
        try:
            partial = json.loads(payload)
        except Exception:
            return
        if not isinstance(partial, dict):
            return
        SETTINGS.update(partial)
        save_settings(SETTINGS)
        if any(key in RESTART_REQUIRED_KEYS for key in partial):
            self.restartRequired.emit()

    @pyqtSlot()
    def exportSettings(self):
        path, _ = QFileDialog.getSaveFileName(
            self.window, "Export Settings", "sys_io_settings.json", "JSON Files (*.json)"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(SETTINGS, f, indent=2)
            self.settingsExported.emit(True, path)
        except Exception as exc:
            self.settingsExported.emit(False, str(exc))

    @pyqtSlot()
    def importSettings(self):
        path, _ = QFileDialog.getOpenFileName(
            self.window, "Import Settings", "", "JSON Files (*.json)"
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception as exc:
            self.settingsImported.emit(False, str(exc))
            return
        filtered = validate_imported_settings(raw)
        if not filtered:
            self.settingsImported.emit(False, "No valid settings found in file.")
            return
        changed_restart_keys = any(
            key in RESTART_REQUIRED_KEYS and SETTINGS.get(key) != value
            for key, value in filtered.items()
        )
        SETTINGS.update(filtered)
        save_settings(SETTINGS)
        self.settingsImported.emit(True, json.dumps(SETTINGS))
        if changed_restart_keys:
            self.restartRequired.emit()

    @pyqtSlot()
    def startMove(self):
        handle = self.window.windowHandle()
        if handle:
            handle.startSystemMove()

    @pyqtSlot(str)
    def startResize(self, edge):
        handle = self.window.windowHandle()
        if not handle:
            return
        combined = None
        for part in edge.split("-"):
            flag = self.EDGE_FLAGS.get(part)
            if flag is None:
                continue
            combined = flag if combined is None else combined | flag
        if combined is not None:
            handle.startSystemResize(combined)

    @pyqtSlot()
    def minimizeWindow(self):
        self.window.showMinimized()

    @pyqtSlot()
    def toggleMaximize(self):
        if getattr(self.window, "frameless", False):
            self.window.animatedToggleMaximize()
        elif self.window.isMaximized():
            self.window.showNormal()
        else:
            self.window.showMaximized()

    @pyqtSlot()
    def closeWindow(self):
        self.window.close()

    @pyqtSlot()
    def restartApp(self):
        relaunch_self()
        QApplication.instance().quit()

    @pyqtSlot()
    def deferRestart(self):
        self._restart_pending = True

    @pyqtSlot(str)
    def copyToClipboard(self, text):
        QApplication.clipboard().setText(text)


HTML = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Comfortaa:wght@300..700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/css/all.min.css">
<style>
:root {
  --bg: #070707;
  --bg-elevated: #0a0a0a;
  --bg-card: #111111;
  --border: #1c1c1c;
  --border-strong: #2a2a2a;
  --fg: #cccccc;
  --fg-dim: #7a7a7a;
  --accent: #ffffff;
  --accent-contrast: #0a0a0a;
  --accent-soft: rgba(255, 255, 255, 0.12);
  --scrollbar: #2a2a2a;
  --skeleton-a: #111111;
  --skeleton-b: #171717;
  --shadow: rgba(0, 0, 0, 0.35);
  --radius: 10px;
}
:root[data-theme="light"] {
  --bg: #f2f2f4;
  --bg-elevated: #ffffff;
  --bg-card: #ffffff;
  --border: #e2e2e6;
  --border-strong: #d2d2d8;
  --fg: #1c1c1e;
  --fg-dim: #6c6c72;
  --accent: #1c1c1e;
  --accent-contrast: #ffffff;
  --accent-soft: rgba(28, 28, 30, 0.08);
  --scrollbar: #cfcfd4;
  --skeleton-a: #ececf0;
  --skeleton-b: #e0e0e6;
  --shadow: rgba(0, 0, 0, 0.12);
}
:root[data-theme="halloween"] {
  --bg: #120b18;
  --bg-elevated: #180f20;
  --bg-card: #1f1428;
  --border: #30203c;
  --border-strong: #46304f;
  --fg: #ede2d6;
  --fg-dim: #9686a3;
  --accent: #ff9a3c;
  --accent-contrast: #1a0f12;
  --accent-soft: rgba(255, 154, 60, 0.16);
  --scrollbar: #46304f;
  --skeleton-a: #1f1428;
  --skeleton-b: #2b1c38;
  --shadow: rgba(0, 0, 0, 0.45);
}
:root[data-theme="halloween"] .boot-logo-wrap,
:root[data-theme="halloween"] #sidebar-footer,
:root[data-theme="halloween"] #titlebar {
  position: relative;
}
:root[data-theme="halloween"] .boot-logo-wrap::before {
  content: "🕸️";
  position: absolute;
  top: -14px;
  left: -26px;
  font-size: 20px;
  opacity: 0.8;
}
:root[data-theme="halloween"] .boot-logo-wrap::after {
  content: "🦇";
  position: absolute;
  bottom: -10px;
  right: -28px;
  font-size: 20px;
  opacity: 0.85;
}
:root[data-theme="halloween"] #titlebar::after {
  content: "🎃";
  position: absolute;
  right: 150px;
  top: 50%;
  transform: translateY(-50%);
  font-size: 16px;
  opacity: 0.8;
  pointer-events: none;
}
:root[data-theme="halloween"] #sidebar-footer::after {
  content: "🎃";
  position: absolute;
  right: 16px;
  bottom: 16px;
  font-size: 18px;
  opacity: 0.85;
}
:root[data-theme="halloween"] #content-header {
  position: relative;
  overflow: hidden;
}
:root[data-theme="halloween"] #content-header::before {
  content: "🌙";
  position: absolute;
  right: 54px;
  top: 50%;
  transform: translateY(-50%);
  font-size: 26px;
  opacity: 0.18;
  pointer-events: none;
}
:root[data-theme="halloween"] .card:hover {
  border-color: var(--accent);
  box-shadow: 0 10px 22px var(--shadow), 0 0 0 1px rgba(255, 154, 60, 0.18);
}
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body { height: 100%; }
button, input { font-family: inherit; }
body {
  background: var(--bg);
  color: var(--fg);
  font-family: "Comfortaa", "Segoe UI", system-ui, -apple-system, sans-serif;
  overflow: hidden;
  user-select: none;
  transition: background-color 0.25s cubic-bezier(0.4, 0, 0.2, 1), color 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}
body:not(.native-window) { background: transparent; }
#boot-screen {
  position: fixed;
  inset: 0;
  z-index: 50;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: var(--bg);
  transition: opacity 0.45s cubic-bezier(0.4, 0, 0.2, 1), transform 0.45s cubic-bezier(0.4, 0, 0.2, 1);
}
#boot-screen.boot-hide {
  opacity: 0;
  transform: scale(1.03);
  pointer-events: none;
}
.boot-logo-wrap {
  width: 84px;
  height: 84px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 22px;
}
#boot-logo { max-width: 100%; max-height: 100%; }
#boot-logo-fallback {
  display: none;
  width: 84px;
  height: 84px;
  border-radius: 20px;
  background: var(--accent-soft);
  border: 1px solid var(--border);
  color: var(--accent);
  font-size: 34px;
  font-weight: 700;
  align-items: center;
  justify-content: center;
}
.boot-title { font-size: 22px; font-weight: 700; letter-spacing: 0.5px; color: var(--fg); }
.boot-subtitle { font-size: 12.5px; color: var(--fg-dim); margin-top: 6px; letter-spacing: 0.3px; }
.boot-progress {
  width: 220px;
  height: 4px;
  background: var(--border);
  border-radius: 2px;
  overflow: hidden;
  margin-top: 26px;
}
.boot-progress-bar {
  width: 40%;
  height: 100%;
  background: linear-gradient(90deg, transparent, var(--accent), transparent);
  animation: boot-sweep 1.2s ease-in-out infinite;
}
@keyframes boot-sweep {
  0% { transform: translateX(-120%); }
  100% { transform: translateX(380%); }
}
#boot-status { margin-top: 14px; font-size: 11.5px; color: var(--fg-dim); letter-spacing: 0.3px; }
#app {
  position: fixed;
  inset: 0;
  display: flex;
  flex-direction: column;
  opacity: 0;
  pointer-events: none;
  background: var(--bg);
  transition: opacity 0.5s cubic-bezier(0.4, 0, 0.2, 1);
}
#app.visible { opacity: 1; pointer-events: auto; }
body.native-window #titlebar { display: none; }
body.native-window .resize-grip { display: none; }
body:not(.native-window) #app,
body:not(.native-window) #boot-screen {
  border-radius: 17px;
  overflow: hidden;
  transition: border-radius 0.26s cubic-bezier(0.4, 0, 0.2, 1);
}
body.window-maximized #app,
body.window-maximized #boot-screen {
  border-radius: 0;
}
@keyframes app-minimize {
  from { opacity: 1; transform: scale(1); }
  to { opacity: 0; transform: scale(0.85); }
}
@keyframes app-restore {
  from { opacity: 0; transform: scale(0.9); }
  to { opacity: 1; transform: scale(1); }
}
#app.minimizing { animation: app-minimize 0.22s cubic-bezier(0.4, 0, 0.2, 1) forwards; }
#app.restoring { animation: app-restore 0.26s cubic-bezier(0.34, 1.56, 0.64, 1) forwards; }
#titlebar {
  height: 44px;
  min-height: 44px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 6px 0 14px;
  background: var(--bg);
  border-bottom: 1px solid var(--border);
}
#drag-region { flex: 1; display: flex; align-items: center; gap: 10px; height: 100%; }
#title-logo-wrap { width: 22px; height: 22px; display: flex; align-items: center; justify-content: center; }
#title-logo { max-width: 100%; max-height: 100%; }
#title-logo-fallback {
  display: none;
  width: 22px;
  height: 22px;
  border-radius: 6px;
  background: var(--accent-soft);
  color: var(--accent);
  font-size: 12px;
  font-weight: 700;
  align-items: center;
  justify-content: center;
}
#title-text { font-size: 13px; font-weight: 600; letter-spacing: 0.3px; color: var(--fg); }
#window-controls { display: flex; gap: 4px; }
#window-controls button {
  position: relative;
  overflow: hidden;
  width: 38px;
  height: 32px;
  border-radius: 6px;
  background: transparent;
  border: none;
  color: var(--fg-dim);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  transition: background 0.15s cubic-bezier(0.4, 0, 0.2, 1), color 0.15s cubic-bezier(0.4, 0, 0.2, 1);
}
#window-controls button:hover { background: rgba(127, 127, 127, 0.14); color: var(--fg); }
#btn-close:hover { background: rgba(224, 70, 70, 0.18); color: #ff6b6b; }
#shell { display: flex; flex: 1; min-height: 0; }
#sidebar {
  position: relative;
  width: 236px;
  min-width: 236px;
  background: var(--bg-elevated);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  transition: width 0.25s cubic-bezier(0.22, 1, 0.36, 1), min-width 0.25s cubic-bezier(0.22, 1, 0.36, 1);
  will-change: width;
}
#sidebar.collapsed { width: 72px; min-width: 72px; }
#sidebar-toggle {
  position: absolute;
  top: 50%;
  right: -12px;
  transform: translateY(-50%);
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--bg-card);
  border: 1px solid var(--border-strong);
  color: var(--fg-dim);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  box-shadow: 0 2px 8px var(--shadow);
  z-index: 5;
  font-size: 11px;
  transition: background 0.15s cubic-bezier(0.4, 0, 0.2, 1), color 0.15s cubic-bezier(0.4, 0, 0.2, 1), border-color 0.15s cubic-bezier(0.4, 0, 0.2, 1);
}
#sidebar-toggle:hover { background: var(--accent-soft); color: var(--accent); border-color: var(--accent); }
#sidebar-list { flex: 1; overflow-y: auto; padding: 14px 10px 10px 10px; }
#sidebar-bottom { padding: 10px; border-top: 1px solid var(--border); }
.nav-item {
  position: relative;
  height: 44px;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0 14px;
  margin-bottom: 4px;
  border-radius: 8px;
  color: var(--fg-dim);
  font-size: 13.5px;
  font-weight: 500;
  cursor: pointer;
  overflow: hidden;
  background: transparent;
  transition: background-color 0.2s cubic-bezier(0.4, 0, 0.2, 1), color 0.2s cubic-bezier(0.4, 0, 0.2, 1), transform 0.15s cubic-bezier(0.4, 0, 0.2, 1), justify-content 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  will-change: transform;
}
.nav-item i { width: 16px; text-align: center; font-size: 14.5px; color: inherit; transition: color 0.2s cubic-bezier(0.4, 0, 0.2, 1); }
.nav-item:hover { background: rgba(127, 127, 127, 0.1); color: var(--fg); }
.nav-item.active { background: rgba(127, 127, 127, 0.14); color: var(--fg); font-weight: 600; }
.nav-item.active i { color: var(--accent); }
.nav-item.active::before {
  content: "";
  position: absolute;
  left: 0;
  top: 9px;
  bottom: 9px;
  width: 3px;
  border-radius: 0 3px 3px 0;
  background: var(--accent);
}
.nav-item:active { transform: scale(0.98); }
#sidebar.collapsed .nav-item { justify-content: center; padding: 0; gap: 0; }
#sidebar.collapsed .nav-item span { display: none; }
#sidebar-footer {
  padding: 14px 18px 18px 18px;
  border-top: 1px solid var(--border);
}
#sidebar.collapsed #sidebar-footer { display: none; }
.footer-line { font-size: 12px; color: var(--fg); font-weight: 600; }
.footer-line.dim { color: var(--fg-dim); font-weight: 400; margin-top: 4px; font-size: 11.5px; }
.version-badge {
  font-size: 10px;
  color: var(--fg-dim);
  font-weight: 500;
  background: var(--bg-card);
  border: 1px solid var(--border);
  padding: 2px 6px;
  border-radius: 4px;
  margin-left: 4px;
}
#content { flex: 1; display: flex; flex-direction: column; min-width: 0; }
#content-header {
  height: 64px;
  min-height: 64px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 28px;
  border-bottom: 1px solid var(--border);
}
#section-title { font-size: 19px; font-weight: 600; letter-spacing: 0.2px; }
.mini-loader {
  width: 15px;
  height: 15px;
  border-radius: 50%;
  border: 2px solid var(--border-strong);
  border-top-color: var(--accent);
  opacity: 0;
  animation: mini-spin 0.7s linear infinite;
  transition: opacity 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}
.mini-loader.show { opacity: 1; }
@keyframes mini-spin { to { transform: rotate(360deg); } }
#data-grid {
  flex: 1;
  padding: 24px 28px;
  display: flex;
  flex-direction: column;
  gap: 24px;
  overflow-y: auto;
}
.scroll-area, #data-grid, #sidebar-list {
  scrollbar-width: thin;
  scrollbar-color: var(--scrollbar) transparent;
  scroll-behavior: smooth;
  -webkit-overflow-scrolling: touch;
  overscroll-behavior: contain;
}
#data-grid::-webkit-scrollbar, #sidebar-list::-webkit-scrollbar { width: 8px; }
#data-grid::-webkit-scrollbar-thumb, #sidebar-list::-webkit-scrollbar-thumb { background: var(--scrollbar); border-radius: 4px; }
#data-grid::-webkit-scrollbar-track, #sidebar-list::-webkit-scrollbar-track { background: transparent; }
.group-section { display: flex; flex-direction: column; gap: 12px; }
.group-heading {
  font-size: 11.5px;
  text-transform: uppercase;
  letter-spacing: 0.8px;
  color: var(--fg-dim);
  font-weight: 700;
  padding-left: 2px;
}
.group-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(230px, 1fr));
  gap: 14px;
}
.card {
  position: relative;
  overflow: hidden;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px 40px 16px 18px;
  animation: card-in 0.3s cubic-bezier(0.4, 0, 0.2, 1) both;
  will-change: transform, opacity;
  transition: transform 0.2s cubic-bezier(0.4, 0, 0.2, 1), border-color 0.2s cubic-bezier(0.4, 0, 0.2, 1), box-shadow 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}
.card:hover { transform: translateY(-3px); border-color: var(--border-strong); box-shadow: 0 10px 22px var(--shadow); }
.copy-btn {
  position: absolute;
  top: 50%;
  right: 10px;
  transform: translateY(-50%);
  width: 26px;
  height: 26px;
  border-radius: 6px;
  border: none;
  background: transparent;
  color: var(--fg-dim);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.15s cubic-bezier(0.4, 0, 0.2, 1), background 0.15s cubic-bezier(0.4, 0, 0.2, 1), color 0.15s cubic-bezier(0.4, 0, 0.2, 1);
}
.card:hover .copy-btn { opacity: 1; pointer-events: auto; }
.copy-btn:hover { background: var(--accent-soft); color: var(--accent); }
.copy-btn i { font-size: 12px; }
@keyframes card-in {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}
.card-label { font-size: 11px; text-transform: uppercase; letter-spacing: 0.6px; color: var(--fg-dim); margin-bottom: 8px; }
.card-value { font-size: 15px; font-weight: 600; color: var(--fg); word-break: break-word; }
.card-deco {
  position: absolute;
  pointer-events: none;
  user-select: none;
  line-height: 1;
  filter: saturate(0.9);
}
.card-deco-tl { top: 6px; left: 8px; }
.card-deco-tr { top: 6px; right: 42px; }
.card-deco-bl { bottom: 6px; left: 10px; }
.card-deco-br { bottom: 6px; right: 14px; }
.card.skeleton {
  background: linear-gradient(90deg, var(--skeleton-a) 25%, var(--skeleton-b) 37%, var(--skeleton-a) 63%);
  background-size: 400% 100%;
  animation: shimmer 1.4s ease infinite;
}
@keyframes shimmer {
  0% { background-position: 100% 0; }
  100% { background-position: 0 0; }
}
.error-card {
  display: flex;
  align-items: center;
  gap: 12px;
  color: #ff6b6b;
  border-color: rgba(255, 107, 107, 0.25);
}
.setting-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px 18px;
  flex-wrap: wrap;
  animation: card-in 0.3s cubic-bezier(0.4, 0, 0.2, 1) both;
  will-change: transform, opacity;
}
.setting-row-info { display: flex; flex-direction: column; gap: 4px; max-width: 420px; }
.setting-row-title { font-size: 14px; font-weight: 600; color: var(--fg); }
.setting-row-desc { font-size: 12px; color: var(--fg-dim); line-height: 1.5; }
.segmented {
  display: flex;
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 3px;
  gap: 3px;
}
.segmented button {
  position: relative;
  overflow: hidden;
  border: none;
  background: transparent;
  color: var(--fg-dim);
  font-size: 12.5px;
  font-weight: 600;
  padding: 8px 12px;
  border-radius: 6px;
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.18s cubic-bezier(0.4, 0, 0.2, 1), color 0.18s cubic-bezier(0.4, 0, 0.2, 1);
}
.segmented button.active { background: var(--accent); color: var(--accent-contrast); }
.segmented button:hover:not(.active) { color: var(--fg); background: rgba(127, 127, 127, 0.12); }
.switch {
  position: relative;
  width: 44px;
  height: 24px;
  border-radius: 12px;
  background: var(--border-strong);
  cursor: pointer;
  overflow: hidden;
  flex-shrink: 0;
  transition: background 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}
.switch::after {
  content: "";
  position: absolute;
  top: 3px;
  left: 3px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #ffffff;
  transition: transform 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}
.switch.on { background: var(--accent); }
.switch.on::after { transform: translateX(20px); background: var(--accent-contrast); }
.number-input {
  width: 76px;
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  color: var(--fg);
  border-radius: 6px;
  padding: 8px 10px;
  font-size: 13px;
  text-align: center;
  font-family: inherit;
}
.number-input:focus { outline: none; border-color: var(--accent); }
.update-check {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
}
.update-check-btn {
  border: 1px solid var(--border);
  background: var(--bg-elevated);
  color: var(--fg);
  font-size: 12.5px;
  font-weight: 600;
  font-family: inherit;
  padding: 9px 14px;
  border-radius: 8px;
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.18s cubic-bezier(0.4, 0, 0.2, 1), border-color 0.18s cubic-bezier(0.4, 0, 0.2, 1);
}
.update-check-btn:hover:not(:disabled) { border-color: var(--border-strong); background: rgba(127, 127, 127, 0.12); }
.update-check-btn:disabled { opacity: 0.6; cursor: default; }
.update-check-status { font-size: 12px; color: var(--fg-dim); }
.update-check-status.positive { color: var(--fg); font-weight: 600; }
.update-changelog {
  display: none;
  width: 100%;
  margin: 0;
  padding-left: 18px;
  font-size: 12px;
  color: var(--fg-dim);
  line-height: 1.6;
}
.update-changelog.show { display: block; }
.update-changelog li { margin: 2px 0; }
.update-changelog strong { color: var(--fg); font-weight: 700; }
.update-changelog em { color: var(--fg); font-style: italic; }
.update-changelog del { opacity: 0.7; }
.update-changelog code {
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 1px 5px;
  font-family: "Consolas", "SFMono-Regular", Menlo, monospace;
  font-size: 11.5px;
  color: var(--fg);
}
.update-changelog a { color: var(--accent); text-decoration: none; }
.update-changelog a:hover { text-decoration: underline; }
.update-progress {
  display: none;
  width: 100%;
  height: 6px;
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: 4px;
  overflow: hidden;
}
.update-progress.show { display: block; }
.update-progress-bar {
  height: 100%;
  width: 0%;
  background: var(--accent);
  transition: width 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}
#toast {
  position: fixed;
  bottom: 22px;
  right: 22px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  color: var(--fg);
  padding: 10px 16px;
  border-radius: 8px;
  font-size: 12.5px;
  font-weight: 600;
  opacity: 0;
  transform: translateY(8px);
  transition: opacity 0.25s cubic-bezier(0.4, 0, 0.2, 1), transform 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  pointer-events: none;
  z-index: 60;
  box-shadow: 0 10px 24px var(--shadow);
}
#toast.show { opacity: 1; transform: translateY(0); }
#restart-overlay {
  position: fixed;
  inset: 0;
  z-index: 70;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.45);
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}
#restart-overlay.show { opacity: 1; pointer-events: auto; }
#restart-modal {
  width: 320px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 22px 22px 18px 22px;
  box-shadow: 0 20px 48px var(--shadow);
  transform: translateY(10px) scale(0.98);
  transition: transform 0.25s cubic-bezier(0.34, 1.56, 0.64, 1);
}
#restart-overlay.show #restart-modal { transform: translateY(0) scale(1); }
#restart-modal-title { font-size: 15px; font-weight: 700; color: var(--fg); margin-bottom: 8px; }
#restart-modal-desc { font-size: 12.5px; color: var(--fg-dim); line-height: 1.6; margin-bottom: 18px; }
#restart-modal-actions { display: flex; justify-content: flex-end; gap: 10px; }
#restart-modal-actions button {
  position: relative;
  overflow: hidden;
  border: none;
  font-family: inherit;
  font-size: 12.5px;
  font-weight: 700;
  padding: 9px 18px;
  border-radius: 7px;
  cursor: pointer;
  transition: opacity 0.18s cubic-bezier(0.4, 0, 0.2, 1), background 0.18s cubic-bezier(0.4, 0, 0.2, 1);
}
#restart-later {
  background: var(--bg-elevated);
  color: var(--fg);
  border: 1px solid var(--border-strong);
}
#restart-later:hover { background: rgba(127, 127, 127, 0.14); }
#restart-now {
  background: var(--accent);
  color: var(--accent-contrast);
}
#restart-now:hover { opacity: 0.85; }
.ripple {
  position: absolute;
  border-radius: 50%;
  background: rgba(127, 127, 127, 0.28);
  transform: scale(0);
  animation: ripple-anim 0.5s ease-out;
  pointer-events: none;
}
@keyframes ripple-anim {
  to { transform: scale(2.4); opacity: 0; }
}
.resize-grip { position: fixed; z-index: 100; }
.grip-top { top: 0; left: 8px; right: 8px; height: 4px; cursor: ns-resize; }
.grip-bottom { bottom: 0; left: 8px; right: 8px; height: 4px; cursor: ns-resize; }
.grip-left { top: 8px; bottom: 8px; left: 0; width: 4px; cursor: ew-resize; }
.grip-right { top: 8px; bottom: 8px; right: 0; width: 4px; cursor: ew-resize; }
.grip-top-left { top: 0; left: 0; width: 8px; height: 8px; cursor: nwse-resize; }
.grip-top-right { top: 0; right: 0; width: 8px; height: 8px; cursor: nesw-resize; }
.grip-bottom-left { bottom: 0; left: 0; width: 8px; height: 8px; cursor: nesw-resize; }
.grip-bottom-right { bottom: 0; right: 0; width: 8px; height: 8px; cursor: nwse-resize; }
</style>
</head>
<body>
<div class="resize-grip grip-top" data-edge="top"></div>
<div class="resize-grip grip-bottom" data-edge="bottom"></div>
<div class="resize-grip grip-left" data-edge="left"></div>
<div class="resize-grip grip-right" data-edge="right"></div>
<div class="resize-grip grip-top-left" data-edge="top-left"></div>
<div class="resize-grip grip-top-right" data-edge="top-right"></div>
<div class="resize-grip grip-bottom-left" data-edge="bottom-left"></div>
<div class="resize-grip grip-bottom-right" data-edge="bottom-right"></div>
<div id="boot-screen">
  <div class="boot-logo-wrap">
    <img id="boot-logo" alt="">
    <div id="boot-logo-fallback">S</div>
  </div>
  <div class="boot-title">__APP_NAME__</div>
  <div class="boot-subtitle">__APP_VERSION__</div>
  <div class="boot-progress"><div class="boot-progress-bar"></div></div>
  <div id="boot-status">Initializing...</div>
</div>
<div id="app">
  <div id="titlebar">
    <div id="drag-region">
      <div id="title-logo-wrap">
        <img id="title-logo" alt="">
        <div id="title-logo-fallback">S</div>
      </div>
      <span id="title-text">__APP_NAME__</span>
    </div>
    <div id="window-controls">
      <button id="btn-min" title="Minimize"><i class="fa-solid fa-minus"></i></button>
      <button id="btn-maximize" title="Maximize"><i class="fa-regular fa-square"></i></button>
      <button id="btn-close" title="Close"><i class="fa-solid fa-xmark"></i></button>
    </div>
  </div>
  <div id="shell">
    <nav id="sidebar">
      <button id="sidebar-toggle" title="Collapse sidebar"><i class="fa-solid fa-angles-left"></i></button>
      <div id="sidebar-list"></div>
      <div id="sidebar-bottom"></div>
      <div id="sidebar-footer">
        <div class="footer-line">__APP_NAME__<span class="version-badge">__APP_VERSION__</span></div>
        <div class="footer-line dim">Made by __APP_AUTHOR__ (__APP_AUTHOR_HANDLE__)</div>
      </div>
    </nav>
    <div id="content">
      <header id="content-header">
        <h1 id="section-title">Overview</h1>
        <div id="mini-loader" class="mini-loader" aria-hidden="true"></div>
      </header>
      <section id="data-grid"></section>
    </div>
  </div>
</div>
<div id="toast"></div>
<div id="restart-overlay">
  <div id="restart-modal">
    <div id="restart-modal-title">Restart Required</div>
    <div id="restart-modal-desc">This change needs the app to restart before it becomes active.</div>
    <div id="restart-modal-actions">
      <button id="restart-later">Restart Later</button>
      <button id="restart-now">Restart Now</button>
    </div>
  </div>
</div>
<script src="qrc:///qtwebchannel/qwebchannel.js"></script>
<script>
const LOGO_URI = "__LOGO_URI__";
const APP_VERSION = "__APP_VERSION__";
const UPDATE_CHECK_URL = "__UPDATE_TAGS_URL__";
const INITIAL_SETTINGS = __SETTINGS_JSON__;
const CATEGORY_ORDER = __CATEGORY_ORDER_JSON__;
const CATEGORY_META = {
  overview: { label: "Overview", icon: "fa-solid fa-gauge-high" },
  os: { label: "OS", icon: "fa-brands fa-windows" },
  motherboard: { label: "Motherboard", icon: "fa-solid fa-server" },
  processor: { label: "Processor", icon: "fa-solid fa-microchip" },
  graphics: { label: "Graphics Card", icon: "fa-solid fa-display" },
  memory: { label: "Memory", icon: "fa-solid fa-memory" },
  storage: { label: "Storage", icon: "fa-solid fa-hard-drive" },
  network: { label: "Network", icon: "fa-solid fa-network-wired" },
  temperatures: { label: "Temperatures", icon: "fa-solid fa-temperature-half" },
  hwid: { label: "Hardware ID's", icon: "fa-solid fa-fingerprint" },
  misc: { label: "Miscellaneous", icon: "fa-solid fa-ellipsis" },
};
const SETTINGS_META = { label: "Settings", icon: "fa-solid fa-gear" };
const RESTART_REQUIRED_KEYS = __RESTART_REQUIRED_KEYS_JSON__;
const VALID_THEMES = ["dark", "light", "halloween"];

function resolveTheme(value) {
  return VALID_THEMES.includes(value) ? value : "dark";
}

let bridge = null;
let activeCategory = "overview";
let loadedCache = {};
let bootMinTimeDone = false;
let pendingBootCategories = new Set(CATEGORY_ORDER);
let appReady = false;
let bootMsgInterval = null;
let activeRefreshTimer = null;
let backgroundRefreshTimer = null;
let settingsLoadTimer = null;
let settingsLoaded = false;
let settingsRowIndex = 0;
let currentSettings = Object.assign({}, INITIAL_SETTINGS);
let isWindowMaximized = false;
let renderedCategory = null;
let renderedValueEls = null;
let liveRegistry = {};
let updateCheckState = { status: "idle", latest: null, url: UPDATE_CHECK_URL, downloadUrl: null, assetName: null, assetSize: 0, whatsNew: [] };
let updateDownloadState = { status: "idle", received: 0, total: 0 };
let updateCheckStatusEl = null;
let updateCheckButtonEl = null;
let updateChangelogEl = null;
let updateProgressEl = null;
let updateProgressBarEl = null;

document.documentElement.setAttribute("data-theme", resolveTheme(currentSettings.theme));
document.body.classList.toggle("native-window", currentSettings.window_mode === "default");

function setupLogo(imgId, fallbackId) {
  const img = document.getElementById(imgId);
  const fallback = document.getElementById(fallbackId);
  if (LOGO_URI) {
    img.addEventListener("error", () => {
      img.style.display = "none";
      fallback.style.display = "flex";
    });
    img.src = LOGO_URI;
  } else {
    img.remove();
    fallback.style.display = "flex";
  }
}

function spawnRipple(event, target) {
  const circle = document.createElement("span");
  circle.className = "ripple";
  const rect = target.getBoundingClientRect();
  const size = Math.max(rect.width, rect.height);
  circle.style.width = circle.style.height = `${size}px`;
  circle.style.left = `${event.clientX - rect.left - size / 2}px`;
  circle.style.top = `${event.clientY - rect.top - size / 2}px`;
  target.appendChild(circle);
  circle.addEventListener("animationend", () => circle.remove());
}

function setupResizeGrips() {
  document.querySelectorAll(".resize-grip").forEach((grip) => {
    grip.addEventListener("mousedown", () => {
      if (bridge) bridge.startResize(grip.dataset.edge);
    });
  });
}

function setupTitlebar() {
  const dragRegion = document.getElementById("drag-region");
  dragRegion.addEventListener("mousedown", (e) => {
    if (e.button === 0 && bridge) bridge.startMove();
  });
  dragRegion.addEventListener("dblclick", () => {
    if (bridge) bridge.toggleMaximize();
  });
  document.getElementById("btn-min").addEventListener("click", (e) => {
    spawnRipple(e, e.currentTarget);
    triggerMinimize();
  });
  document.getElementById("btn-maximize").addEventListener("click", (e) => {
    spawnRipple(e, e.currentTarget);
    if (bridge) bridge.toggleMaximize();
  });
  document.getElementById("btn-close").addEventListener("click", (e) => {
    spawnRipple(e, e.currentTarget);
    if (bridge) bridge.closeWindow();
  });
}

function updateMaximizeIcon() {
  const btn = document.getElementById("btn-maximize");
  if (!btn) return;
  const icon = btn.querySelector("i");
  icon.className = isWindowMaximized ? "fa-regular fa-copy" : "fa-regular fa-square";
  btn.title = isWindowMaximized ? "Restore" : "Maximize";
}

function onWindowMaximizedChanged(isMaximized) {
  isWindowMaximized = isMaximized;
  document.body.classList.toggle("window-maximized", isMaximized);
  updateMaximizeIcon();
}

function triggerMinimize() {
  const app = document.getElementById("app");
  if (document.body.classList.contains("native-window")) {
    if (bridge) bridge.minimizeWindow();
    return;
  }
  app.classList.remove("restoring");
  app.classList.add("minimizing");
  const onEnd = () => {
    app.removeEventListener("animationend", onEnd);
    app.classList.remove("minimizing");
    if (bridge) bridge.minimizeWindow();
  };
  app.addEventListener("animationend", onEnd);
}

function onWindowMinimizedChanged(isMinimized) {
  if (isMinimized) return;
  if (document.body.classList.contains("native-window")) return;
  const app = document.getElementById("app");
  app.classList.remove("minimizing");
  app.classList.add("restoring");
  const onEnd = () => {
    app.removeEventListener("animationend", onEnd);
    app.classList.remove("restoring");
  };
  app.addEventListener("animationend", onEnd);
}

function setupRestartModal() {
  document.getElementById("restart-later").addEventListener("click", (e) => {
    spawnRipple(e, e.currentTarget);
    hideRestartNotice();
    if (bridge) bridge.deferRestart();
  });
  document.getElementById("restart-now").addEventListener("click", (e) => {
    spawnRipple(e, e.currentTarget);
    hideRestartNotice();
    if (bridge) bridge.restartApp();
  });
}

function setupSidebarToggle() {
  document.getElementById("sidebar-toggle").addEventListener("click", (e) => {
    spawnRipple(e, e.currentTarget);
    const sidebar = document.getElementById("sidebar");
    const collapsed = sidebar.classList.toggle("collapsed");
    const icon = document.querySelector("#sidebar-toggle i");
    icon.className = collapsed ? "fa-solid fa-angles-right" : "fa-solid fa-angles-left";
  });
}

function startBootMessages() {
  const messages = ["Initializing core...", "Scanning hardware...", "Collecting system data...", "Finalizing..."];
  let index = 0;
  const el = document.getElementById("boot-status");
  return setInterval(() => {
    index = (index + 1) % messages.length;
    el.textContent = messages[index];
  }, 650);
}

function requestAllCategories() {
  CATEGORY_ORDER.forEach((key) => {
    if (bridge) bridge.requestCategory(key);
  });
}

function tryFinishBoot() {
  if (bootMinTimeDone && pendingBootCategories.size === 0 && !appReady) {
    appReady = true;
    if (bootMsgInterval) clearInterval(bootMsgInterval);
    const boot = document.getElementById("boot-screen");
    const app = document.getElementById("app");
    boot.classList.add("boot-hide");
    app.classList.add("visible");
    setTimeout(() => { boot.style.display = "none"; }, 500);
    restartAutoRefresh();
  }
}

function buildSidebar() {
  const list = document.getElementById("sidebar-list");
  CATEGORY_ORDER.forEach((key) => {
    const meta = CATEGORY_META[key];
    const item = document.createElement("div");
    item.className = "nav-item";
    item.dataset.category = key;
    item.title = meta.label;
    item.innerHTML = `<i class="${meta.icon}"></i><span>${meta.label}</span>`;
    item.addEventListener("click", (e) => {
      spawnRipple(e, item);
      selectCategory(key);
    });
    list.appendChild(item);
  });
  const settingsWrap = document.getElementById("sidebar-bottom");
  const settingsItem = document.createElement("div");
  settingsItem.className = "nav-item";
  settingsItem.dataset.category = "settings";
  settingsItem.title = SETTINGS_META.label;
  settingsItem.innerHTML = `<i class="${SETTINGS_META.icon}"></i><span>${SETTINGS_META.label}</span>`;
  settingsItem.addEventListener("click", (e) => {
    spawnRipple(e, settingsItem);
    selectCategory("settings");
  });
  settingsWrap.appendChild(settingsItem);
  highlightActive("overview");
}

function highlightActive(key) {
  document.querySelectorAll(".nav-item").forEach((el) => {
    el.classList.toggle("active", el.dataset.category === key);
  });
}

function selectCategory(key) {
  activeCategory = key;
  highlightActive(key);
  document.getElementById("section-title").textContent = key === "settings" ? SETTINGS_META.label : CATEGORY_META[key].label;
  if (key === "settings") {
    if (settingsLoaded) {
      renderSettings();
    } else {
      if (settingsLoadTimer) clearTimeout(settingsLoadTimer);
      renderSkeleton();
      settingsLoadTimer = setTimeout(() => {
        settingsLoadTimer = null;
        settingsLoaded = true;
        if (activeCategory === "settings") renderSettings();
      }, 380);
    }
  } else if (loadedCache[key]) {
    renderData(key, loadedCache[key]);
  } else {
    renderSkeleton();
    if (bridge) bridge.requestCategory(key);
  }
  if (appReady) restartAutoRefresh();
}

function getRefreshIntervalMs() {
  const mode = currentSettings.refresh_mode;
  if (mode === "fast") return 1000;
  if (mode === "normal") return 3000;
  if (mode === "slow") return 5000;
  if (mode === "custom") {
    const secs = Number(currentSettings.refresh_custom_seconds) || 0;
    return secs > 0 ? secs * 1000 : 0;
  }
  return 3000;
}

function restartAutoRefresh() {
  if (activeRefreshTimer) {
    clearInterval(activeRefreshTimer);
    activeRefreshTimer = null;
  }
  if (backgroundRefreshTimer) {
    clearInterval(backgroundRefreshTimer);
    backgroundRefreshTimer = null;
  }
  const interval = getRefreshIntervalMs();
  if (interval <= 0) return;
  activeRefreshTimer = setInterval(() => {
    if (bridge && activeCategory !== "settings") bridge.requestCategory(activeCategory);
  }, interval);
  backgroundRefreshTimer = setInterval(() => {
    if (!bridge) return;
    CATEGORY_ORDER.forEach((key) => {
      if (key !== activeCategory) bridge.requestCategory(key);
    });
  }, interval * 3);
}

function isLiveValue(value) {
  return value !== null && typeof value === "object" && typeof value.live === "string";
}

function formatLiveUptime(epochSeconds, includeSeconds) {
  const totalSeconds = Math.max(0, Math.floor(Date.now() / 1000 - epochSeconds));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  if (!includeSeconds) return `${hours}h ${minutes}m`;
  const seconds = totalSeconds % 60;
  return `${hours}h ${minutes}m ${seconds}s`;
}

function liveValueText(descriptor) {
  if (descriptor.live === "uptime") {
    return formatLiveUptime(descriptor.epoch, !!descriptor.seconds);
  }
  if (descriptor.live === "clock") {
    const elapsedMs = Date.now() - descriptor.capturedAtMs;
    const date = new Date(descriptor.epoch * 1000 + elapsedMs);
    const pad = (n) => String(n).padStart(2, "0");
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
  }
  return "N/A";
}

function registerLiveValue(regKey, el, descriptor) {
  descriptor.capturedAtMs = Date.now();
  liveRegistry[regKey] = { el, descriptor };
  el.textContent = liveValueText(descriptor);
}

function tickLiveValues() {
  Object.values(liveRegistry).forEach(({ el, descriptor }) => {
    el.textContent = liveValueText(descriptor);
  });
}

setInterval(tickLiveValues, 1000);

function setMiniLoaderVisible(visible) {
  const loader = document.getElementById("mini-loader");
  if (!loader) return;
  loader.classList.toggle("show", visible && appReady);
}

function createGroupHeading(text) {
  const heading = document.createElement("div");
  heading.className = "group-heading";
  heading.textContent = text;
  return heading;
}

function createGroupSection(heading) {
  const section = document.createElement("div");
  section.className = "group-section";
  if (heading) section.appendChild(createGroupHeading(heading));
  const subgrid = document.createElement("div");
  subgrid.className = "group-grid";
  section.appendChild(subgrid);
  return { section, subgrid };
}

const HALLOWEEN_DECOS = ["🎃", "👻", "🦇", "🕸️", "🕷️", "💀", "🧙", "🔮"];
const HALLOWEEN_POSITIONS = ["tl", "tr", "bl", "br"];
const HALLOWEEN_DECO_CHANCE = 0.35;

function addHalloweenDecoration(card) {
  if (document.documentElement.getAttribute("data-theme") !== "halloween") return;
  if (Math.random() > HALLOWEEN_DECO_CHANCE) return;
  const deco = document.createElement("span");
  deco.className = "card-deco";
  deco.setAttribute("aria-hidden", "true");
  const emoji = HALLOWEEN_DECOS[Math.floor(Math.random() * HALLOWEEN_DECOS.length)];
  const position = HALLOWEEN_POSITIONS[Math.floor(Math.random() * HALLOWEEN_POSITIONS.length)];
  const rotation = Math.round(Math.random() * 30 - 15);
  const size = 14 + Math.round(Math.random() * 8);
  const opacity = (0.14 + Math.random() * 0.14).toFixed(2);
  deco.textContent = emoji;
  deco.classList.add(`card-deco-${position}`);
  deco.style.transform = `rotate(${rotation}deg)`;
  deco.style.fontSize = `${size}px`;
  deco.style.opacity = opacity;
  card.appendChild(deco);
}

function renderSkeleton() {
  renderedCategory = null;
  renderedValueEls = null;
  setMiniLoaderVisible(true);
  const grid = document.getElementById("data-grid");
  grid.innerHTML = "";
  const { section, subgrid } = createGroupSection();
  for (let i = 0; i < 6; i++) {
    const card = document.createElement("div");
    card.className = "card skeleton";
    card.style.height = "62px";
    subgrid.appendChild(card);
  }
  grid.appendChild(section);
}

function renderData(category, payload) {
  setMiniLoaderVisible(false);
  const grid = document.getElementById("data-grid");
  let parsed = {};
  try {
    parsed = JSON.parse(payload);
  } catch (err) {
    renderError("Failed to parse data");
    return;
  }
  const groupNames = Object.keys(parsed);
  grid.innerHTML = "";
  renderedCategory = category;
  renderedValueEls = {};
  liveRegistry = {};
  if (groupNames.length === 0) {
    renderError("No data available");
    renderedCategory = null;
    renderedValueEls = null;
    return;
  }
  let cardIndex = 0;
  groupNames.forEach((groupName) => {
    const fields = parsed[groupName] || {};
    const entries = Object.entries(fields);
    if (entries.length === 0) return;
    const { section, subgrid } = createGroupSection(groupName);
    entries.forEach(([key, value]) => {
      const card = document.createElement("div");
      card.className = "card";
      card.style.animationDelay = `${cardIndex * 30}ms`;
      cardIndex += 1;
      addHalloweenDecoration(card);
      const label = document.createElement("div");
      label.className = "card-label";
      label.textContent = key;
      const val = document.createElement("div");
      val.className = "card-value";
      const regKey = `${groupName}\u0000${key}`;
      if (isLiveValue(value)) {
        registerLiveValue(regKey, val, value);
      } else {
        val.textContent = value;
      }
      const copyBtn = document.createElement("button");
      copyBtn.type = "button";
      copyBtn.className = "copy-btn";
      copyBtn.title = "Copy";
      copyBtn.innerHTML = '<i class="fa-solid fa-copy"></i>';
      copyBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        spawnRipple(e, copyBtn);
        copyValue(key, val.textContent);
      });
      card.appendChild(label);
      card.appendChild(val);
      card.appendChild(copyBtn);
      subgrid.appendChild(card);
      renderedValueEls[regKey] = val;
    });
    grid.appendChild(section);
  });
}

function patchData(category, payload) {
  let parsed = {};
  try {
    parsed = JSON.parse(payload);
  } catch (err) {
    return;
  }
  const groupNames = Object.keys(parsed);
  const incomingKeys = [];
  groupNames.forEach((groupName) => {
    Object.keys(parsed[groupName] || {}).forEach((key) => {
      incomingKeys.push(`${groupName}\u0000${key}`);
    });
  });
  const existingKeys = renderedValueEls ? Object.keys(renderedValueEls) : [];
  const sameShape = renderedCategory === category &&
    existingKeys.length === incomingKeys.length &&
    incomingKeys.every((key) => Object.prototype.hasOwnProperty.call(renderedValueEls, key));
  if (!sameShape) {
    renderData(category, payload);
    return;
  }
  groupNames.forEach((groupName) => {
    const fields = parsed[groupName] || {};
    Object.entries(fields).forEach(([key, value]) => {
      const regKey = `${groupName}\u0000${key}`;
      const el = renderedValueEls[regKey];
      if (!el) return;
      if (isLiveValue(value)) {
        registerLiveValue(regKey, el, value);
        return;
      }
      if (liveRegistry[regKey]) delete liveRegistry[regKey];
      const text = String(value);
      if (el.textContent !== text) {
        el.textContent = text;
      }
    });
  });
}

function renderError(message) {
  setMiniLoaderVisible(false);
  renderedCategory = null;
  renderedValueEls = null;
  const grid = document.getElementById("data-grid");
  grid.innerHTML = "";
  const { section, subgrid } = createGroupSection();
  const card = document.createElement("div");
  card.className = "card error-card";
  card.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i><span>${escapeHtml(String(message == null ? "" : message))}</span>`;
  subgrid.appendChild(card);
  grid.appendChild(section);
}

function showRestartNotice() {
  document.getElementById("restart-overlay").classList.add("show");
}

function hideRestartNotice() {
  document.getElementById("restart-overlay").classList.remove("show");
}

function copyValue(label, text) {
  if (bridge) bridge.copyToClipboard(text);
  showToast(`${label} copied`);
}

function showToast(message) {
  const toast = document.getElementById("toast");
  toast.textContent = message;
  toast.classList.add("show");
  clearTimeout(toast._hideTimer);
  toast._hideTimer = setTimeout(() => toast.classList.remove("show"), 1800);
}

function persistSettings(partial) {
  if (bridge) bridge.updateSetting(JSON.stringify(partial));
}

function applySettingEffects(key) {
  if (key === "theme") {
    document.documentElement.setAttribute("data-theme", resolveTheme(currentSettings.theme));
    if (renderedCategory && Object.prototype.hasOwnProperty.call(loadedCache, renderedCategory)) {
      renderData(renderedCategory, loadedCache[renderedCategory]);
    }
  }
  if (key === "refresh_mode" || key === "refresh_custom_seconds") {
    restartAutoRefresh();
  }
}

function updateSetting(key, value) {
  currentSettings[key] = value;
  applySettingEffects(key);
  persistSettings({ [key]: value });
  if (RESTART_REQUIRED_KEYS.includes(key)) {
    showRestartNotice();
  } else {
    showToast("Settings saved");
  }
}

function buildSegmented(options, activeValue, onSelect) {
  const wrap = document.createElement("div");
  wrap.className = "segmented";
  options.forEach((opt) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = opt.label;
    btn.className = opt.value === activeValue ? "active" : "";
    btn.addEventListener("click", (e) => {
      spawnRipple(e, btn);
      onSelect(opt.value);
    });
    wrap.appendChild(btn);
  });
  return wrap;
}

function buildSwitchControl(isOn, onToggle) {
  const el = document.createElement("div");
  el.className = "switch" + (isOn ? " on" : "");
  el.addEventListener("click", (e) => {
    spawnRipple(e, el);
    onToggle(!el.classList.contains("on"));
  });
  return el;
}

function buildSettingRow(title, desc) {
  const row = document.createElement("div");
  row.className = "setting-row";
  row.style.animationDelay = `${settingsRowIndex * 30}ms`;
  settingsRowIndex += 1;
  const info = document.createElement("div");
  info.className = "setting-row-info";
  const titleEl = document.createElement("div");
  titleEl.className = "setting-row-title";
  titleEl.textContent = title;
  const descEl = document.createElement("div");
  descEl.className = "setting-row-desc";
  descEl.textContent = desc;
  info.appendChild(titleEl);
  info.appendChild(descEl);
  row.appendChild(info);
  return row;
}

function renderSettings() {
  setMiniLoaderVisible(false);
  renderedCategory = null;
  renderedValueEls = null;
  settingsRowIndex = 0;
  const grid = document.getElementById("data-grid");
  grid.innerHTML = "";

  const appearanceSection = document.createElement("div");
  appearanceSection.className = "group-section";
  appearanceSection.appendChild(createGroupHeading("Appearance"));
  const themeRow = buildSettingRow("Theme", "Switch the App-Theme.");
  themeRow.appendChild(buildSegmented(
    [
      { label: "Dark", value: "dark" },
      { label: "Light", value: "light" },
      { label: "Halloween", value: "halloween" },
    ],
    currentSettings.theme,
    (value) => { updateSetting("theme", value); renderSettings(); }
  ));
  appearanceSection.appendChild(themeRow);
  grid.appendChild(appearanceSection);

  const perfSection = document.createElement("div");
  perfSection.className = "group-section";
  perfSection.appendChild(createGroupHeading("Performance"));
  const refreshRow = buildSettingRow("Refresh Rate", "How often the current category reloads itself automatically.");
  refreshRow.appendChild(buildSegmented(
    [
      { label: "Fast (1s)", value: "fast" },
      { label: "Normal (3s)", value: "normal" },
      { label: "Slow (5s)", value: "slow" },
      { label: "Custom", value: "custom" },
    ],
    currentSettings.refresh_mode,
    (value) => { updateSetting("refresh_mode", value); renderSettings(); }
  ));
  perfSection.appendChild(refreshRow);
  if (currentSettings.refresh_mode === "custom") {
    const customRow = buildSettingRow("Custom Interval", "Seconds between refreshes. 0 disables auto refresh.");
    const input = document.createElement("input");
    input.type = "number";
    input.min = "0";
    input.className = "number-input";
    input.value = currentSettings.refresh_custom_seconds;
    input.addEventListener("change", () => {
      const value = Math.max(0, parseInt(input.value, 10) || 0);
      input.value = value;
      updateSetting("refresh_custom_seconds", value);
    });
    customRow.appendChild(input);
    perfSection.appendChild(customRow);
  }
  grid.appendChild(perfSection);

  const windowSection = document.createElement("div");
  windowSection.className = "group-section";
  windowSection.appendChild(createGroupHeading("Window"));
  const windowRow = buildSettingRow("Window Style", "Use a custom window or the default Windows window frame.");
  windowRow.appendChild(buildSegmented(
    [{ label: "Default Window", value: "default" }, { label: "Custom Window", value: "custom" }],
    currentSettings.window_mode,
    (value) => { updateSetting("window_mode", value); renderSettings(); }
  ));
  windowSection.appendChild(windowRow);
  grid.appendChild(windowSection);

  const privSection = document.createElement("div");
  privSection.className = "group-section";
  privSection.appendChild(createGroupHeading("Privileges"));
  const adminRow = buildSettingRow("Start as Administrator", "Recommended for full hardware access. Applies on next launch.");
  adminRow.appendChild(buildSwitchControl(
    !!currentSettings.start_as_admin,
    (value) => { updateSetting("start_as_admin", value); renderSettings(); }
  ));
  privSection.appendChild(adminRow);

  const updateRow = buildSettingRow("Software Update", `You are currently on version ${APP_VERSION}.`);
  const updateWrap = document.createElement("div");
  updateWrap.className = "update-check";
  const checkBtn = document.createElement("button");
  checkBtn.type = "button";
  checkBtn.className = "update-check-btn";
  checkBtn.textContent = "Check for Updates";
  checkBtn.addEventListener("click", (e) => {
    spawnRipple(e, checkBtn);
    if (updateCheckState.status === "available") {
      if (updateCheckState.downloadUrl) {
        startUpdateDownload();
      } else if (bridge) {
        bridge.openExternalUrl(updateCheckState.url || UPDATE_CHECK_URL);
      }
    } else {
      startUpdateCheck();
    }
  });
  const progressEl = document.createElement("div");
  progressEl.className = "update-progress";
  const progressBarEl = document.createElement("div");
  progressBarEl.className = "update-progress-bar";
  progressEl.appendChild(progressBarEl);
  const statusEl = document.createElement("div");
  statusEl.className = "update-check-status";
  const changelogEl = document.createElement("ul");
  changelogEl.className = "update-changelog";
  updateWrap.appendChild(checkBtn);
  updateWrap.appendChild(progressEl);
  updateWrap.appendChild(statusEl);
  updateWrap.appendChild(changelogEl);
  updateRow.appendChild(updateWrap);
  privSection.appendChild(updateRow);

  updateCheckButtonEl = checkBtn;
  updateProgressEl = progressEl;
  updateProgressBarEl = progressBarEl;
  updateCheckStatusEl = statusEl;
  updateChangelogEl = changelogEl;
  applyUpdateCheckState();

  grid.appendChild(privSection);

  const backupSection = document.createElement("div");
  backupSection.className = "group-section";
  backupSection.appendChild(createGroupHeading("Backup"));
  const backupRow = buildSettingRow("Export / Import Settings", "Save your current settings to a file, or load them from a previously exported file.");
  const backupWrap = document.createElement("div");
  backupWrap.className = "update-check";
  const exportBtn = document.createElement("button");
  exportBtn.type = "button";
  exportBtn.className = "update-check-btn";
  exportBtn.textContent = "Export Settings";
  exportBtn.addEventListener("click", (e) => {
    spawnRipple(e, exportBtn);
    startExportSettings();
  });
  const importBtn = document.createElement("button");
  importBtn.type = "button";
  importBtn.className = "update-check-btn";
  importBtn.textContent = "Import Settings";
  importBtn.addEventListener("click", (e) => {
    spawnRipple(e, importBtn);
    startImportSettings();
  });
  backupWrap.appendChild(exportBtn);
  backupWrap.appendChild(importBtn);
  backupRow.appendChild(backupWrap);
  backupSection.appendChild(backupRow);
  grid.appendChild(backupSection);
}

function formatBytes(num) {
  if (!num || num <= 0) return "0 MB";
  return `${(num / (1024 * 1024)).toFixed(1)} MB`;
}

function escapeHtml(text) {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function formatInlineMarkdown(text) {
  let formatted = escapeHtml(String(text == null ? "" : text));
  formatted = formatted.replace(/`([^`]+)`/g, "<code>$1</code>");
  formatted = formatted.replace(/\\[([^\\]]+)\\]\\((https?:\\/\\/[^\\s)]+)\\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
  formatted = formatted.replace(/\\*\\*([^*]+)\\*\\*/g, "<strong>$1</strong>");
  formatted = formatted.replace(/__([^_]+)__/g, "<strong>$1</strong>");
  formatted = formatted.replace(/~~([^~]+)~~/g, "<del>$1</del>");
  formatted = formatted.replace(/\\*([^*]+)\\*/g, "<em>$1</em>");
  formatted = formatted.replace(/_([^_]+)_/g, "<em>$1</em>");
  return formatted;
}

function startUpdateCheck() {
  if (updateCheckState.status === "checking") return;
  updateDownloadState = { status: "idle", received: 0, total: 0 };
  updateCheckState = { status: "checking", latest: null, url: updateCheckState.url || UPDATE_CHECK_URL, downloadUrl: null, assetName: null, assetSize: 0, whatsNew: [] };
  applyUpdateCheckState();
  if (bridge) bridge.checkForUpdates();
}

function onUpdateCheckResult(payload) {
  let parsed = {};
  try {
    parsed = JSON.parse(payload);
  } catch (err) {
    updateCheckState = { status: "error", latest: null, url: UPDATE_CHECK_URL, downloadUrl: null, assetName: null, assetSize: 0, whatsNew: [] };
    applyUpdateCheckState();
    return;
  }
  if (parsed.error) {
    updateCheckState = { status: "error", latest: parsed.latest || null, url: parsed.url || UPDATE_CHECK_URL, downloadUrl: null, assetName: null, assetSize: 0, whatsNew: [] };
  } else if (parsed.available) {
    updateCheckState = {
      status: "available",
      latest: parsed.latest,
      url: parsed.url || UPDATE_CHECK_URL,
      downloadUrl: parsed.download_url || null,
      assetName: parsed.asset_name || null,
      assetSize: parsed.asset_size || 0,
      whatsNew: Array.isArray(parsed.whats_new) ? parsed.whats_new : [],
    };
  } else {
    updateCheckState = { status: "current", latest: parsed.latest, url: parsed.url || UPDATE_CHECK_URL, downloadUrl: null, assetName: null, assetSize: 0, whatsNew: [] };
  }
  applyUpdateCheckState();
}

function startUpdateDownload() {
  if (!updateCheckState.downloadUrl || updateDownloadState.status === "downloading" || updateDownloadState.status === "installing") return;
  updateDownloadState = { status: "downloading", received: 0, total: updateCheckState.assetSize || 0 };
  applyUpdateCheckState();
  if (bridge) bridge.downloadUpdate(updateCheckState.downloadUrl, updateCheckState.assetName || "");
}

function onUpdateDownloadProgress(received, total) {
  updateDownloadState = { status: "downloading", received, total: total || updateDownloadState.total };
  applyUpdateCheckState();
}

function onUpdateDownloadReady() {
  updateDownloadState = { status: "installing", received: updateDownloadState.total, total: updateDownloadState.total };
  applyUpdateCheckState();
}

function onUpdateDownloadError(message) {
  updateDownloadState = { status: "error", received: 0, total: 0 };
  applyUpdateCheckState();
}

function startExportSettings() {
  if (bridge) bridge.exportSettings();
}

function startImportSettings() {
  if (bridge) bridge.importSettings();
}

function onSettingsExported(success, info) {
  showToast(success ? "Settings exported" : "Export failed");
}

function onSettingsImported(success, info) {
  if (!success) {
    showToast("Import failed");
    return;
  }
  let parsed = null;
  try {
    parsed = JSON.parse(info);
  } catch (err) {
    showToast("Import failed");
    return;
  }
  currentSettings = Object.assign({}, currentSettings, parsed);
  document.documentElement.setAttribute("data-theme", resolveTheme(currentSettings.theme));
  if (renderedCategory && Object.prototype.hasOwnProperty.call(loadedCache, renderedCategory)) {
    renderData(renderedCategory, loadedCache[renderedCategory]);
  }
  if (appReady) restartAutoRefresh();
  if (activeCategory === "settings") renderSettings();
  showToast("Settings imported");
}

function applyUpdateCheckState() {
  if (!updateCheckStatusEl || !updateCheckButtonEl || !updateChangelogEl || !updateProgressEl || !updateProgressBarEl) return;
  const checkStatus = updateCheckState.status;
  const downloadStatus = updateDownloadState.status;
  updateProgressEl.classList.remove("show");
  updateCheckStatusEl.classList.remove("positive");
  updateChangelogEl.classList.remove("show");
  updateChangelogEl.innerHTML = "";

  if (downloadStatus === "downloading" || downloadStatus === "installing") {
    const percent = updateDownloadState.total > 0 ? Math.min(100, Math.round((updateDownloadState.received / updateDownloadState.total) * 100)) : 0;
    updateCheckButtonEl.disabled = true;
    updateCheckButtonEl.textContent = downloadStatus === "installing" ? "Installing..." : "Downloading...";
    updateProgressEl.classList.add("show");
    updateProgressBarEl.style.width = `${percent}%`;
    updateCheckStatusEl.textContent = downloadStatus === "installing"
      ? "Installing update, the app will restart shortly."
      : `Downloading ${formatBytes(updateDownloadState.received)} / ${formatBytes(updateDownloadState.total)} (${percent}%)`;
    return;
  }

  updateCheckButtonEl.disabled = checkStatus === "checking";
  if (checkStatus === "available") {
    updateCheckButtonEl.textContent = "Update Now";
  } else {
    updateCheckButtonEl.textContent = checkStatus === "checking" ? "Checking..." : "Check for Updates";
  }

  if (downloadStatus === "error") {
    updateCheckStatusEl.textContent = "Update download failed. Try again.";
  } else if (checkStatus === "idle") {
    updateCheckStatusEl.textContent = "";
  } else if (checkStatus === "checking") {
    updateCheckStatusEl.textContent = "Checking for updates...";
  } else if (checkStatus === "current") {
    updateCheckStatusEl.textContent = "You are on the latest version.";
  } else if (checkStatus === "available") {
    updateCheckStatusEl.textContent = updateCheckState.downloadUrl
      ? `Version ${updateCheckState.latest} is available (${formatBytes(updateCheckState.assetSize)}).`
      : `Version ${updateCheckState.latest} is available.`;
    updateCheckStatusEl.classList.add("positive");
    if (updateCheckState.whatsNew && updateCheckState.whatsNew.length > 0) {
      updateCheckState.whatsNew.forEach((item) => {
        const li = document.createElement("li");
        li.innerHTML = formatInlineMarkdown(item);
        updateChangelogEl.appendChild(li);
      });
      updateChangelogEl.classList.add("show");
    }
  } else if (checkStatus === "error") {
    updateCheckStatusEl.textContent = "Could not check for updates.";
  }
}

function onCategoryData(category, payload) {
  const isRefresh = Object.prototype.hasOwnProperty.call(loadedCache, category);
  loadedCache[category] = payload;
  if (category === activeCategory) {
    if (isRefresh) {
      patchData(category, payload);
    } else {
      renderData(category, payload);
    }
  }
  pendingBootCategories.delete(category);
  tryFinishBoot();
}

function onCategoryError(category, message) {
  if (category === activeCategory) renderError(message);
  pendingBootCategories.delete(category);
  tryFinishBoot();
}

setupLogo("boot-logo", "boot-logo-fallback");
setupLogo("title-logo", "title-logo-fallback");
setupResizeGrips();
setupTitlebar();
setupSidebarToggle();
setupRestartModal();
bootMsgInterval = startBootMessages();
setTimeout(() => { bootMinTimeDone = true; tryFinishBoot(); }, 900);

new QWebChannel(qt.webChannelTransport, (channel) => {
  bridge = channel.objects.bridge;
  bridge.categoryData.connect(onCategoryData);
  bridge.categoryError.connect(onCategoryError);
  bridge.restartRequired.connect(showRestartNotice);
  bridge.updateCheckResult.connect(onUpdateCheckResult);
  bridge.updateDownloadProgress.connect(onUpdateDownloadProgress);
  bridge.updateDownloadReady.connect(onUpdateDownloadReady);
  bridge.updateDownloadError.connect(onUpdateDownloadError);
  bridge.windowMaximizedChanged.connect(onWindowMaximizedChanged);
  bridge.windowMinimizedChanged.connect(onWindowMinimizedChanged);
  bridge.settingsExported.connect(onSettingsExported);
  bridge.settingsImported.connect(onSettingsImported);
  buildSidebar();
  selectCategory("overview");
  requestAllCategories();
});
</script>
</body>
</html>
'''


def build_html():
    html = HTML
    settings_payload = dict(SETTINGS)
    html = html.replace("__LOGO_URI__", LOGO_URI)
    html = html.replace("__SETTINGS_JSON__", json.dumps(settings_payload))
    html = html.replace("__APP_NAME__", APP_NAME)
    html = html.replace("__APP_VERSION__", APP_VERSION)
    html = html.replace("__APP_AUTHOR__", APP_AUTHOR)
    html = html.replace("__APP_AUTHOR_HANDLE__", APP_AUTHOR_HANDLE)
    html = html.replace("__UPDATE_TAGS_URL__", UPDATE_TAGS_PAGE_URL)
    html = html.replace("__CATEGORY_ORDER_JSON__", json.dumps(list(PROVIDERS.keys())))
    html = html.replace("__RESTART_REQUIRED_KEYS_JSON__", json.dumps(sorted(RESTART_REQUIRED_KEYS)))
    return html


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1280, 800)
        self.setMinimumSize(1000, 650)
        frameless = SETTINGS.get("window_mode", "default") != "default"
        self.frameless = frameless
        self._custom_maximized = False
        self._normal_geometry = None
        self._was_minimized = False
        self._maximize_animation = None
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, frameless)
        if frameless:
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        if os.path.exists(LOGO_PATH):
            self.setWindowIcon(QIcon(LOGO_PATH))

        self.view = QWebEngineView(self)
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.setCentralWidget(self.view)
        if frameless:
            self.view.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            self.view.page().setBackgroundColor(QColor(Qt.GlobalColor.transparent))

        settings = self.view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)

        self.channel = QWebChannel()
        self.bridge = Bridge(self)
        self.channel.registerObject("bridge", self.bridge)
        self.view.page().setWebChannel(self.channel)
        self.view.setHtml(build_html(), BASE_URL)

        self.setWindowOpacity(0.0)
        self.fade_animation = QPropertyAnimation(self, b"windowOpacity")
        self.fade_animation.setDuration(450)
        self.fade_animation.setStartValue(0.0)
        self.fade_animation.setEndValue(1.0)
        self.fade_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade_started = False
        self._load_finished = False
        self.view.loadFinished.connect(self._on_load_finished)
        QTimer.singleShot(4000, self._force_fade)

    def _on_load_finished(self, ok):
        self._load_finished = True
        self._maybe_start_fade()

    def _force_fade(self):
        self._load_finished = True
        self._maybe_start_fade()

    def _maybe_start_fade(self):
        if self._fade_started or not self._load_finished or not self.isVisible():
            return
        self._fade_started = True
        self.fade_animation.start()

    def showEvent(self, event):
        super().showEvent(event)
        self._maybe_start_fade()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            is_min = self.isMinimized()
            if is_min != self._was_minimized:
                self._was_minimized = is_min
                self.bridge.windowMinimizedChanged.emit(is_min)
                if is_min and self.bridge._restart_pending:
                    self.bridge._restart_pending = False
                    QTimer.singleShot(150, self.bridge.restartApp)
            if not self.frameless:
                self.bridge.windowMaximizedChanged.emit(self.isMaximized())

    def animatedToggleMaximize(self):
        if self._maximize_animation is not None and self._maximize_animation.state() == QPropertyAnimation.State.Running:
            return
        screen = self.screen() or QApplication.primaryScreen()
        available = screen.availableGeometry()
        start_geo = self.geometry()
        if not self._custom_maximized:
            self._normal_geometry = start_geo
            end_geo = available
            self._custom_maximized = True
        else:
            end_geo = self._normal_geometry if self._normal_geometry is not None else start_geo
            self._custom_maximized = False
        anim = QPropertyAnimation(self, b"geometry")
        anim.setDuration(260)
        anim.setStartValue(start_geo)
        anim.setEndValue(end_geo)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._maximize_animation = anim
        anim.start()
        self.bridge.windowMaximizedChanged.emit(self._custom_maximized)


def main():
    if IS_WINDOWS and SETTINGS.get("start_as_admin", True) and not is_admin():
        if relaunch_as_admin():
            sys.exit(0)
        show_admin_required_dialog()
        if IS_FROZEN:
            os._exit(0)
        sys.exit(0)

    start_cpu_monitor()

    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName(APP_AUTHOR)

    missing_assets = get_missing_assets()
    if missing_assets:
        show_missing_assets_dialog(missing_assets)

    window = MainWindow()
    window.show()
    app.aboutToQuit.connect(window.bridge.shutdownCategoryWorkers)

    exit_code = app.exec()
    if IS_FROZEN:
        os._exit(exit_code)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
