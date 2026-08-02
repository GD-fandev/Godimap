import ctypes
import difflib
import json
import os
import re
import sys
import time
import tkinter as tk
import traceback
import unicodedata
import webbrowser
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from ctypes import wintypes
from pathlib import Path
from tkinter import messagebox, ttk

import dxcam
from PIL import Image, ImageDraw, ImageEnhance, ImageGrab, ImageOps, ImageTk
from map_store import MapStore
from app_update_checker import APP_VERSION, fetch_latest_release, is_newer_version
from map_updater import (
    download_and_install,
    fetch_manifest,
    load_local_version,
    update_is_available,
)


if getattr(sys, "frozen", False):
    APP_DIR = Path(sys.executable).resolve().parent
    BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR))
    # Keep user-maintained maps, per-map JSON files, and OCR models beside the
    # executable so a distributed build can be updated without rebuilding it.
    RESOURCE_DIR = APP_DIR
else:
    APP_DIR = Path(__file__).resolve().parent
    RESOURCE_DIR = APP_DIR.parent
    BUNDLE_DIR = RESOURCE_DIR

LOCAL_APPDATA = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
CONFIG_PATH = LOCAL_APPDATA / "Godimap" / "godimap-config.json"
UPDATE_ERROR_LOG_PATH = LOCAL_APPDATA / "Godimap" / "update-error.log"
MAP_STORE = MapStore(RESOURCE_DIR)

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
ERROR_ALREADY_EXISTS = 183
GWL_EXSTYLE = -20
GWLP_HWNDPARENT = -8
GA_ROOT = 2
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TRANSPARENT = 0x00000020
HWND_TOPMOST = wintypes.HWND(-1)
HWND_TOP = wintypes.HWND(0)
HWND_NOTOPMOST = wintypes.HWND(-2)
SW_SHOWNOACTIVATE = 4
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020
SWP_SHOWWINDOW = 0x0040
VK_F11 = 0x7A
VK_SHIFT = 0x10
VK_CONTROL = 0x11

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

try:
    user32.SetProcessDPIAware()
except Exception:
    pass

EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [EnumWindowsProc, wintypes.LPARAM]
user32.EnumWindows.restype = wintypes.BOOL
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL
user32.IsIconic.argtypes = [wintypes.HWND]
user32.IsIconic.restype = wintypes.BOOL
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetForegroundWindow.restype = wintypes.HWND
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetAncestor.restype = wintypes.HWND
user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
user32.SetWindowLongPtrW.restype = ctypes.c_void_p
user32.EnableWindow.argtypes = [wintypes.HWND, wintypes.BOOL]
user32.EnableWindow.restype = wintypes.BOOL
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.CreateMutexW.restype = wintypes.HANDLE


def is_toggle_key_down():
    return bool(user32.GetAsyncKeyState(VK_F11) & 0x8000)


DEFAULT_CONFIG = {
    "process_name": "Godius.exe",
    "window_title": "Godius Client",
    "capture_region": None,
    "capture_reference_size": None,
    "coordinate_region": None,
    "coordinate_reference_size": None,
    "debug_x": 35,
    "debug_y": 35,
    "map_x": 1200,
    "map_y": 80,
    "map_offset_x": None,
    "map_offset_y": None,
    "map_size_scale": 1.0,
    "map_opacity_percent": 100,
    "ocr_interval_ms": 700,
    "map_match_hold_seconds": 2.0,
    "ui_language": None,
    "ocr_backend": "paddle",
    "ignored_app_update_version": None,
}


def detect_windows_ui_language():
    try:
        buffer = ctypes.create_unicode_buffer(85)
        kernel32.GetUserDefaultLocaleName(buffer, len(buffer))
        language_tag = buffer.value.lower()
    except Exception:
        language_tag = ""
    if language_tag.startswith("ja"):
        return "JP"
    if language_tag.startswith("ko"):
        return "KR"
    return "EN"


def load_config():
    if not CONFIG_PATH.exists():
        config = dict(DEFAULT_CONFIG)
        config["ui_language"] = detect_windows_ui_language()
        return config
    try:
        saved = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        config = {**DEFAULT_CONFIG, **saved}
        if config.get("ui_language") not in ("KR", "JP", "EN"):
            config["ui_language"] = detect_windows_ui_language()
        return config
    except Exception:
        config = dict(DEFAULT_CONFIG)
        config["ui_language"] = detect_windows_ui_language()
        return config


def save_config(config):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_update_error_log(error):
    try:
        UPDATE_ERROR_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        detail = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        UPDATE_ERROR_LOG_PATH.write_text(
            f"Time: {datetime.now().astimezone().isoformat()}\n"
            f"Type: {type(error).__name__}\n"
            f"Error: {error}\n\n"
            f"{detail}",
            encoding="utf-8",
        )
        return True
    except Exception:
        return False


def contributors_for_map(map_record):
    if not isinstance(map_record, dict):
        return []
    raw_names = map_record.get("contributors", [])
    names = raw_names if isinstance(raw_names, list) else [raw_names]
    clean_names = []
    for raw_name in names:
        name = " ".join(str(raw_name).split()).strip()
        if name and name not in clean_names:
            clean_names.append(name[:40])
    return clean_names[:5]


STATUS_TEXTS = {
    "searching": {"KR": "Godius Client 탐색 중", "JP": "Godius Clientを検索中", "EN": "Searching for Godius Client"},
    "no_map_resize": {"KR": "표시 중인 미니맵이 없어 크기를 조절할 수 없습니다.", "JP": "表示中のミニマップがないため、サイズを変更できません。", "EN": "No minimap is available to resize."},
    "resize_mode": {"KR": "미니맵 크기 조절 중 · 노란 꼭짓점을 드래그 · Ctrl+F11로 완료", "JP": "ミニマップのサイズ変更中・黄色いハンドルをドラッグ・Ctrl+F11で完了", "EN": "Resizing minimap · Drag the yellow handle · Ctrl+F11 to finish"},
    "opacity": {"KR": "미니맵 불투명도 {percent}%", "JP": "ミニマップ不透明度 {percent}%", "EN": "Minimap opacity {percent}%"},
    "size": {"KR": "미니맵 크기 {percent}% · 꼭짓점을 놓으면 저장", "JP": "ミニマップサイズ {percent}%・ハンドルを離すと保存", "EN": "Minimap size {percent}% · Release the handle to save"},
    "target_missing": {"KR": "Godius Client 창을 찾지 못했습니다.", "JP": "Godius Clientウィンドウが見つかりません。", "EN": "Godius Client window was not found."},
    "need_name_region": {"KR": "F11을 눌러 맵 이름 영역을 먼저 저장해 주세요.", "JP": "F11を押して、先にマップ名の範囲を保存してください。", "EN": "Press F11 and save the map-name region first."},
    "need_coordinate_region": {"KR": "Shift+F11을 눌러 좌표 영역을 저장해 주세요.", "JP": "Shift+F11を押して、座標範囲を保存してください。", "EN": "Press Shift+F11 and save the coordinate region."},
    "debug_overlap": {"KR": "GODIMAP 창이 OCR 영역을 가림 · 창을 옮겨 주세요", "JP": "GODIMAPウィンドウがOCR範囲を覆っています・ウィンドウを移動してください", "EN": "The GODIMAP window overlaps the OCR region · Move the window"},
    "map_overlap": {"KR": "미니맵이 OCR 영역을 가림 · 수정 모드에서 옮겨 주세요", "JP": "ミニマップがOCR範囲を覆っています・編集モードで移動してください", "EN": "The minimap overlaps the OCR region · Move it in edit mode"},
    "capture_failed": {"KR": "{backend} 캡처 실패: {error}", "JP": "{backend}のキャプチャーに失敗: {error}", "EN": "{backend} capture failed: {error}"},
    "error": {"KR": "오류: {error}", "JP": "エラー: {error}", "EN": "Error: {error}"},
    "black_frame": {"KR": "검은 캡처 프레임 폐기 · 마지막 정상 상태 유지", "JP": "黒いキャプチャーフレームを破棄・最後の正常状態を維持", "EN": "Discarded a black capture frame · Keeping the last valid state"},
    "confirmed": {"KR": "확정됨: {name} [{language}] · 유사도 {score:.0%}", "JP": "確定: {name} [{language}]・類似度 {score:.0%}", "EN": "Confirmed: {name} [{language}] · Similarity {score:.0%}"},
    "confirming": {"KR": "맵 이름 재확인 중 (1/2)", "JP": "マップ名を再確認中 (1/2)", "EN": "Confirming map name (1/2)"},
    "no_map_data": {"KR": "맵 이름을 5초 이상 찾지 못함 · No Map Data", "JP": "マップ名を5秒以上検出できません・No Map Data", "EN": "Map name not found for 5 seconds · No Map Data"},
    "temporary_miss": {"KR": "맵 이름 일시 인식 실패 · 현재 맵 유지", "JP": "マップ名を一時的に認識できません・現在のマップを維持", "EN": "Temporary map-name miss · Keeping the current map"},
    "finding_map": {"KR": "저장된 맵 이름을 찾는 중", "JP": "保存済みのマップ名を検索中", "EN": "Searching saved map names"},
    "minimized": {"KR": "Godius가 최소화되어 인식을 일시정지했습니다.", "JP": "Godiusが最小化されたため認識を一時停止しました。", "EN": "Recognition paused because Godius is minimized."},
    "other_foreground": {"KR": "다른 창이 전면이라 캡처 일시정지 · 마지막 정상 상태 유지", "JP": "別のウィンドウが前面のためキャプチャーを一時停止・最後の正常状態を維持", "EN": "Capture paused while another window is in front · Keeping the last valid state"},
}

SECTION_LABELS = {
    "KR": {"ocr": "OCR", "recognized": "인식된 내용", "status": "상태"},
    "JP": {"ocr": "OCR", "recognized": "認識結果", "status": "状態"},
    "EN": {"ocr": "OCR", "recognized": "Recognized Content", "status": "Status"},
}

UPDATE_TEXTS = {
    "available": {
        "KR": "최신 맵 업데이트가 있습니다. 업데이트하시려면 여기를 눌러주세요.",
        "JP": "最新のマップ更新があります。更新するにはここをクリックしてください。",
        "EN": "A map update is available. Click here to update.",
    },
    "downloading": {
        "KR": "맵 데이터를 다운로드하고 있습니다... {percent}%",
        "JP": "マップデータをダウンロードしています... {percent}%",
        "EN": "Downloading map data... {percent}%",
    },
    "installed": {
        "KR": "맵 업데이트 완료 · 버전 {version} · 맵 {count}개",
        "JP": "マップ更新完了・バージョン {version}・マップ {count}件",
        "EN": "Map update complete · Version {version} · {count} maps",
    },
    "failed": {
        "KR": "맵 업데이트에 실패했습니다. 다시 시도하려면 여기를 눌러주세요.",
        "JP": "マップ更新に失敗しました。再試行するにはここをクリックしてください。",
        "EN": "Map update failed. Click here to try again.",
    },
}

UPDATE_ERROR_DIALOGS = {
    "KR": {
        "title": "맵 업데이트 실패",
        "message": "맵 업데이트를 완료하지 못했습니다.\n\n{error}\n\n오류 로그: %LOCALAPPDATA%\\Godimap\\update-error.log",
    },
    "JP": {
        "title": "マップ更新失敗",
        "message": "マップ更新を完了できませんでした。\n\n{error}\n\nエラーログ: %LOCALAPPDATA%\\Godimap\\update-error.log",
    },
    "EN": {
        "title": "Map update failed",
        "message": "The map update could not be completed.\n\n{error}\n\nError log: %LOCALAPPDATA%\\Godimap\\update-error.log",
    },
}

WAITING_TEXTS = {
    "KR": "(대기 중)",
    "JP": "(待機中)",
    "EN": "(Waiting)",
}

VERSION_LABELS = {
    "KR": f"v{APP_VERSION} 정식 릴리스",
    "JP": f"v{APP_VERSION} 正式リリース",
    "EN": f"v{APP_VERSION} Stable Release",
}

APP_UPDATE_DIALOGS = {
    "KR": {
        "title": "GODIMAP 업데이트",
        "message": "GODIMAP 프로그램의 새 버전({version})이 있습니다.\n다운로드하러 가시겠습니까?",
        "yes": "예",
        "no": "아니오",
        "skip": "다음 업데이트까지 알리지 않음",
    },
    "JP": {
        "title": "GODIMAPアップデート",
        "message": "GODIMAPの新しいバージョン（{version}）があります。\nダウンロードページを開きますか？",
        "yes": "はい",
        "no": "いいえ",
        "skip": "次のアップデートまで通知しない",
    },
    "EN": {
        "title": "GODIMAP Update",
        "message": "A new version of GODIMAP ({version}) is available.\nWould you like to open the download page?",
        "yes": "Yes",
        "no": "No",
        "skip": "Don't notify until the next update",
    },
}


def load_map_database():
    try:
        return MAP_STORE.load_maps()
    except Exception:
        return []


def map_database_signature():
    paths = MAP_STORE.iter_map_paths()
    return tuple(
        (path.relative_to(MAP_STORE.data_dir).as_posix(), path.stat().st_mtime_ns, path.stat().st_size)
        for path in paths
    )


def normalize_text(value):
    return "".join(ch.lower() for ch in value if ch.isalnum())


def canonicalize_for_match(value):
    normalized = unicodedata.normalize("NFKC", value).casefold()
    substitutions = {
        "o": "0",
        "〇": "0",
        "○": "0",
        "l": "1",
        "i": "1",
        "|": "1",
        "!": "1",
        "굴": "글",
        "충": "층",
    }
    result = []
    for character in normalized:
        if character.isalnum() or character in substitutions:
            result.append(substitutions.get(character, character))
    return "".join(result)


def find_best_map_match(name_results, maps, active_map=None):
    per_map = {}
    for map_record in maps:
        map_id = map_record.get("id")
        best_for_map = (0.0, None)
        aliases = map_record.get("names", {})
        for language_key, recognized in name_results.items():
            recognized_key = canonicalize_for_match(recognized)
            if not recognized_key:
                continue
            for alias in aliases.get(language_key, []):
                alias_key = canonicalize_for_match(alias)
                if not alias_key:
                    continue
                if recognized_key == alias_key:
                    score = 1.0
                else:
                    score = difflib.SequenceMatcher(None, recognized_key, alias_key).ratio()
                if score > best_for_map[0]:
                    best_for_map = (score, language_key)
        if best_for_map[1] is not None:
            per_map[map_id] = (best_for_map[0], best_for_map[1], map_record)

    ranked = sorted(per_map.values(), key=lambda item: item[0], reverse=True)
    if not ranked or ranked[0][0] < 0.76:
        return None, None, 0.0

    best_score, best_language, best_map = ranked[0]
    if best_score >= 0.999:
        return best_map, best_language, best_score

    if len(ranked) > 1 and best_score - ranked[1][0] < 0.04:
        active_id = active_map.get("id") if active_map else None
        active_candidate = next((item for item in ranked if item[2].get("id") == active_id and best_score - item[0] < 0.04), None)
        if active_candidate:
            return active_candidate[2], active_candidate[1], active_candidate[0]
        return None, None, 0.0

    return best_map, best_language, best_score


def debug_valid_locale(name_results, matched_language=None, match_score=0.0):
    """Choose one trustworthy locale for the debug readout, if possible."""
    if matched_language in ("ko", "ja", "en") and match_score >= 0.76:
        return matched_language

    # Even without registered map data, a result made predominantly from the
    # Latin alphabet is clearly an English-locale read. Digits and punctuation
    # do not dilute the ratio, and a minimum length avoids classifying "B1".
    english_text = unicodedata.normalize("NFKC", str(name_results.get("en", "")))
    letters = [character for character in english_text if character.isalpha()]
    latin_letters = [character for character in letters if "a" <= character.casefold() <= "z"]
    if len(latin_letters) >= 3 and len(latin_letters) / max(1, len(letters)) >= 0.70:
        return "en"
    return None


def process_path_from_pid(pid):
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(32768)
        buf = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return buf.value
        return ""
    finally:
        kernel32.CloseHandle(handle)


def process_name_for_hwnd(hwnd):
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return os.path.basename(process_path_from_pid(pid.value))


def window_title_for_hwnd(hwnd):
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def find_target_window(process_name, window_title):
    title_matches = []
    process_matches = []
    title_needle = window_title.lower()
    process_needle = process_name.lower()

    def callback(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        title = window_title_for_hwnd(hwnd)
        if title_needle and title_needle in title.lower():
            title_matches.append(hwnd)
        if process_name_for_hwnd(hwnd).lower() == process_needle:
            process_matches.append(hwnd)
        return True

    user32.EnumWindows(EnumWindowsProc(callback), 0)
    return title_matches[0] if title_matches else process_matches[0] if process_matches else None


def get_client_screen_rect(hwnd):
    rect = wintypes.RECT()
    origin = wintypes.POINT(0, 0)
    if not hwnd or not user32.GetClientRect(hwnd, ctypes.byref(rect)):
        return None
    if not user32.ClientToScreen(hwnd, ctypes.byref(origin)):
        return None
    if rect.right <= 0 or rect.bottom <= 0:
        return None
    return origin.x, origin.y, origin.x + rect.right, origin.y + rect.bottom


def set_noactivate_toolwindow(window, click_through=False):
    window.update_idletasks()
    hwnd = user32.GetAncestor(window.winfo_id(), GA_ROOT) or window.winfo_id()
    style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    style |= WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
    if click_through:
        style |= WS_EX_TRANSPARENT
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)


def set_window_click_through(window, enabled):
    window.update_idletasks()
    widget_hwnd = window.winfo_id()
    root_hwnd = user32.GetAncestor(widget_hwnd, GA_ROOT) or widget_hwnd
    # Apply layered/input styles only to the native top-level wrapper. Applying
    # WS_EX_LAYERED to Tk's child canvas prevents the minimap from painting.
    style = user32.GetWindowLongW(root_hwnd, GWL_EXSTYLE)
    style |= WS_EX_TOOLWINDOW | WS_EX_LAYERED
    if enabled:
        style |= WS_EX_TRANSPARENT | WS_EX_NOACTIVATE
    else:
        style &= ~(WS_EX_TRANSPARENT | WS_EX_NOACTIVATE)
    user32.SetWindowLongW(root_hwnd, GWL_EXSTYLE, style)
    user32.SetWindowPos(
        root_hwnd,
        HWND_TOP,
        0,
        0,
        0,
        0,
        SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_FRAMECHANGED,
    )
    # A disabled window can still consume hit-testing and redirect activation
    # to its owner. Keep it enabled and let the transparent layered style pass
    # mouse input directly to the game underneath.
    user32.EnableWindow(root_hwnd, True)


def keep_topmost(window):
    if not window.winfo_viewable():
        window.deiconify()
    hwnd = user32.GetAncestor(window.winfo_id(), GA_ROOT) or window.winfo_id()
    user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
    user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW)


def show_above_owner(window, owner_hwnd):
    if not window.winfo_viewable():
        window.deiconify()
    hwnd = user32.GetAncestor(window.winfo_id(), GA_ROOT) or window.winfo_id()
    if owner_hwnd:
        user32.SetWindowLongPtrW(hwnd, GWLP_HWNDPARENT, owner_hwnd)
    user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
    user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW)
    user32.SetWindowPos(hwnd, HWND_TOP, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW)


class GodimapOcrDebug:
    def __init__(self):
        self.config = load_config()
        self.ui_language = self.config.get("ui_language", "EN")
        self.current_status_key = "searching"
        self.current_status_values = {}
        self.current_status_color = "#ffd066"
        self.maps = load_map_database()
        self.map_database_state = map_database_signature()
        self.active_map = None
        self.pending_map_id = None
        self.pending_map_hits = 0
        self.target_hwnd = None
        self.calibration_mode = None
        self.last_toggle_down = False
        self.ocr_running = False
        self.last_ocr_at = 0
        self.last_map_match_at = 0.0
        self.map_miss_started_at = None
        self.no_map_data_visible = False
        self.no_map_data_shown_at = None
        self.no_map_data_dismissed_for_miss = False
        self.no_map_animation_step = 1
        self.last_no_map_animation_at = 0.0
        self.last_coordinate_at = 0.0
        self.current_game_coordinate = None
        self.credit_map_id = None
        self.credit_started_at = None
        self.credit_visible_until = 0.0
        self.map_updates_enabled = bool(getattr(sys, "frozen", False)) or os.environ.get("GODIMAP_ENABLE_UPDATER") == "1"
        self.update_future = None
        self.update_task = None
        self.update_manifest = None
        self.update_banner_state = None
        self.update_banner_values = {}
        self.update_banner_until = 0.0
        self.update_progress_percent = 0
        self.app_update_future = None
        self.app_update_dialog = None
        self.marker_visible = True
        self.last_marker_blink_at = time.monotonic()
        self.capture_bbox = None
        self.stable_client_rect = None
        self.pending_client_rect = None
        self.pending_client_rect_hits = 0
        self.map_dragging = False
        self.map_resize_mode = False
        self.map_resizing = False
        self.map_resize_corner = None
        self.map_resize_anchor = None
        self.map_resize_start_scale = None
        self.map_resize_start_size = None
        self.scale_indicator_until = 0.0
        self.opacity_indicator_until = 0.0
        self.map_drag_start = None
        self.map_drag_origin = None
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="godimap-ocr")
        self.update_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="godimap-map-update")
        self.app_update_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="godimap-app-update")
        self.ocr_backend_name = os.environ.get(
            "GODIMAP_OCR_BACKEND", self.config.get("ocr_backend", "paddle")
        ).lower()
        if self.ocr_backend_name == "windows":
            # WinRT and ONNX Runtime can conflict when both native runtimes are
            # loaded in the same process.  Import only the selected backend.
            from windows_ocr_backend import WindowsOcrBackend

            self.ocr = WindowsOcrBackend()
        else:
            try:
                from paddle_ocr_backend import PaddleOcrBackend

                self.ocr = PaddleOcrBackend(RESOURCE_DIR / "ocr_models")
                self.ocr_backend_name = "paddle"
            except Exception:
                from windows_ocr_backend import WindowsOcrBackend

                self.ocr = WindowsOcrBackend()
                self.ocr_backend_name = "windows"
        self.capture_backend = "Desktop Duplication"
        try:
            self.desktop_camera = dxcam.create(output_color="RGB", processor_backend="numpy")
        except Exception:
            self.desktop_camera = None
            self.capture_backend = "ImageGrab fallback"
        self.closed = False

        self.root = tk.Tk()
        try:
            self.window_icon = tk.PhotoImage(file=str(BUNDLE_DIR / "assets" / "icons" / "godimapicon.png"))
            self.root.iconphoto(True, self.window_icon)
        except Exception:
            self.window_icon = None
        self.root.title("GODIMAP")
        self.root.configure(bg="#15191f")
        self.root.attributes("-topmost", True)
        debug_width = min(680, max(560, self.root.winfo_screenwidth() - 40))
        debug_height = min(490, max(430, self.root.winfo_screenheight() - 80))
        debug_x = max(0, min(int(self.config["debug_x"]), self.root.winfo_screenwidth() - debug_width))
        debug_y = max(0, min(int(self.config["debug_y"]), self.root.winfo_screenheight() - debug_height))
        self.root.geometry(f"{debug_width}x{debug_height}+{debug_x}+{debug_y}")
        self.root.minsize(560, 430)
        self.root.resizable(True, True)
        self.root.protocol("WM_DELETE_WINDOW", self.quit)

        header = tk.Frame(self.root, bg="#15191f")
        header.pack(fill="x", padx=12, pady=(10, 4))
        tk.Label(header, text="GODIMAP", fg="#55c7f3", bg="#15191f", font=("Segoe UI", 11, "bold")).pack(side="left")
        self.version_label = tk.Label(
            header,
            text=VERSION_LABELS[self.ui_language],
            fg="#8f9ba8",
            bg="#15191f",
            font=("Segoe UI", 8),
        )
        self.version_label.pack(side="left", padx=(7, 0), pady=(3, 0))
        tk.Button(header, text="EXIT", command=self.quit, bg="#3b4652", fg="white", relief="flat", padx=12).pack(side="right")
        tk.Button(header, text="HELP", command=self.show_help, bg="#3b4652", fg="white", relief="flat", padx=12).pack(side="right", padx=(0, 6))
        self.locale_button = tk.Button(
            header,
            text=self.ui_language,
            command=self.cycle_locale,
            bg="#3b4652",
            fg="white",
            relief="flat",
            width=4,
        )
        self.locale_button.pack(side="right", padx=(0, 6))

        self.section_labels = {}

        def add_section_label(key):
            label = tk.Label(
                self.root,
                text=SECTION_LABELS[self.ui_language][key],
                anchor="w",
                fg="#8f9ba8",
                bg="#15191f",
                font=("맑은 고딕", 9, "bold"),
            )
            label.pack(fill="x", padx=12, pady=(5, 0))
            self.section_labels[key] = label

        add_section_label("ocr")

        self.preview_label = tk.Label(self.root, bg="black", bd=1, relief="solid")
        self.preview_label.pack(fill="x", padx=12, pady=5, ipady=2)
        self.preview_label.configure(height=8)

        add_section_label("recognized")
        result_frame = tk.Frame(self.root, bg="#20262d", bd=1, relief="solid", padx=10, pady=7)
        result_frame.pack(fill="x", padx=12, pady=(5, 7))
        self.ocr_result_labels = {}
        result_rows = (
            ("ko", "KR", "#72d6ff"),
            ("ja", "JP", "#ff9fcf"),
            ("en", "EN", "#a8e6a3"),
            ("coordinates", "X:Y", "#ffe27a"),
        )
        for row_index, (key, title, color) in enumerate(result_rows):
            tk.Label(
                result_frame,
                text=title,
                width=8,
                anchor="w",
                fg=color,
                bg="#20262d",
                font=("맑은 고딕", 11, "bold"),
            ).grid(row=row_index, column=0, sticky="nw", pady=3)
            value_label = tk.Label(
                result_frame,
                text=WAITING_TEXTS[self.ui_language],
                anchor="w",
                justify="left",
                wraplength=530,
                fg="white",
                bg="#20262d",
                font=("맑은 고딕", 12, "bold"),
            )
            value_label.grid(row=row_index, column=1, sticky="ew", padx=(8, 0), pady=3)
            self.ocr_result_labels[key] = value_label
        result_frame.columnconfigure(1, weight=1)
        result_frame.bind(
            "<Configure>",
            lambda event: [
                label.configure(wraplength=max(260, event.width - 120))
                for label in self.ocr_result_labels.values()
            ],
        )

        add_section_label("status")
        state_frame = tk.Frame(self.root, bg="#0d1117", height=68, bd=1, relief="solid")
        state_frame.pack(fill="x", padx=12, pady=(0, 12))
        state_frame.pack_propagate(False)
        self.state_frame = state_frame
        self.state_label = tk.Label(
            state_frame,
            text=STATUS_TEXTS[self.current_status_key][self.ui_language],
            anchor="w",
            justify="left",
            wraplength=620,
            fg="#ffd066",
            bg="#0d1117",
            font=("맑은 고딕", 10),
        )
        self.state_label.pack(fill="both", expand=True, padx=4, pady=4)
        self.update_label = tk.Label(
            state_frame,
            text="",
            anchor="w",
            justify="left",
            fg="#ff6868",
            bg="#0d1117",
            font=("맑은 고딕", 9, "bold"),
            cursor="hand2",
            wraplength=620,
        )
        self.update_label.bind("<Button-1>", self.on_update_click)
        state_frame.bind(
            "<Configure>",
            lambda event: (
                self.state_label.configure(wraplength=max(300, event.width - 8)),
                self.update_label.configure(wraplength=max(300, event.width - 8)),
            ),
        )

        self.root.update_idletasks()
        required_height = self.root.winfo_reqheight() + 8
        fitted_height = min(self.root.winfo_screenheight() - 80, max(debug_height, required_height))
        fitted_y = max(0, min(debug_y, self.root.winfo_screenheight() - fitted_height))
        self.root.geometry(f"{debug_width}x{fitted_height}+{debug_x}+{fitted_y}")
        self.root.minsize(560, min(fitted_height, required_height))

        self.preview_photo = None
        self.map_photo = None
        self.region_window = self.create_region_window()
        self.map_window = self.create_map_window()
        self.drag_kind = None
        self.drag_start = None
        self.drag_bbox = None
        if self.map_updates_enabled:
            self.root.after(800, self.start_update_check)
            self.root.after(1600, self.start_app_update_check)
        self.root.after(50, self.tick)

    def start_app_update_check(self):
        if self.closed or self.app_update_future is not None:
            return
        self.app_update_future = self.app_update_executor.submit(fetch_latest_release)

    def finish_app_update_check(self):
        future = self.app_update_future
        self.app_update_future = None
        try:
            release = future.result()
        except Exception:
            # Version checking must never interrupt normal program startup.
            return
        version = release["version"]
        if not is_newer_version(version):
            return
        if self.config.get("ignored_app_update_version") == version:
            return
        self.show_app_update_dialog(release)

    def show_app_update_dialog(self, release):
        if self.app_update_dialog and self.app_update_dialog.winfo_exists():
            return
        texts = APP_UPDATE_DIALOGS[self.ui_language]
        window = tk.Toplevel(self.root)
        self.app_update_dialog = window
        window.title(texts["title"])
        window.configure(bg="#15191f")
        window.resizable(False, False)
        window.transient(self.root)
        window.grab_set()
        if self.window_icon is not None:
            window.iconphoto(True, self.window_icon)
        tk.Label(
            window,
            text=texts["message"].format(version=release["version"]),
            justify="left",
            fg="white",
            bg="#15191f",
            font=("Segoe UI", 10),
            padx=20,
            pady=18,
        ).pack(fill="x")
        buttons = tk.Frame(window, bg="#15191f")
        buttons.pack(fill="x", padx=14, pady=(0, 14))

        def close():
            window.grab_release()
            window.destroy()
            self.app_update_dialog = None

        def open_release():
            close()
            webbrowser.open(release["url"], new=2)

        def ignore_version():
            self.config["ignored_app_update_version"] = release["version"]
            save_config(self.config)
            close()

        tk.Button(buttons, text=texts["yes"], command=open_release, width=10).pack(side="left", padx=3)
        tk.Button(buttons, text=texts["no"], command=close, width=10).pack(side="left", padx=3)
        tk.Button(buttons, text=texts["skip"], command=ignore_version).pack(side="left", padx=3)
        window.protocol("WM_DELETE_WINDOW", close)
        window.update_idletasks()
        x = self.root.winfo_rootx() + max(0, (self.root.winfo_width() - window.winfo_reqwidth()) // 2)
        y = self.root.winfo_rooty() + max(0, (self.root.winfo_height() - window.winfo_reqheight()) // 2)
        window.geometry(f"+{x}+{y}")

    def start_update_check(self):
        if self.closed or self.update_future is not None:
            return
        self.update_task = "check"
        self.update_future = self.update_executor.submit(fetch_manifest)

    def show_update_banner(self, state, **values):
        self.update_banner_state = state
        self.update_banner_values = values
        template = UPDATE_TEXTS[state][self.ui_language]
        self.update_label.configure(
            text=template.format(**values),
            fg="#69df88" if state == "installed" else "#ff6868",
            cursor="hand2" if state in ("available", "failed") else "arrow",
        )
        if not self.update_label.winfo_manager():
            self.update_label.pack(side="bottom", fill="x", padx=4, pady=(0, 5))
        self.state_frame.configure(height=94)

    def hide_update_banner(self):
        self.update_banner_state = None
        self.update_banner_values = {}
        self.update_banner_until = 0.0
        self.update_label.pack_forget()
        self.state_frame.configure(height=68)

    def refresh_update_banner_locale(self):
        if self.update_banner_state:
            self.show_update_banner(self.update_banner_state, **self.update_banner_values)

    def on_update_click(self, _event=None):
        if self.update_banner_state not in ("available", "failed"):
            return
        if not self.update_manifest or self.update_future is not None:
            return
        self.update_progress_percent = 0
        self.show_update_banner("downloading", percent=0)
        self.update_task = "install"
        self.update_future = self.update_executor.submit(
            download_and_install,
            self.update_manifest,
            APP_DIR,
            self.record_update_progress,
        )

    def record_update_progress(self, downloaded, total):
        if total > 0:
            self.update_progress_percent = max(0, min(100, round(downloaded * 100 / total)))

    def finish_update_task(self):
        future = self.update_future
        task = self.update_task
        self.update_future = None
        self.update_task = None
        try:
            result = future.result()
        except Exception as exc:
            if task == "install":
                write_update_error_log(exc)
                self.show_update_banner("failed")
                dialog = UPDATE_ERROR_DIALOGS[self.ui_language]
                messagebox.showerror(
                    dialog["title"],
                    dialog["message"].format(error=f"{type(exc).__name__}: {exc}"),
                    parent=self.root,
                )
            return
        if task == "check":
            self.update_manifest = result
            local_version = load_local_version(APP_DIR)
            if update_is_available(local_version, result):
                self.show_update_banner("available")
            return
        if task == "install":
            self.reload_maps_after_update()
            self.show_update_banner(
                "installed",
                version=result["version"],
                count=result["map_count"],
            )
            self.update_banner_until = time.monotonic() + 6.0

    def reload_maps_after_update(self):
        active_id = str(self.active_map.get("id", "")) if self.active_map else ""
        was_visible = self.map_window.winfo_viewable()
        self.maps = load_map_database()
        self.map_database_state = map_database_signature()
        updated_active = next((item for item in self.maps if str(item.get("id", "")) == active_id), None)
        if updated_active:
            self.active_map = None
            self.map_original_image = None
            self.map_base_image = None
            self.set_active_map(updated_active)
            if was_visible:
                self.show_map()
        elif active_id:
            self.active_map = None
            self.current_game_coordinate = None
            self.hide_map()

    def set_status(self, key, color="#ffd066", **values):
        self.current_status_key = key
        self.current_status_values = values
        self.current_status_color = color
        translations = STATUS_TEXTS.get(key, STATUS_TEXTS["error"])
        template = translations.get(self.ui_language, translations["EN"])
        self.state_label.configure(text=template.format(**values), fg=color)

    def refresh_status(self):
        self.set_status(self.current_status_key, self.current_status_color, **self.current_status_values)

    def cycle_locale(self):
        languages = ("KR", "JP", "EN")
        previous_waiting_text = WAITING_TEXTS[self.ui_language]
        self.ui_language = languages[(languages.index(self.ui_language) + 1) % len(languages)]
        self.config["ui_language"] = self.ui_language
        save_config(self.config)
        self.locale_button.configure(text=self.ui_language)
        self.version_label.configure(text=VERSION_LABELS[self.ui_language])
        for key, label in self.section_labels.items():
            label.configure(text=SECTION_LABELS[self.ui_language][key])
        for label in self.ocr_result_labels.values():
            if label.cget("text") in WAITING_TEXTS.values() or label.cget("text") == previous_waiting_text:
                label.configure(text=WAITING_TEXTS[self.ui_language])
        self.refresh_status()
        self.refresh_update_banner_locale()

    def show_help(self):
        if hasattr(self, "help_window") and self.help_window.winfo_exists():
            self.help_window.lift()
            return

        help_texts = {
            "KR": (
                "캡처 영역 설정\n"
                "  F11 : 맵 이름 OCR 영역 설정\n"
                "  Shift + F11 : X:Y 좌표 OCR 영역 설정\n\n"
                "  박스 드래그 : 영역 이동\n"
                "  우측 하단 손잡이 드래그 : 영역 크기 조절\n\n"
                "미니맵 조작\n"
                "  Ctrl + F11 : 크기 조절 모드 시작/종료\n"
                "  우측 하단 노란 손잡이 드래그 : 크기 조절 (40~500%)\n"
                "  마우스 휠 : 불투명도 조절 (30~100%)\n"
                "  드래그 : 미니맵 이동\n\n"
                "OCR은 Godius Client가 전면에 있을 때만 실행됩니다."
            ),
            "JP": (
                "キャプチャー範囲の設定\n"
                "  F11 : マップ名のOCR範囲を設定\n"
                "  Shift + F11 : X:Y座標のOCR範囲を設定\n\n"
                "  ボックスをドラッグ : 範囲を移動\n"
                "  右下のハンドルをドラッグ : 範囲のサイズを変更\n\n"
                "ミニマップ操作\n"
                "  Ctrl + F11 : サイズ変更モードの開始／終了\n"
                "  右下の黄色いハンドルをドラッグ : サイズ変更（40～500%）\n"
                "  マウスホイール : 不透明度の調整（30～100%）\n"
                "  ドラッグ : ミニマップの移動\n\n"
                "OCRはGodius Clientが最前面にある場合のみ実行されます。"
            ),
            "EN": (
                "Capture regions\n"
                "  F11 : Set the map-name OCR region\n"
                "  Shift + F11 : Set the X:Y coordinate OCR region\n\n"
                "  Drag the box : Move the region\n"
                "  Drag the bottom-right handle : Resize the region\n\n"
                "Minimap controls\n"
                "  Ctrl + F11 : Enter or leave resize mode\n"
                "  Drag the yellow bottom-right handle : Resize (40–500%)\n"
                "  Mouse wheel : Adjust opacity (30–100%)\n"
                "  Drag : Move the minimap\n\n"
                "OCR runs only while Godius Client is in the foreground."
            ),
        }

        window = tk.Toplevel(self.root)
        self.help_window = window
        window.title("GODIMAP HELP")
        window.transient(self.root)
        window.grab_set()

        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        available_width = max(440, screen_width - 100)
        available_height = max(320, screen_height - 140)
        content_width = min(720, available_width - 48)

        body = ttk.Frame(window, padding=(20, 18, 20, 12))
        body.pack(fill="both", expand=True)
        tk.Message(
            body,
            text=help_texts[self.ui_language],
            width=content_width,
            anchor="nw",
            justify="left",
            font=("맑은 고딕", 11),
        ).pack(fill="both", expand=True)
        ttk.Button(body, text="OK", command=window.destroy).pack(pady=(16, 0))

        window.update_idletasks()
        width = min(available_width, max(480, window.winfo_reqwidth()))
        height = min(available_height, max(300, window.winfo_reqheight()))
        x = max(0, min(screen_width - width, self.root.winfo_rootx() + (self.root.winfo_width() - width) // 2))
        y = max(0, min(screen_height - height, self.root.winfo_rooty() + (self.root.winfo_height() - height) // 2))
        window.geometry(f"{width}x{height}+{x}+{y}")
        window.resizable(False, False)
        window.protocol("WM_DELETE_WINDOW", window.destroy)

    def create_map_window(self):
        win = tk.Toplevel(self.root)
        win.overrideredirect(True)
        win.attributes("-topmost", False)
        win.configure(bg="#000000")
        self.map_canvas = tk.Canvas(win, bg="#000000", highlightthickness=2, highlightbackground="#444444", cursor="fleur")
        self.map_canvas.pack(fill="both", expand=True)
        self.map_canvas.bind("<ButtonPress-1>", self.map_press)
        self.map_canvas.bind("<B1-Motion>", self.map_drag)
        self.map_canvas.bind("<ButtonRelease-1>", self.map_release)
        self.map_canvas.bind("<MouseWheel>", self.map_wheel)
        self.map_canvas.bind("<Motion>", self.map_pointer_motion)
        self.map_canvas.bind("<Leave>", lambda _event: self.map_canvas.configure(cursor="fleur"))
        self.map_width = 1
        self.map_height = 1
        self.map_scale = 1.0
        self.map_base_image = None
        self.map_original_image = None
        win.geometry(f"1x1+{int(self.config['map_x'])}+{int(self.config['map_y'])}")
        win.withdraw()
        # Outside edit mode the overlay is disabled and all mouse input passes through.
        set_noactivate_toolwindow(win, click_through=True)
        set_window_click_through(win, True)
        return win

    def set_active_map(self, map_record):
        self.no_map_data_visible = False
        self.no_map_data_shown_at = None
        self.no_map_data_dismissed_for_miss = False
        self.apply_map_opacity()
        if self.active_map and self.active_map.get("id") == map_record.get("id") and self.map_base_image is not None:
            self.apply_map_size()
            return
        path = Path(map_record.get("image", ""))
        if not path.is_absolute():
            path = RESOURCE_DIR / path
        if not path.exists():
            return
        self.map_original_image = Image.open(path).convert("RGBA")
        self.active_map = map_record
        map_id = str(map_record.get("id", ""))
        if contributors_for_map(map_record):
            self.credit_map_id = map_id
            self.credit_started_at = time.monotonic()
            self.credit_visible_until = self.credit_started_at + 3.0
        else:
            self.credit_map_id = None
            self.credit_started_at = None
            self.credit_visible_until = 0.0
        self.apply_map_size()

    def apply_map_size(self):
        if self.map_original_image is None:
            return
        original_width = max(1, self.map_original_image.width)
        size_scale = max(0.4, min(5.0, float(self.config.get("map_size_scale", 1.0))))
        max_size = round(420 * size_scale)
        original_height = max(1, self.map_original_image.height)
        resize_ratio = max_size / max(original_width, original_height)
        resized_width = max(1, round(original_width * resize_ratio))
        resized_height = max(1, round(original_height * resize_ratio))
        image = self.map_original_image.resize((resized_width, resized_height), Image.Resampling.LANCZOS)
        self.map_scale = image.width / original_width
        black = Image.new("RGBA", image.size, (0, 0, 0, 255))
        black.alpha_composite(image)
        self.map_base_image = black
        self.map_width = image.width + 4
        self.map_height = image.height + 4
        self.map_canvas.configure(width=image.width, height=image.height)
        self.render_map()
        if self.map_window.winfo_viewable():
            self.position_map()

    def toggle_map_resize_mode(self):
        if not self.active_map:
            self.set_status("no_map_resize")
            return
        self.calibration_mode = None
        self.region_window.withdraw()
        self.map_resize_mode = not self.map_resize_mode
        set_window_click_through(self.map_window, not self.map_resize_mode)
        border_color = "#ffe000" if self.map_resize_mode else "#444444"
        self.map_canvas.configure(highlightbackground=border_color, highlightcolor=border_color)
        if self.map_resize_mode:
            self.set_status("resize_mode", "#ffe27a")
            self.render_map()
            self.show_map()
        else:
            self.render_map()
            save_config(self.config)
            if self.target_hwnd:
                user32.SetForegroundWindow(self.target_hwnd)

    def map_wheel(self, event):
        if not self.map_resize_mode:
            return
        current = int(self.config.get("map_opacity_percent", 100))
        change = 5 if event.delta > 0 else -5
        self.config["map_opacity_percent"] = max(30, min(100, current + change))
        self.apply_map_opacity()
        save_config(self.config)
        self.opacity_indicator_until = time.monotonic() + 1.0
        self.draw_adjustment_indicators()
        percent = self.config["map_opacity_percent"]
        self.set_status("opacity", "#ffe27a", percent=percent)
        return "break"

    def render_map(self):
        if self.map_base_image is None or self.no_map_data_visible:
            return
        image = self.map_base_image.copy()
        transform = self.active_map.get("transform") if self.active_map else None
        has_location_data = (
            isinstance(transform, dict)
            and isinstance(transform.get("imageX"), dict)
            and isinstance(transform.get("imageY"), dict)
        )
        if self.marker_visible and self.current_game_coordinate and self.active_map and has_location_data:
            tx = transform.get("imageX", {})
            ty = transform.get("imageY", {})
            game_x, game_y = self.current_game_coordinate
            try:
                image_x = tx["gameX"] * game_x + tx["gameY"] * game_y + tx["offset"]
                image_y = ty["gameX"] * game_x + ty["gameY"] * game_y + ty["offset"]
                px = round(image_x * self.map_scale)
                py = round(image_y * self.map_scale)
                if -10 <= px <= image.width + 10 and -10 <= py <= image.height + 10:
                    draw = ImageDraw.Draw(image)
                    radius = 7
                    draw.ellipse((px - radius, py - radius, px + radius, py + radius), fill="#ffe500", outline="#000000", width=2)
            except (KeyError, TypeError, ValueError):
                pass
        self.map_photo = ImageTk.PhotoImage(image)
        self.map_canvas.delete("all")
        self.map_canvas.create_image(0, 0, image=self.map_photo, anchor="nw")
        if self.active_map and not has_location_data:
            label = self.map_canvas.create_text(
                image.width - 7,
                image.height - 6,
                text="No location data",
                anchor="se",
                fill="#ffe36a",
                font=("Segoe UI", 8),
                tags="no_location_data",
            )
            bounds = self.map_canvas.bbox(label)
            if bounds:
                background = self.map_canvas.create_rectangle(
                    bounds[0] - 3,
                    bounds[1] - 2,
                    bounds[2] + 3,
                    bounds[3] + 2,
                    fill="#000000",
                    outline="",
                    stipple="gray50",
                    tags="no_location_data",
                )
                self.map_canvas.tag_lower(background, label)
        self.draw_contributor_credit(image.width, image.height)
        self.draw_resize_handles()
        self.draw_adjustment_indicators()

    def draw_contributor_credit(self, width, height):
        if not self.active_map:
            return
        map_id = str(self.active_map.get("id", ""))
        if map_id != self.credit_map_id or time.monotonic() >= self.credit_visible_until:
            return
        names = contributors_for_map(self.active_map)
        if not names or self.credit_started_at is None:
            return
        credit = "Charted by " + ", ".join(names)
        label = self.map_canvas.create_text(
            7,
            height - 6,
            text=credit,
            width=max(80, width - 14),
            anchor="sw",
            justify="left",
            fill=self.contributor_credit_color(),
            font=("Segoe UI", 10, "bold"),
            tags=("contributor_credit", "contributor_credit_text"),
        )
        bounds = self.map_canvas.bbox(label)
        if bounds:
            background = self.map_canvas.create_rectangle(
                bounds[0] - 3,
                bounds[1] - 2,
                bounds[2] + 3,
                bounds[3] + 2,
                fill="#000000",
                outline="",
                stipple="gray50",
                tags="contributor_credit",
            )
            self.map_canvas.tag_lower(background, label)

    def contributor_credit_color(self):
        if self.credit_started_at is None:
            return "#00ffff"
        elapsed = max(0.0, time.monotonic() - self.credit_started_at)
        colors = ((0, 255, 255), (255, 0, 255), (255, 255, 0))
        phase = (elapsed % 1.8) / 0.6
        index = int(phase) % 3
        fraction = phase - int(phase)
        start = colors[index]
        end = colors[(index + 1) % 3]
        rgb = [
            round(start[channel] + (end[channel] - start[channel]) * fraction)
            for channel in range(3)
        ]
        remaining = self.credit_visible_until - time.monotonic()
        if remaining < 0.5:
            fade = max(0.0, remaining / 0.5)
            rgb = [round(value * fade) for value in rgb]
        return "#{:02x}{:02x}{:02x}".format(*rgb)

    def draw_resize_handles(self):
        self.map_canvas.delete("resize_handle")
        if not self.map_resize_mode or self.no_map_data_visible:
            return
        width = max(1, int(float(self.map_canvas.cget("width"))))
        height = max(1, int(float(self.map_canvas.cget("height"))))
        size = 10
        x = width - size
        y = height - size
        self.map_canvas.create_rectangle(
            x,
            y,
            x + size,
            y + size,
            fill="#ffe000",
            outline="#000000",
            tags="resize_handle",
        )

    def draw_adjustment_indicators(self):
        self.map_canvas.delete("scale_indicator")
        self.map_canvas.delete("opacity_indicator")
        now = time.monotonic()
        if now < self.opacity_indicator_until:
            self.draw_corner_indicator(
                f"{int(self.config.get('map_opacity_percent', 100))}%",
                8,
                "nw",
                "opacity_indicator",
            )
        if now < self.scale_indicator_until and not self.no_map_data_visible:
            width = int(float(self.map_canvas.cget("width")))
            self.draw_corner_indicator(
                f"{round(float(self.config.get('map_size_scale', 1.0)) * 100)}%",
                width - 8,
                "ne",
                "scale_indicator",
            )

    def draw_corner_indicator(self, text, x, anchor, tag):
        text_id = self.map_canvas.create_text(
            x,
            18,
            text=text,
            anchor=anchor,
            fill="#ffe000",
            font=("맑은 고딕", 10, "bold"),
            tags=tag,
        )
        box = self.map_canvas.bbox(text_id)
        if box:
            background = self.map_canvas.create_rectangle(
                box[0] - 4,
                box[1] - 2,
                box[2] + 4,
                box[3] + 2,
                fill="#000000",
                outline="#666666",
                tags=tag,
            )
            self.map_canvas.tag_lower(background, text_id)

    def apply_map_opacity(self):
        percent = max(30, min(100, int(self.config.get("map_opacity_percent", 100))))
        self.config["map_opacity_percent"] = percent
        self.map_window.attributes("-alpha", percent / 100.0)

    def show_no_map_data(self):
        if self.no_map_data_dismissed_for_miss:
            return
        if not self.no_map_data_visible:
            size_scale = 0.5
            width = round(680 * size_scale)
            height = round(280 * size_scale)
            self.map_width = width
            self.map_height = height
            self.map_canvas.configure(width=width - 4, height=height - 4)
            self.map_canvas.delete("all")
            self.map_canvas.create_rectangle(0, 0, width, height, fill="#000000", outline="")
            self.map_canvas.create_text(
                0,
                height / 2,
                text="No Map Data",
                fill="#ffe000",
                font=("Segoe UI", 15, "bold"),
                anchor="w",
                tags="no_map_base",
            )
            self.map_canvas.create_text(
                0,
                height / 2,
                text="...",
                fill="#ffe000",
                font=("Segoe UI", 15, "bold"),
                anchor="w",
                tags="no_map_dots",
            )
            base_box = self.map_canvas.bbox("no_map_base")
            dots_box = self.map_canvas.bbox("no_map_dots")
            base_width = base_box[2] - base_box[0] if base_box else 140
            dots_width = dots_box[2] - dots_box[0] if dots_box else 24
            gap = 3
            start_x = (width - base_width - gap - dots_width) / 2
            self.map_canvas.coords("no_map_base", start_x, height / 2)
            self.map_canvas.coords("no_map_dots", start_x + base_width + gap, height / 2)
            self.map_canvas.itemconfigure("no_map_dots", text=".")
            self.apply_map_opacity()
            self.no_map_data_visible = True
            self.no_map_data_shown_at = time.monotonic()
            self.last_no_map_animation_at = self.no_map_data_shown_at
            self.no_map_animation_step = 1
        self.show_map()

    def map_pointer_motion(self, event):
        if self.map_resize_mode and not self.no_map_data_visible:
            corner = self.corner_at(event.x, event.y)
            if corner == "br":
                self.map_canvas.configure(cursor="size_nw_se")
                return
        self.map_canvas.configure(cursor="fleur")

    def corner_at(self, x, y):
        margin = 18
        width = self.map_canvas.winfo_width()
        height = self.map_canvas.winfo_height()
        return "br" if x >= width - margin and y >= height - margin else None

    def map_press(self, event):
        if not self.map_resize_mode:
            return
        corner = self.corner_at(event.x, event.y) if self.map_resize_mode and not self.no_map_data_visible else None
        if corner:
            x = self.map_window.winfo_x()
            y = self.map_window.winfo_y()
            self.map_resizing = True
            self.map_resize_corner = corner
            self.map_resize_anchor = {
                "tl": (x + self.map_width, y + self.map_height),
                "tr": (x, y + self.map_height),
                "bl": (x + self.map_width, y),
                "br": (x, y),
            }[corner]
            self.map_resize_start_scale = float(self.config.get("map_size_scale", 1.0))
            self.map_resize_start_size = (self.map_width, self.map_height)
            return
        self.map_dragging = True
        self.map_drag_start = (event.x_root, event.y_root)
        self.map_drag_origin = (self.map_window.winfo_x(), self.map_window.winfo_y())

    def map_drag(self, event):
        if self.map_resizing and self.map_resize_anchor and self.map_resize_start_size:
            anchor_x, anchor_y = self.map_resize_anchor
            start_width, start_height = self.map_resize_start_size
            desired_width = event.x_root - anchor_x
            desired_height = event.y_root - anchor_y
            start_diagonal = max(1.0, (start_width**2 + start_height**2) ** 0.5)
            ratio = (desired_width**2 + desired_height**2) ** 0.5 / start_diagonal
            self.config["map_size_scale"] = round(max(0.4, min(5.0, self.map_resize_start_scale * ratio)), 4)
            self.scale_indicator_until = time.monotonic() + 1.0
            self.apply_map_size()
            if "l" in self.map_resize_corner:
                x = anchor_x - self.map_width
            else:
                x = anchor_x
            if "t" in self.map_resize_corner:
                y = anchor_y - self.map_height
            else:
                y = anchor_y
            self.map_window.geometry(f"{self.map_width}x{self.map_height}+{round(x)}+{round(y)}")
            percent = round(self.config["map_size_scale"] * 100)
            self.set_status("size", "#ffe27a", percent=percent)
            return
        if not self.map_dragging or not self.map_drag_start or not self.map_drag_origin:
            return
        dx = event.x_root - self.map_drag_start[0]
        dy = event.y_root - self.map_drag_start[1]
        x = self.map_drag_origin[0] + dx
        y = self.map_drag_origin[1] + dy
        client = self.get_stable_client_rect()
        if client:
            left, top, right, bottom = client
            x = max(left, min(x, right - self.map_width))
            y = max(top, min(y, bottom - self.map_height))
        self.map_window.geometry(f"{self.map_width}x{self.map_height}+{round(x)}+{round(y)}")

    def map_release(self, _event):
        if self.map_resizing:
            self.map_resizing = False
            self.map_resize_corner = None
            self.map_resize_anchor = None
            self.map_resize_start_scale = None
            self.map_resize_start_size = None
            self.save_map_position()
            save_config(self.config)
            self.draw_resize_handles()
            return
        if not self.map_dragging:
            return
        self.save_map_position()
        save_config(self.config)
        self.map_dragging = False
        self.map_drag_start = None
        self.map_drag_origin = None

    def save_map_position(self):
        client = self.get_stable_client_rect()
        if client:
            self.config["map_offset_x"] = self.map_window.winfo_x() - client[0]
            self.config["map_offset_y"] = self.map_window.winfo_y() - client[1]

    def create_region_window(self):
        win = tk.Toplevel(self.root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.attributes("-alpha", 0.62)
        win.configure(bg="#ff00ff")
        win.wm_attributes("-transparentcolor", "#ff00ff")
        canvas = tk.Canvas(win, bg="#ff00ff", highlightthickness=0, cursor="fleur")
        canvas.pack(fill="both", expand=True)
        canvas.bind("<ButtonPress-1>", self.region_press)
        canvas.bind("<B1-Motion>", self.region_drag)
        canvas.bind("<ButtonRelease-1>", self.region_release)
        canvas.bind("<Motion>", self.region_pointer_motion)
        canvas.bind("<Leave>", lambda _event: canvas.configure(cursor="fleur"))
        win.withdraw()
        set_noactivate_toolwindow(win)
        return win

    def find_target(self):
        if self.target_hwnd and get_client_screen_rect(self.target_hwnd):
            return self.target_hwnd
        self.target_hwnd = find_target_window(self.config["process_name"], self.config["window_title"])
        self.stable_client_rect = None
        self.pending_client_rect = None
        self.pending_client_rect_hits = 0
        return self.target_hwnd

    def can_capture_game(self):
        foreground = user32.GetForegroundWindow()
        if not foreground:
            return False
        if process_name_for_hwnd(foreground).lower() == self.config["process_name"].lower():
            return True
        if self.map_resize_mode:
            map_root = user32.GetAncestor(self.map_window.winfo_id(), GA_ROOT) or self.map_window.winfo_id()
            return foreground == map_root
        return False

    def is_target_foreground(self):
        if not self.target_hwnd:
            return False
        foreground = user32.GetForegroundWindow()
        if not foreground:
            return False
        foreground_root = user32.GetAncestor(foreground, GA_ROOT) or foreground
        target_root = user32.GetAncestor(self.target_hwnd, GA_ROOT) or self.target_hwnd
        if foreground_root == target_root:
            return True
        if self.map_resize_mode:
            map_root = user32.GetAncestor(self.map_window.winfo_id(), GA_ROOT) or self.map_window.winfo_id()
            return foreground_root == map_root
        if self.calibration_mode:
            region_root = user32.GetAncestor(self.region_window.winfo_id(), GA_ROOT) or self.region_window.winfo_id()
            return foreground_root == region_root
        return False

    def reload_map_database_if_changed(self):
        modified = map_database_signature()
        if modified == self.map_database_state:
            return
        self.map_database_state = modified
        updated_maps = load_map_database()
        active_id = self.active_map.get("id") if self.active_map else None
        self.maps = updated_maps
        if active_id:
            updated_active = next((item for item in self.maps if item.get("id") == active_id), None)
            if updated_active:
                self.active_map = updated_active
            else:
                self.active_map = None
                self.current_game_coordinate = None
                self.hide_map()

    def get_stable_client_rect(self):
        raw = get_client_screen_rect(self.target_hwnd)
        if not raw:
            return self.stable_client_rect
        if self.stable_client_rect is None:
            self.stable_client_rect = raw
            return raw

        difference = max(abs(raw[i] - self.stable_client_rect[i]) for i in range(4))
        if difference <= 3:
            self.stable_client_rect = raw
            self.pending_client_rect = None
            self.pending_client_rect_hits = 0
            return raw

        # A genuine move/resize remains stable for multiple 50 ms ticks. A
        # single bad ClientToScreen result is ignored and never reaches OCR.
        if self.pending_client_rect and max(abs(raw[i] - self.pending_client_rect[i]) for i in range(4)) <= 3:
            self.pending_client_rect_hits += 1
        else:
            self.pending_client_rect = raw
            self.pending_client_rect_hits = 1

        if self.pending_client_rect_hits >= 3:
            self.stable_client_rect = raw
            self.pending_client_rect = None
            self.pending_client_rect_hits = 0
        return self.stable_client_rect

    def current_bbox(self, kind="name", allow_default=False):
        hwnd = self.find_target()
        client = self.get_stable_client_rect()
        if not client:
            return None
        left, top, right, bottom = client
        client_w = right - left
        client_h = bottom - top
        region_key = "coordinate_region" if kind == "coordinates" else "capture_region"
        reference_key = "coordinate_reference_size" if kind == "coordinates" else "capture_reference_size"
        region = self.config.get(region_key)
        reference = self.config.get(reference_key)
        if not region or len(region) != 4 or not reference or len(reference) != 2:
            if not allow_default:
                return None
            width = min(480, max(160, int(client_w * (0.30 if kind == "coordinates" else 0.45))))
            height = 70 if kind == "coordinates" else 90
            x = left + (client_w - width) // 2
            y = top + (max(20, int(client_h * 0.85)) if kind == "coordinates" else max(20, int(client_h * 0.06)))
            return x, y, x + width, y + height
        sx = client_w / max(1, reference[0])
        sy = client_h / max(1, reference[1])
        return (
            left + round(region[0] * sx),
            top + round(region[1] * sy),
            left + round(region[2] * sx),
            top + round(region[3] * sy),
        )

    def store_bbox(self, bbox, kind=None):
        client = self.get_stable_client_rect()
        if not client:
            return
        cl, ct, cr, cb = client
        left, top, right, bottom = bbox
        left = max(cl, min(left, cr - 40))
        top = max(ct, min(top, cb - 24))
        right = max(left + 40, min(right, cr))
        bottom = max(top + 24, min(bottom, cb))
        kind = kind or self.calibration_mode or "name"
        region_key = "coordinate_region" if kind == "coordinates" else "capture_region"
        reference_key = "coordinate_reference_size" if kind == "coordinates" else "capture_reference_size"
        self.config[region_key] = [left - cl, top - ct, right - cl, bottom - ct]
        self.config[reference_key] = [cr - cl, cb - ct]
        save_config(self.config)

    def toggle_calibration(self, kind):
        if not self.find_target():
            self.set_status("target_missing", "#ff7777")
            return
        if self.map_resize_mode:
            self.map_resize_mode = False
            self.map_canvas.configure(highlightbackground="#444444", highlightcolor="#444444")
            set_window_click_through(self.map_window, True)
            self.render_map()
            if self.target_hwnd:
                user32.SetForegroundWindow(self.target_hwnd)
            save_config(self.config)
        if self.calibration_mode == kind:
            bbox = self.capture_bbox or self.current_bbox(kind, allow_default=True)
            if bbox:
                self.store_bbox(bbox, kind)
            self.calibration_mode = None
            self.region_window.withdraw()
        else:
            self.calibration_mode = kind
            self.capture_bbox = self.current_bbox(kind, allow_default=True)
            self.hide_map()
            self.update_region_window()

    def update_region_window(self):
        kind = self.calibration_mode or "name"
        bbox = self.current_bbox(kind, allow_default=True)
        if not bbox:
            return
        self.capture_bbox = bbox
        left, top, right, bottom = bbox
        width = max(40, right - left)
        height = max(24, bottom - top)
        self.region_window.geometry(f"{width}x{height}+{left}+{top}")
        canvas = self.region_window.winfo_children()[0]
        canvas.configure(width=width, height=height)
        canvas.delete("all")
        color = "#ffd400" if kind == "coordinates" else "#ff3535"
        fill = "#947d00" if kind == "coordinates" else "#b51f1f"
        canvas.create_rectangle(2, 2, width - 3, height - 3, outline=color, fill=fill, width=4)
        handle = 12
        x = width - handle - 2
        y = height - handle - 2
        canvas.create_oval(x, y, x + handle, y + handle, fill="white", outline=color, width=2)
        self.region_window.deiconify()
        keep_topmost(self.region_window)

    def region_press(self, event):
        width = max(1, self.region_window.winfo_width())
        height = max(1, self.region_window.winfo_height())
        margin = 24
        right = event.x >= width - margin
        bottom = event.y >= height - margin
        self.drag_kind = "br" if right and bottom else "move"
        self.drag_start = (event.x_root, event.y_root)
        self.drag_bbox = self.capture_bbox or self.current_bbox(self.calibration_mode or "name", allow_default=True)

    def region_pointer_motion(self, event):
        width = max(1, self.region_window.winfo_width())
        height = max(1, self.region_window.winfo_height())
        if event.x >= width - 24 and event.y >= height - 24:
            event.widget.configure(cursor="size_nw_se")
        else:
            event.widget.configure(cursor="fleur")

    def region_drag(self, event):
        if not self.drag_start or not self.drag_bbox:
            return
        dx = event.x_root - self.drag_start[0]
        dy = event.y_root - self.drag_start[1]
        l, t, r, b = self.drag_bbox
        if self.drag_kind == "move":
            l, t, r, b = l + dx, t + dy, r + dx, b + dy
        else:
            if "l" in self.drag_kind:
                l = min(l + dx, r - 40)
            if "r" in self.drag_kind:
                r = max(r + dx, l + 40)
            if "t" in self.drag_kind:
                t = min(t + dy, b - 24)
            if "b" in self.drag_kind:
                b = max(b + dy, t + 24)
        self.capture_bbox = (round(l), round(t), round(r), round(b))
        self.store_bbox(self.capture_bbox, self.calibration_mode)
        self.update_region_window()

    def region_release(self, _event):
        if self.capture_bbox:
            self.store_bbox(self.capture_bbox, self.calibration_mode)
        self.drag_start = None
        self.drag_bbox = None
        self.drag_kind = None

    def capture_and_submit(self):
        name_bbox = self.current_bbox("name")
        coordinate_bbox = self.current_bbox("coordinates")
        if not name_bbox:
            self.set_status("need_name_region")
            return
        if not coordinate_bbox:
            self.set_status("need_coordinate_region")
            return


        def overlaps(first, second):
            return first[0] < second[2] and first[2] > second[0] and first[1] < second[3] and first[3] > second[1]

        self.root.update_idletasks()
        debug_rect = (
            self.root.winfo_rootx(),
            self.root.winfo_rooty(),
            self.root.winfo_rootx() + self.root.winfo_width(),
            self.root.winfo_rooty() + self.root.winfo_height(),
        )
        if overlaps(debug_rect, name_bbox) or overlaps(debug_rect, coordinate_bbox):
            self.set_status("debug_overlap", "#ff7777")
            return
        if self.map_window.winfo_viewable():
            map_rect = (
                self.map_window.winfo_rootx(),
                self.map_window.winfo_rooty(),
                self.map_window.winfo_rootx() + self.map_window.winfo_width(),
                self.map_window.winfo_rooty() + self.map_window.winfo_height(),
            )
            if overlaps(map_rect, name_bbox) or overlaps(map_rect, coordinate_bbox):
                self.set_status("map_overlap", "#ff7777")
                return
        client = self.get_stable_client_rect()
        if not client:
            return
        try:
            if self.desktop_camera is not None:
                array = self.desktop_camera.grab(
                    region=tuple(int(value) for value in client),
                    new_frame_only=False,
                )
                if array is None:
                    return
                client_frame = Image.fromarray(array, mode="RGB")
            else:
                client_frame = ImageGrab.grab(bbox=client).convert("RGB")
        except Exception as exc:
            self.set_status("capture_failed", "#ff7777", backend=self.capture_backend, error=exc)
            return

        client_left, client_top, _client_right, _client_bottom = client

        def crop_from_client(bbox):
            left = max(0, round(bbox[0] - client_left))
            top = max(0, round(bbox[1] - client_top))
            right = min(client_frame.width, round(bbox[2] - client_left))
            bottom = min(client_frame.height, round(bbox[3] - client_top))
            if right <= left or bottom <= top:
                raise ValueError("OCR 영역이 게임 클라이언트 밖에 있습니다.")
            return client_frame.crop((left, top, right, bottom))

        try:
            name_capture = crop_from_client(name_bbox)
            coordinate_capture = crop_from_client(coordinate_bbox)
        except ValueError as exc:
            self.set_status("error", "#ff7777", error=exc)
            return


        def is_black_frame(image):
            grayscale = image.convert("L")
            low, high = grayscale.getextrema()
            return high <= 4 or (high - low <= 2 and high <= 8)

        if is_black_frame(name_capture) or is_black_frame(coordinate_capture):
            self.set_status("black_frame")
            return

        preview_width = max(name_capture.width, coordinate_capture.width)
        preview = Image.new("RGB", (preview_width, name_capture.height + coordinate_capture.height + 2), "black")
        preview.paste(name_capture, (0, 0))
        preview.paste(coordinate_capture, (0, name_capture.height + 2))
        preview.thumbnail((490, 110), Image.Resampling.NEAREST)
        self.preview_photo = ImageTk.PhotoImage(preview)
        self.preview_label.configure(image=self.preview_photo, height=110)

        def prepare(capture):
            enlarged = capture.resize((capture.width * 4, capture.height * 4), Image.Resampling.NEAREST)
            enlarged = ImageEnhance.Contrast(enlarged).enhance(1.8)
            return ImageOps.autocontrast(enlarged)

        if self.ocr_backend_name == "paddle":
            name_input = name_capture
            coordinate_input = coordinate_capture
        else:
            name_input = prepare(name_capture)
            coordinate_input = prepare(coordinate_capture)

        self.ocr_running = True
        future = self.executor.submit(self.ocr.recognize_multilingual, name_input, coordinate_input)
        future.add_done_callback(lambda result: self.root.after(0, self.finish_ocr, result))

    def finish_ocr(self, future):
        self.ocr_running = False
        if self.closed:
            return
        try:
            name_results, coordinate_text = future.result()
        except Exception as exc:
            for label in self.ocr_result_labels.values():
                label.configure(text="OCR 오류")
            self.set_status("error", "#ff7777", error=exc)
            return

        matched_map, matched_language, match_score = find_best_map_match(name_results, self.maps, self.active_map)
        valid_locale = debug_valid_locale(name_results, matched_language, match_score)
        for language_key in ("ko", "ja", "en"):
            display_text = name_results.get(language_key)
            if valid_locale and language_key != valid_locale:
                display_text = "invalid"
            self.ocr_result_labels[language_key].configure(text=display_text or "(No data)")
        self.ocr_result_labels["coordinates"].configure(text=coordinate_text or "(No data)")

        if matched_map:
            self.map_miss_started_at = None
            matched_id = matched_map.get("id")
            active_id = self.active_map.get("id") if self.active_map else None
            if matched_id == active_id:
                self.pending_map_id = None
                self.pending_map_hits = 0
            elif matched_id == self.pending_map_id:
                self.pending_map_hits += 1
            else:
                self.pending_map_id = matched_id
                self.pending_map_hits = 1

            # Require two consecutive readings before initially selecting or
            # changing a map. An OCR miss never clears an already selected map.
            if matched_id == active_id or self.pending_map_hits >= 2:
                self.last_map_match_at = time.monotonic()
                self.set_active_map(matched_map)
                self.pending_map_id = None
                self.pending_map_hits = 0
                names = matched_map.get("names", {})
                preferred_names = names.get(matched_language, [])
                display_name = next(
                    (values[0] for values in (preferred_names, names.get("ko", []), names.get("ja", []), names.get("en", [])) if values),
                    matched_map.get("id", "맵"),
                )
                self.set_status(
                    "confirmed",
                    "#6df0ae",
                    name=display_name,
                    language=matched_language.upper(),
                    score=match_score,
                )
                self.show_map()
            else:
                self.set_status("confirming")
        else:
            self.pending_map_id = None
            self.pending_map_hits = 0
            now = time.monotonic()
            if self.map_miss_started_at is None:
                self.map_miss_started_at = now
            miss_seconds = now - self.map_miss_started_at
            if miss_seconds >= 5.0:
                self.set_status("no_map_data")
                self.show_no_map_data()
            elif self.active_map:
                self.set_status("temporary_miss")
                self.show_map()
            else:
                self.set_status("finding_map")

        numbers = re.findall(r"-?\d+", coordinate_text.replace(",", " ").replace(":", " "))
        if len(numbers) >= 2:
            self.current_game_coordinate = (int(numbers[0]), int(numbers[1]))
            self.last_coordinate_at = time.monotonic()
            self.render_map()

    def position_map(self):
        if self.map_dragging or self.map_resizing:
            return
        client = self.get_stable_client_rect()
        if not client:
            return
        left, top, right, bottom = client
        margin = 12
        offset_x = self.config.get("map_offset_x")
        offset_y = self.config.get("map_offset_y")
        if offset_x is None or offset_y is None:
            x = left + margin
            y = bottom - self.map_height - margin
        else:
            x = left + int(offset_x)
            y = top + int(offset_y)
        x = max(left, min(x, right - self.map_width))
        y = max(top, min(y, bottom - self.map_height))
        self.map_window.geometry(f"{self.map_width}x{self.map_height}+{round(x)}+{round(y)}")

    def show_map(self):
        self.position_map()
        show_above_owner(self.map_window, self.target_hwnd)
        # Deiconify/owner changes can cause Tk or Windows to rebuild extended
        # styles, so enforce the correct input behavior after every show.
        set_window_click_through(self.map_window, not self.map_resize_mode)

    def hide_map(self):
        if self.map_window.winfo_viewable():
            self.map_window.withdraw()

    def tick(self):
        if self.closed:
            return
        self.reload_map_database_if_changed()
        self.find_target()
        toggle_down = self.is_target_foreground() and is_toggle_key_down()
        if toggle_down and not self.last_toggle_down:
            shift_down = bool(user32.GetAsyncKeyState(VK_SHIFT) & 0x8000)
            control_down = bool(user32.GetAsyncKeyState(VK_CONTROL) & 0x8000)
            if control_down:
                self.toggle_map_resize_mode()
            else:
                self.toggle_calibration("coordinates" if shift_down else "name")
        self.last_toggle_down = toggle_down

        if self.calibration_mode:
            self.update_region_window()
        elif not self.target_hwnd:
            self.set_status("target_missing", "#ff7777")
            self.hide_map()
        elif user32.IsIconic(self.target_hwnd):
            self.set_status("minimized")
            self.hide_map()
        elif not self.can_capture_game():
            self.set_status("other_foreground")
        elif not self.ocr_running:
            now = time.monotonic()
            interval = max(0.1, int(self.config["ocr_interval_ms"]) / 1000.0)
            if now - self.last_ocr_at >= interval:
                self.last_ocr_at = now
                self.capture_and_submit()

        if self.map_window.winfo_viewable() and self.target_hwnd:
            self.position_map()

        now = time.monotonic()
        if self.update_future is not None and self.update_future.done():
            self.finish_update_task()
        if self.app_update_future is not None and self.app_update_future.done():
            self.finish_app_update_check()
        if self.update_banner_state == "downloading":
            displayed_percent = self.update_banner_values.get("percent", -1)
            if displayed_percent != self.update_progress_percent:
                self.show_update_banner("downloading", percent=self.update_progress_percent)
        if self.update_banner_until and now >= self.update_banner_until:
            self.hide_update_banner()
        if self.credit_visible_until:
            if now >= self.credit_visible_until:
                self.credit_visible_until = 0.0
                self.map_canvas.delete("contributor_credit")
            elif self.map_window.winfo_viewable():
                self.map_canvas.itemconfigure(
                    "contributor_credit_text",
                    fill=self.contributor_credit_color(),
                )
        if self.opacity_indicator_until and now >= self.opacity_indicator_until:
            self.opacity_indicator_until = 0.0
            self.map_canvas.delete("opacity_indicator")
        if self.scale_indicator_until and now >= self.scale_indicator_until:
            self.scale_indicator_until = 0.0
            self.map_canvas.delete("scale_indicator")

        if self.no_map_data_visible and self.no_map_data_shown_at is not None:
            if now - self.no_map_data_shown_at >= 5.0:
                self.no_map_data_visible = False
                self.no_map_data_shown_at = None
                self.no_map_data_dismissed_for_miss = True
                self.hide_map()
            elif now - self.last_no_map_animation_at >= 0.45:
                self.last_no_map_animation_at = now
                self.no_map_animation_step = self.no_map_animation_step % 3 + 1
                self.map_canvas.itemconfigure("no_map_dots", text="." * self.no_map_animation_step)

        if now - self.last_marker_blink_at >= 0.5:
            self.last_marker_blink_at = now
            self.marker_visible = not self.marker_visible
            if self.map_window.winfo_viewable():
                self.render_map()

        self.root.after(50, self.tick)

    def quit(self):
        self.closed = True
        self.config["debug_x"] = self.root.winfo_x()
        self.config["debug_y"] = self.root.winfo_y()
        if self.map_window.winfo_exists():
            self.config["map_x"] = self.map_window.winfo_x()
            self.config["map_y"] = self.map_window.winfo_y()
        save_config(self.config)
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.update_executor.shutdown(wait=False, cancel_futures=True)
        self.app_update_executor.shutdown(wait=False, cancel_futures=True)
        if self.desktop_camera is not None:
            try:
                self.desktop_camera.release()
            except Exception:
                pass
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def main():
    if sys.platform != "win32":
        raise SystemExit("This overlay is Windows-only.")
    mutex = kernel32.CreateMutexW(None, False, "Local\\GodimapOcrDebug.SingleInstance")
    if not mutex or ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        language = load_config().get("ui_language", "EN")
        message = {
            "KR": "GODIMAP이 이미 실행 중입니다.",
            "JP": "GODIMAPは既に実行中です。",
            "EN": "GODIMAP is already running.",
        }[language]
        ctypes.windll.user32.MessageBoxW(None, message, "GODIMAP", 0x40)
        return
    try:
        GodimapOcrDebug().run()
    finally:
        kernel32.CloseHandle(mutex)


if __name__ == "__main__":
    main()
