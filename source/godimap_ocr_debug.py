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
VK_MENU = 0x12

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
    "world_map_size_scale": 1.0,
    "world_map_opacity_percent": 100,
    "ocr_interval_ms": 700,
    "map_match_hold_seconds": 2.0,
    "ui_language": None,
    "ocr_backend": "paddle",
    "ignored_app_update_version": None,
    "favorites": {"KR": [], "JP": []},
    "favorite_overlay_visible": False,
    "favorite_overlay_offset_x": None,
    "favorite_overlay_offset_y": None,
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
    "need_name_region": {"KR": "Shift+F11을 눌러 맵 이름 영역을 저장해 주세요.", "JP": "Shift+F11を押して、マップ名の範囲を保存してください。", "EN": "Press Shift+F11 and save the map-name region."},
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
    "world_map_open": {"KR": "월드맵 표시 중 · F11로 닫기", "JP": "ワールドマップを表示中・F11で閉じる", "EN": "World map displayed · F11 to close"},
    "world_map_missing": {"KR": "월드맵 이미지를 찾을 수 없습니다: maps/other/worldmap.jpg", "JP": "ワールドマップ画像が見つかりません: maps/other/worldmap.jpg", "EN": "World map image not found: maps/other/worldmap.jpg"},
    "world_resize_mode": {"KR": "월드맵 조정 중 · 우측 하단 손잡이/마우스 휠 · Ctrl+F11로 완료", "JP": "ワールドマップ調整中・右下ハンドル／マウスホイール・Ctrl+F11で完了", "EN": "Adjusting world map · Bottom-right handle/mouse wheel · Ctrl+F11 to finish"},
    "world_opacity": {"KR": "월드맵 불투명도 {percent}%", "JP": "ワールドマップ不透明度 {percent}%", "EN": "World map opacity {percent}%"},
    "world_size": {"KR": "월드맵 크기 {percent}%", "JP": "ワールドマップサイズ {percent}%", "EN": "World map size {percent}%"},
}

SECTION_LABELS = {
    "KR": {"ocr": "OCR", "recognized": "인식된 내용", "status": "상태", "favorites": "즐겨찾기"},
    "JP": {"ocr": "OCR", "recognized": "認識結果", "status": "状態", "favorites": "お気に入り"},
    "EN": {"ocr": "OCR", "recognized": "Recognized Content", "status": "Status", "favorites": "Favorites"},
}

FAVORITE_TEXTS = {
    "KR": {
        "register": "등록", "show": "표시", "hide": "비표시", "edit": "편집", "done": "완료",
        "title": "즐겨찾기 등록", "map_list": "맵 목록", "registered": "등록된 장소",
        "overlay_label": "오버레이 글자", "destination": "이동할 맵 이름", "command": "복사될 명령어",
        "add": "등록", "update": "내용 수정", "delete": "삭제", "close": "닫기",
        "empty": "등록된 장소가 없습니다. 먼저 장소를 등록해주세요.",
        "show_first": "먼저 오버레이를 켜주세요.", "limit": "즐겨찾기는 최대 5개까지 등록할 수 있습니다.",
        "select_map": "왼쪽 맵 목록에서 장소를 선택하거나 이동할 맵 이름을 입력해주세요.",
        "invalid": "영어 환경에서는 즐겨찾기 기능을 사용할 수 없습니다.",
        "map_name": "맵 이름", "label": "표시", "saved": "즐겨찾기를 저장했습니다.",
        "search": "맵 이름 검색",
    },
    "JP": {
        "register": "登録", "show": "表示", "hide": "非表示", "edit": "編集", "done": "完了",
        "title": "お気に入り登録", "map_list": "マップ一覧", "registered": "登録済みの場所",
        "overlay_label": "オーバーレイ文字", "destination": "移動先のマップ名", "command": "コピーするコマンド",
        "add": "登録", "update": "内容を変更", "delete": "削除", "close": "閉じる",
        "empty": "登録された場所がありません。先に場所を登録してください。",
        "show_first": "先にオーバーレイを表示してください。", "limit": "お気に入りは最大5件まで登録できます。",
        "select_map": "左のマップ一覧から場所を選ぶか、移動先のマップ名を入力してください。",
        "invalid": "英語環境ではお気に入り機能を利用できません。",
        "map_name": "マップ名", "label": "表示", "saved": "お気に入りを保存しました。",
        "search": "マップ名を検索",
    },
    "EN": {
        "register": "Register", "show": "Show", "hide": "Hide", "edit": "Edit", "done": "Done",
        "title": "Favorites", "map_list": "Map list", "registered": "Registered places",
        "overlay_label": "Overlay label", "destination": "Destination map name", "command": "Command to copy",
        "add": "Register", "update": "Update", "delete": "Delete", "close": "Close",
        "empty": "No places are registered. Register a place first.", "show_first": "Show the overlay first.",
        "limit": "Up to five favorites can be registered.", "select_map": "Select a map or enter a destination.",
        "invalid": "Favorites are unavailable in the English interface.",
        "map_name": "Map name", "label": "Label", "saved": "Favorites saved.",
        "search": "Search map names",
    },
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
        favorites = self.config.get("favorites")
        if not isinstance(favorites, dict):
            favorites = {}
        self.config["favorites"] = {
            language: list(favorites.get(language, []))[:5] if isinstance(favorites.get(language, []), list) else []
            for language in ("KR", "JP")
        }
        self.current_status_key = "searching"
        self.current_status_values = {}
        self.current_status_color = "#ffd066"
        self.maps = load_map_database()
        self.synchronize_favorite_locales()
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
        self.capture_bboxes = {"name": None, "coordinates": None}
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
        self.world_map_mode = False
        self.world_map_original_image = None
        self.world_map_photo = None
        self.world_map_scale = 1.0
        self.world_map_render_key = None
        self.favorite_overlay_editing = False
        self.favorite_drag_start = None
        self.favorite_drag_origin = None
        self.favorite_copied_index = None
        self.favorite_copied_after_id = None
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

        add_section_label("favorites")
        favorite_bar = tk.Frame(self.root, bg="#15191f")
        favorite_bar.pack(fill="x", padx=12, pady=(4, 10))
        self.favorite_buttons = {}
        for key, command in (
            ("register", self.open_favorite_dialog),
            ("show", self.toggle_favorite_overlay),
            ("edit", self.toggle_favorite_edit_mode),
        ):
            button = tk.Button(
                favorite_bar,
                text=FAVORITE_TEXTS[self.ui_language][key],
                command=command,
                bg="#3b4652",
                fg="white",
                activebackground="#586675",
                activeforeground="white",
                relief="flat",
                padx=14,
            )
            button.pack(side="left", padx=(0, 6))
            self.favorite_buttons[key] = button

        self.root.update_idletasks()
        required_height = self.root.winfo_reqheight() + 8
        fitted_height = min(self.root.winfo_screenheight() - 80, max(debug_height, required_height))
        fitted_y = max(0, min(debug_y, self.root.winfo_screenheight() - fitted_height))
        self.root.geometry(f"{debug_width}x{fitted_height}+{debug_x}+{fitted_y}")
        self.root.minsize(560, min(fitted_height, required_height))

        self.preview_photo = None
        self.map_photo = None
        self.region_window = self.create_region_window("name")
        self.coordinate_region_window = self.create_region_window("coordinates")
        self.map_window = self.create_map_window()
        self.favorite_window = self.create_favorite_overlay()
        self.refresh_favorite_controls()
        self.drag_region_kind = None
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
        self.refresh_favorite_controls()
        self.rebuild_favorite_overlay()

    def favorite_text(self, key):
        return FAVORITE_TEXTS[self.ui_language][key]

    def favorite_entries(self):
        if self.ui_language not in ("KR", "JP"):
            return []
        return self.config["favorites"][self.ui_language]

    def favorite_command(self, destination, language=None):
        language = language or self.ui_language
        prefix = "/이동 " if language == "KR" else "/MOVE "
        return prefix + destination.strip()

    def preferred_map_name(self, map_record, language=None):
        language = language or self.ui_language
        language_key = "ko" if language == "KR" else "ja"
        names = map_record.get("names", {}).get(language_key, [])
        if not isinstance(names, list):
            names = [names]
        return next((str(name).strip() for name in names if str(name).strip()), "")

    def find_map_for_favorite(self, item):
        map_id = str(item.get("map_id", "")).strip() if isinstance(item, dict) else ""
        if map_id:
            matched = next((record for record in self.maps if str(record.get("id", "")) == map_id), None)
            if matched:
                return matched
        destination = str(item.get("destination", "")).strip() if isinstance(item, dict) else ""
        if not destination:
            return None
        for record in self.maps:
            for language_key in ("ko", "ja"):
                names = record.get("names", {}).get(language_key, [])
                if not isinstance(names, list):
                    names = [names]
                if any(str(name).strip() == destination for name in names):
                    return record
        return None

    def synchronize_favorite_locales(self):
        favorites = self.config["favorites"]
        kr_items = favorites["KR"]
        jp_items = favorites["JP"]
        pair_count = min(5, max(len(kr_items), len(jp_items)))
        synchronized = {"KR": [], "JP": []}
        for index in range(pair_count):
            kr_item = dict(kr_items[index]) if index < len(kr_items) and isinstance(kr_items[index], dict) else {}
            jp_item = dict(jp_items[index]) if index < len(jp_items) and isinstance(jp_items[index], dict) else {}
            map_record = self.find_map_for_favorite(kr_item) or self.find_map_for_favorite(jp_item)
            map_id = str(map_record.get("id", "")) if map_record else str(kr_item.get("map_id") or jp_item.get("map_id") or "")
            for language, item, other_item in (("KR", kr_item, jp_item), ("JP", jp_item, kr_item)):
                destination = str(item.get("destination", "")).strip()
                if not destination and map_record:
                    destination = self.preferred_map_name(map_record, language)
                if not destination:
                    destination = str(other_item.get("destination", "")).strip()
                if not destination:
                    continue
                label = str(item.get("label", "")).strip() or destination[:2]
                synchronized[language].append({
                    "map_id": map_id,
                    "label": label[:10],
                    "destination": destination[:80],
                    "command": self.favorite_command(destination, language)[:100],
                })
            # Keep both lists aligned even when an old manually entered item
            # cannot be matched to a map JSON.
            if len(synchronized["KR"]) != len(synchronized["JP"]):
                source_language = "KR" if len(synchronized["KR"]) > len(synchronized["JP"]) else "JP"
                target_language = "JP" if source_language == "KR" else "KR"
                source = synchronized[source_language][-1]
                destination = source["destination"]
                synchronized[target_language].append({
                    "map_id": map_id,
                    "label": destination[:2],
                    "destination": destination,
                    "command": self.favorite_command(destination, target_language)[:100],
                })
        self.config["favorites"] = synchronized

    def refresh_favorite_controls(self):
        if not hasattr(self, "favorite_buttons"):
            return
        texts = FAVORITE_TEXTS[self.ui_language]
        enabled = self.ui_language in ("KR", "JP")
        if not enabled:
            self.favorite_overlay_editing = False
        visible = bool(self.config.get("favorite_overlay_visible")) and enabled and bool(self.favorite_entries())
        self.favorite_buttons["register"].configure(text=texts["register"], state="normal" if enabled else "disabled")
        self.favorite_buttons["show"].configure(
            text=texts["hide"] if visible else texts["show"],
            state="normal" if enabled else "disabled",
        )
        self.favorite_buttons["edit"].configure(
            text=texts["done"] if self.favorite_overlay_editing else texts["edit"],
            state="normal" if enabled else "disabled",
        )
        if not enabled and hasattr(self, "favorite_window"):
            self.favorite_window.withdraw()

    def open_favorite_dialog(self):
        if self.ui_language == "EN":
            return
        if hasattr(self, "favorite_dialog") and self.favorite_dialog.winfo_exists():
            self.favorite_dialog.lift()
            return
        texts = FAVORITE_TEXTS[self.ui_language]
        window = tk.Toplevel(self.root)
        self.favorite_dialog = window
        window.title(texts["title"])
        window.transient(self.root)
        window.grab_set()
        window.minsize(720, 590)
        window.geometry("780x650")
        if self.window_icon is not None:
            window.iconphoto(True, self.window_icon)

        body = ttk.Frame(window, padding=12)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=2)
        body.columnconfigure(1, weight=3)
        body.rowconfigure(1, weight=3)
        body.rowconfigure(4, weight=2)

        map_panel = ttk.Frame(body)
        map_panel.grid(row=0, column=0, rowspan=2, sticky="nsew")
        map_panel.columnconfigure(0, weight=1)
        map_panel.rowconfigure(3, weight=1)
        ttk.Label(map_panel, text=texts["map_list"]).grid(row=0, column=0, sticky="w", pady=(0, 5))
        ttk.Label(map_panel, text=texts["search"]).grid(row=1, column=0, sticky="w")
        search_var = tk.StringVar()
        ttk.Entry(map_panel, textvariable=search_var).grid(row=2, column=0, sticky="ew", pady=(3, 7))
        map_list = tk.Listbox(map_panel, exportselection=False, font=("맑은 고딕", 10))
        map_scroll = ttk.Scrollbar(map_panel, orient="vertical", command=map_list.yview)
        map_list.configure(yscrollcommand=map_scroll.set)
        map_list.grid(row=3, column=0, sticky="nsew", padx=(0, 3))
        map_scroll.grid(row=3, column=0, sticky="nse", padx=(0, 3))

        form = ttk.LabelFrame(body, text=texts["title"], padding=10)
        form.grid(row=0, column=1, rowspan=2, sticky="nsew", padx=(10, 0))
        form.columnconfigure(0, weight=1)
        destination_var = tk.StringVar()
        label_var = tk.StringVar()
        command_var = tk.StringVar()
        editing_index = {"value": None}
        selected_map_id = {"value": ""}

        ttk.Label(form, text=texts["destination"]).grid(row=0, column=0, sticky="w")
        destination_entry = ttk.Entry(form, textvariable=destination_var)
        destination_entry.grid(row=1, column=0, sticky="ew", pady=(3, 12))
        ttk.Label(form, text=texts["overlay_label"]).grid(row=2, column=0, sticky="w")
        ttk.Entry(form, textvariable=label_var).grid(row=3, column=0, sticky="ew", pady=(3, 12))
        ttk.Label(form, text=texts["command"]).grid(row=4, column=0, sticky="w")
        ttk.Entry(form, textvariable=command_var, state="readonly").grid(row=5, column=0, sticky="ew", pady=(3, 14))

        action_bar = ttk.Frame(form)
        action_bar.grid(row=6, column=0, sticky="ew")
        add_button = ttk.Button(action_bar, text=texts["add"])
        update_button = ttk.Button(action_bar, text=texts["update"])
        delete_button = ttk.Button(action_bar, text=texts["delete"])
        add_button.pack(side="left", padx=(0, 5))
        update_button.pack(side="left", padx=(0, 5))
        delete_button.pack(side="left")

        ttk.Label(body, text=texts["registered"]).grid(row=3, column=0, columnspan=2, sticky="w", pady=(14, 5))
        columns = ("label", "destination", "command")
        registered = ttk.Treeview(body, columns=columns, show="headings", selectmode="browse", height=6)
        registered.heading("label", text=texts["label"])
        registered.heading("destination", text=texts["map_name"])
        registered.heading("command", text=texts["command"])
        registered.column("label", width=85, stretch=False, anchor="center")
        registered.column("destination", width=220)
        registered.column("command", width=300)
        registered.grid(row=4, column=0, columnspan=2, sticky="nsew")

        all_map_items = []
        seen = set()
        for map_record in self.maps:
            name = self.preferred_map_name(map_record)
            if name and name not in seen:
                seen.add(name)
                all_map_items.append((name, str(map_record.get("id", ""))))
        all_map_items.sort(key=lambda item: item[0].casefold())
        displayed_map_items = list(all_map_items)

        def filter_map_list(*_args):
            query = unicodedata.normalize("NFKC", search_var.get()).strip().casefold()
            displayed_map_items.clear()
            displayed_map_items.extend(
                item
                for item in all_map_items
                if not query or unicodedata.normalize("NFKC", item[0]).casefold().startswith(query)
            )
            map_list.delete(0, "end")
            for name, _map_id in displayed_map_items:
                map_list.insert("end", name)

        search_var.trace_add("write", filter_map_list)
        filter_map_list()

        def update_command(*_args):
            command_var.set(self.favorite_command(destination_var.get()) if destination_var.get().strip() else "")

        destination_var.trace_add("write", update_command)

        def refresh_registered():
            registered.delete(*registered.get_children())
            for index, item in enumerate(self.favorite_entries()):
                destination = str(item.get("destination", "")).strip()
                label = str(item.get("label", "")).strip()
                command = str(item.get("command", "")).strip() or self.favorite_command(destination)
                registered.insert("", "end", iid=str(index), values=(label, destination, command))
            update_button.configure(state="normal" if editing_index["value"] is not None else "disabled")
            delete_button.configure(state="normal" if editing_index["value"] is not None else "disabled")

        def refresh_action_states():
            state = "normal" if editing_index["value"] is not None else "disabled"
            update_button.configure(state=state)
            delete_button.configure(state=state)

        def choose_map(_event=None):
            selection = map_list.curselection()
            if not selection:
                return
            if selection[0] >= len(displayed_map_items):
                return
            name, map_id = displayed_map_items[selection[0]]
            editing_index["value"] = None
            selected_map_id["value"] = map_id
            destination_var.set(name)
            label_var.set(name[:2])
            registered.selection_remove(*registered.selection())
            refresh_action_states()

        def choose_registered(_event=None):
            selection = registered.selection()
            if not selection:
                return
            index = int(selection[0])
            entries = self.favorite_entries()
            if index >= len(entries):
                return
            editing_index["value"] = index
            item = entries[index]
            selected_map_id["value"] = str(item.get("map_id", ""))
            destination_var.set(str(item.get("destination", "")))
            label_var.set(str(item.get("label", "")))
            refresh_action_states()

        def validated_item():
            destination = destination_var.get().strip()
            if not destination:
                messagebox.showinfo(texts["title"], texts["select_map"], parent=window)
                return None
            label = label_var.get().strip() or destination[:2]
            return {
                "map_id": selected_map_id["value"],
                "label": label[:10],
                "destination": destination[:80],
                "command": self.favorite_command(destination)[:100],
            }

        def save_changes():
            if not self.favorite_entries():
                self.config["favorite_overlay_visible"] = False
                self.favorite_overlay_editing = False
                if hasattr(self, "favorite_window"):
                    self.favorite_window.withdraw()
            save_config(self.config)
            self.rebuild_favorite_overlay()
            self.refresh_favorite_controls()
            refresh_registered()

        def add_item():
            item = validated_item()
            if item is None:
                return
            entries = self.favorite_entries()
            if len(entries) >= 5:
                messagebox.showinfo(texts["title"], texts["limit"], parent=window)
                return
            map_record = next(
                (record for record in self.maps if str(record.get("id", "")) == item["map_id"]),
                None,
            )
            other_language = "JP" if self.ui_language == "KR" else "KR"
            other_destination = self.preferred_map_name(map_record, other_language) if map_record else item["destination"]
            if not other_destination:
                other_destination = item["destination"]
            other_item = {
                "map_id": item["map_id"],
                "label": other_destination[:2],
                "destination": other_destination[:80],
                "command": self.favorite_command(other_destination, other_language)[:100],
            }
            self.config["favorites"][self.ui_language].append(item)
            self.config["favorites"][other_language].append(other_item)
            editing_index["value"] = len(self.favorite_entries()) - 1
            save_changes()
            registered.selection_set(str(editing_index["value"]))

        def update_item():
            index = editing_index["value"]
            item = validated_item()
            if index is None or item is None:
                return
            entries = self.favorite_entries()
            if index < len(entries):
                entries[index] = item
                save_changes()
                registered.selection_set(str(index))

        def delete_item():
            index = editing_index["value"]
            entries = self.favorite_entries()
            if index is None or index >= len(entries):
                return
            for language in ("KR", "JP"):
                locale_entries = self.config["favorites"][language]
                if index < len(locale_entries):
                    del locale_entries[index]
            editing_index["value"] = None
            selected_map_id["value"] = ""
            destination_var.set("")
            label_var.set("")
            save_changes()

        map_list.bind("<<ListboxSelect>>", choose_map)
        registered.bind("<<TreeviewSelect>>", choose_registered)
        add_button.configure(command=add_item)
        update_button.configure(command=update_item)
        delete_button.configure(command=delete_item)
        refresh_registered()

        def close():
            try:
                window.grab_release()
            except Exception:
                pass
            window.destroy()

        ttk.Button(body, text=texts["close"], command=close).grid(row=5, column=0, columnspan=2, sticky="e", pady=(12, 0))
        window.protocol("WM_DELETE_WINDOW", close)

    def create_favorite_overlay(self):
        win = tk.Toplevel(self.root)
        win.overrideredirect(True)
        win.attributes("-topmost", False)
        win.configure(bg="#171008")
        self.favorite_frame = tk.Frame(win, bg="#171008", bd=2, relief="ridge")
        self.favorite_frame.pack(fill="both", expand=True)
        win.withdraw()
        set_noactivate_toolwindow(win, click_through=False)
        self.rebuild_favorite_overlay()
        return win

    def rebuild_favorite_overlay(self):
        if not hasattr(self, "favorite_frame"):
            return
        for child in self.favorite_frame.winfo_children():
            child.destroy()
        for index, item in enumerate(self.favorite_entries()):
            label = str(item.get("label", "")).strip() or str(item.get("destination", ""))[:2]
            button = tk.Button(
                self.favorite_frame,
                text=label,
                command=lambda item_index=index: self.copy_favorite(item_index),
                bg="#4b2b17",
                fg="#f6d58a",
                activebackground="#75502b",
                activeforeground="#fff0bd",
                disabledforeground="#f6d58a",
                relief="raised",
                bd=2,
                padx=9,
                pady=4,
                font=("맑은 고딕", 9, "bold"),
                cursor="fleur" if self.favorite_overlay_editing else "hand2",
                takefocus=False,
            )
            button.pack(side="left", padx=1, pady=1)
            button.bind("<ButtonPress-1>", self.favorite_overlay_press, add="+")
            button.bind("<B1-Motion>", self.favorite_overlay_drag, add="+")
            button.bind("<ButtonRelease-1>", self.favorite_overlay_release, add="+")
        if self.favorite_overlay_editing:
            self.favorite_frame.configure(cursor="fleur", highlightthickness=2, highlightbackground="#ffd45a")
        else:
            self.favorite_frame.configure(cursor="arrow", highlightthickness=0)
        if hasattr(self, "favorite_window") and self.config.get("favorite_overlay_visible") and self.ui_language != "EN":
            self.show_favorite_overlay()

    def copy_favorite(self, index):
        if self.favorite_overlay_editing or self.ui_language == "EN":
            return
        entries = self.favorite_entries()
        if index >= len(entries):
            return
        command = str(entries[index].get("command", "")).strip()
        if not command:
            command = self.favorite_command(str(entries[index].get("destination", "")))
        self.root.clipboard_clear()
        self.root.clipboard_append(command)
        self.root.update()
        self.favorite_copied_index = index
        buttons = self.favorite_frame.winfo_children()
        if index < len(buttons):
            buttons[index].configure(text="Copied!")
        if self.favorite_copied_after_id:
            self.root.after_cancel(self.favorite_copied_after_id)
        self.favorite_copied_after_id = self.root.after(900, self.restore_favorite_labels)

    def restore_favorite_labels(self):
        self.favorite_copied_after_id = None
        self.favorite_copied_index = None
        self.rebuild_favorite_overlay()

    def toggle_favorite_overlay(self):
        if self.ui_language == "EN":
            return
        if not self.favorite_entries():
            messagebox.showinfo(self.favorite_text("title"), self.favorite_text("empty"), parent=self.root)
            return
        visible = bool(self.config.get("favorite_overlay_visible"))
        self.config["favorite_overlay_visible"] = not visible
        if visible:
            self.favorite_overlay_editing = False
            self.favorite_window.withdraw()
        else:
            self.rebuild_favorite_overlay()
            self.show_favorite_overlay()
        save_config(self.config)
        self.refresh_favorite_controls()

    def toggle_favorite_edit_mode(self):
        if self.ui_language == "EN":
            return
        if not self.config.get("favorite_overlay_visible") or not self.favorite_window.winfo_viewable():
            messagebox.showinfo(self.favorite_text("title"), self.favorite_text("show_first"), parent=self.root)
            return
        self.favorite_overlay_editing = not self.favorite_overlay_editing
        self.rebuild_favorite_overlay()
        self.refresh_favorite_controls()
        if not self.favorite_overlay_editing:
            save_config(self.config)

    def favorite_overlay_press(self, event):
        if not self.favorite_overlay_editing:
            return
        self.favorite_drag_start = (event.x_root, event.y_root)
        self.favorite_drag_origin = (self.favorite_window.winfo_x(), self.favorite_window.winfo_y())

    def favorite_overlay_drag(self, event):
        if not self.favorite_overlay_editing or not self.favorite_drag_start or not self.favorite_drag_origin:
            return
        dx = event.x_root - self.favorite_drag_start[0]
        dy = event.y_root - self.favorite_drag_start[1]
        x = self.favorite_drag_origin[0] + dx
        y = self.favorite_drag_origin[1] + dy
        client = self.get_stable_client_rect()
        if client:
            left, top, right, bottom = client
            width = self.favorite_window.winfo_width()
            height = self.favorite_window.winfo_height()
            x = max(left, min(x, right - width))
            y = max(top, min(y, bottom - height))
        self.favorite_window.geometry(f"+{round(x)}+{round(y)}")

    def favorite_overlay_release(self, _event):
        if self.favorite_overlay_editing and self.favorite_drag_start:
            client = self.get_stable_client_rect()
            if client:
                self.config["favorite_overlay_offset_x"] = self.favorite_window.winfo_x() - client[0]
                self.config["favorite_overlay_offset_y"] = self.favorite_window.winfo_y() - client[1]
                save_config(self.config)
        self.favorite_drag_start = None
        self.favorite_drag_origin = None

    def position_favorite_overlay(self):
        client = self.get_stable_client_rect()
        if not client:
            return
        self.favorite_window.update_idletasks()
        left, top, right, bottom = client
        width = max(1, self.favorite_window.winfo_reqwidth())
        height = max(1, self.favorite_window.winfo_reqheight())
        offset_x = self.config.get("favorite_overlay_offset_x")
        offset_y = self.config.get("favorite_overlay_offset_y")
        if offset_x is None or offset_y is None:
            offset_x = max(10, right - left - width - 18)
            offset_y = max(10, round((bottom - top) * 0.72) - height)
            self.config["favorite_overlay_offset_x"] = offset_x
            self.config["favorite_overlay_offset_y"] = offset_y
        x = max(left, min(left + int(offset_x), right - width))
        y = max(top, min(top + int(offset_y), bottom - height))
        self.favorite_window.geometry(f"{width}x{height}+{x}+{y}")

    def show_favorite_overlay(self):
        if self.ui_language == "EN" or not self.favorite_entries() or not self.find_target():
            self.favorite_window.withdraw()
            return
        self.position_favorite_overlay()
        show_above_owner(self.favorite_window, self.target_hwnd)

    def show_help(self):
        if hasattr(self, "help_window") and self.help_window.winfo_exists():
            self.help_window.lift()
            return

        help_texts = {
            "KR": (
                "캡처 영역 설정\n"
                "  F11 : 월드맵 표시/숨기기\n"
                "  Shift + F11 : 맵 이름과 X:Y 좌표 OCR 영역 동시 편집\n\n"
                "  박스 드래그 : 영역 이동\n"
                "  우측 하단 손잡이 드래그 : 영역 크기 조절\n\n"
                "미니맵 조작\n"
                "  Ctrl + F11 : 현재 미니맵/월드맵의 위치·크기·불투명도 조절\n"
                "  우측 하단 노란 손잡이 드래그 : 크기 조절 (40~500%)\n"
                "  마우스 휠 : 불투명도 조절 (30~100%)\n"
                "  드래그 : 미니맵 이동\n\n"
                "즐겨찾기\n"
                "  등록 : 맵을 선택하고 복사할 이동 명령어를 저장\n"
                "  KR/JP 항목은 함께 생성되며 수정은 현재 언어에만 반영\n"
                "  표시/비표시 : 게임 안의 즐겨찾기 버튼을 켜거나 끔\n"
                "  편집/완료 : 즐겨찾기 버튼 오버레이의 위치를 이동\n"
                "  버튼 클릭 : 명령어를 클립보드에 복사 (자동 입력하지 않음)\n\n"
                "OCR은 Godius Client가 전면에 있을 때만 실행됩니다."
            ),
            "JP": (
                "キャプチャー範囲の設定\n"
                "  F11 : ワールドマップを表示／非表示\n"
                "  Shift + F11 : マップ名とX:Y座標のOCR範囲を同時編集\n\n"
                "  ボックスをドラッグ : 範囲を移動\n"
                "  右下のハンドルをドラッグ : 範囲のサイズを変更\n\n"
                "ミニマップ操作\n"
                "  Ctrl + F11 : 表示中のミニマップ／ワールドマップの位置・サイズ・不透明度を調整\n"
                "  右下の黄色いハンドルをドラッグ : サイズ変更（40～500%）\n"
                "  マウスホイール : 不透明度の調整（30～100%）\n"
                "  ドラッグ : ミニマップの移動\n\n"
                "お気に入り\n"
                "  登録 : マップを選び、コピーする移動コマンドを保存\n"
                "  KR/JP項目は同時に作成され、変更は現在の言語だけに反映\n"
                "  表示／非表示 : ゲーム内のお気に入りボタンを表示／非表示\n"
                "  編集／完了 : お気に入りオーバーレイの位置を移動\n"
                "  ボタンをクリック : コマンドをクリップボードへコピー（自動入力なし）\n\n"
                "OCRはGodius Clientが最前面にある場合のみ実行されます。"
            ),
            "EN": (
                "Capture regions\n"
                "  F11 : Show or hide the world map\n"
                "  Shift + F11 : Edit the map-name and X:Y OCR regions together\n\n"
                "  Drag the box : Move the region\n"
                "  Drag the bottom-right handle : Resize the region\n\n"
                "Minimap controls\n"
                "  Ctrl + F11 : Adjust the current minimap/world map position, size, and opacity\n"
                "  Ctrl + F11 while world map is shown : Adjust its size/opacity\n"
                "  Drag the yellow bottom-right handle : Resize (40–500%)\n"
                "  Mouse wheel : Adjust opacity (30–100%)\n"
                "  Drag : Move the minimap\n\n"
                "Favorites\n"
                "  This feature is unavailable in the English interface.\n\n"
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

    def load_world_map_image(self):
        path = RESOURCE_DIR / "maps" / "other" / "worldmap.jpg"
        if not path.is_file():
            self.world_map_original_image = None
            return False
        try:
            self.world_map_original_image = Image.open(path).convert("RGBA")
            self.world_map_render_key = None
            return True
        except Exception:
            self.world_map_original_image = None
            return False

    def render_world_map(self):
        if not self.world_map_mode or self.world_map_original_image is None:
            return
        client = self.get_stable_client_rect()
        if not client:
            return
        left, top, right, bottom = client
        client_width = max(1, right - left)
        client_height = max(1, bottom - top)
        source_width, source_height = self.world_map_original_image.size
        fit_ratio = min((client_width * 0.92) / source_width, (client_height * 0.92) / source_height, 1.0)
        size_scale = max(0.4, min(1.0, float(self.config.get("world_map_size_scale", 1.0))))
        self.config["world_map_size_scale"] = size_scale
        ratio = fit_ratio * size_scale
        width = max(1, round(source_width * ratio))
        height = max(1, round(source_height * ratio))
        self.world_map_scale = ratio
        x = left + (client_width - width) // 2
        y = top + (client_height - height) // 2
        self.map_window.geometry(f"{width + 4}x{height + 4}+{x}+{y}")
        self.map_width = width + 4
        self.map_height = height + 4
        position = self.active_map.get("worldMapPosition") if self.active_map else None
        position_key = None
        if isinstance(position, dict):
            position_key = (position.get("x"), position.get("y"))
        render_key = (width, height, str(self.active_map.get("id", "")) if self.active_map else "", position_key)
        if render_key == self.world_map_render_key:
            return
        self.world_map_render_key = render_key
        image = self.world_map_original_image.resize((width, height), Image.Resampling.LANCZOS)
        self.world_map_photo = ImageTk.PhotoImage(image)
        self.map_canvas.configure(
            width=width,
            height=height,
            highlightbackground="#7a1c1c",
            highlightcolor="#7a1c1c",
        )
        self.map_canvas.delete("all")
        self.map_canvas.create_image(0, 0, image=self.world_map_photo, anchor="nw")

        if isinstance(position, dict):
            try:
                marker_x = round(float(position["x"]) * ratio)
                marker_y = round(float(position["y"]) * ratio)
                marker_x = max(12, min(width - 12, marker_x))
                marker_y = max(26, min(height - 4, marker_y))
                # The polygon tip is the stored world-map pixel. A black outer
                # arrow keeps the red marker visible over bright terrain.
                outer = (
                    marker_x - 13, marker_y - 34,
                    marker_x + 13, marker_y - 34,
                    marker_x + 13, marker_y - 18,
                    marker_x + 23, marker_y - 18,
                    marker_x, marker_y + 2,
                    marker_x - 23, marker_y - 18,
                    marker_x - 13, marker_y - 18,
                )
                inner = (
                    marker_x - 9, marker_y - 30,
                    marker_x + 9, marker_y - 30,
                    marker_x + 9, marker_y - 15,
                    marker_x + 16, marker_y - 15,
                    marker_x, marker_y - 1,
                    marker_x - 16, marker_y - 15,
                    marker_x - 9, marker_y - 15,
                )
                self.map_canvas.create_polygon(*outer, fill="#000000", outline="#000000")
                self.map_canvas.create_polygon(*inner, fill="#ff2020", outline="#ff6666", width=2)
            except (KeyError, TypeError, ValueError):
                pass
        self.draw_resize_handles()
        self.draw_adjustment_indicators()

    def show_world_map(self):
        self.render_world_map()
        show_above_owner(self.map_window, self.target_hwnd)
        set_window_click_through(self.map_window, not self.map_resize_mode)

    def hide_world_map(self):
        if self.map_window.winfo_viewable():
            self.map_window.withdraw()

    def toggle_world_map(self):
        if self.world_map_mode:
            self.world_map_mode = False
            self.map_resize_mode = False
            set_window_click_through(self.map_window, True)
            self.hide_world_map()
            if self.active_map:
                self.map_canvas.configure(highlightbackground="#444444", highlightcolor="#444444")
                self.apply_map_size()
                self.apply_map_opacity()
                self.show_map()
            return
        if not self.find_target():
            self.set_status("target_missing", "#ff7777")
            return
        if not self.load_world_map_image():
            self.set_status("world_map_missing", "#ff7777")
            return
        self.calibration_mode = None
        self.region_window.withdraw()
        self.coordinate_region_window.withdraw()
        self.map_resize_mode = False
        set_window_click_through(self.map_window, True)
        self.hide_map()
        self.world_map_mode = True
        self.apply_map_opacity()
        self.set_status("world_map_open", "#ff7777")
        self.show_world_map()

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
        if self.world_map_mode:
            self.render_world_map()

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
        if not self.world_map_mode and not self.active_map:
            self.set_status("no_map_resize")
            return
        self.calibration_mode = None
        self.region_window.withdraw()
        self.coordinate_region_window.withdraw()
        self.map_resize_mode = not self.map_resize_mode
        set_window_click_through(self.map_window, not self.map_resize_mode)
        border_color = "#ffe000" if self.map_resize_mode else "#444444"
        self.map_canvas.configure(highlightbackground=border_color, highlightcolor=border_color)
        if self.world_map_mode:
            self.world_map_render_key = None
        if self.map_resize_mode:
            self.set_status("world_resize_mode" if self.world_map_mode else "resize_mode", "#ffe27a")
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
        opacity_key = "world_map_opacity_percent" if self.world_map_mode else "map_opacity_percent"
        current = int(self.config.get(opacity_key, 100))
        change = 5 if event.delta > 0 else -5
        self.config[opacity_key] = max(30, min(100, current + change))
        self.apply_map_opacity()
        save_config(self.config)
        self.opacity_indicator_until = time.monotonic() + 1.0
        self.draw_adjustment_indicators()
        percent = self.config[opacity_key]
        self.set_status("world_opacity" if self.world_map_mode else "opacity", "#ffe27a", percent=percent)
        return "break"

    def render_map(self):
        if self.world_map_mode:
            self.render_world_map()
            return
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
            opacity_key = "world_map_opacity_percent" if self.world_map_mode else "map_opacity_percent"
            self.draw_corner_indicator(
                f"{int(self.config.get(opacity_key, 100))}%",
                8,
                "nw",
                "opacity_indicator",
            )
        if now < self.scale_indicator_until and not self.no_map_data_visible:
            width = int(float(self.map_canvas.cget("width")))
            scale_key = "world_map_size_scale" if self.world_map_mode else "map_size_scale"
            self.draw_corner_indicator(
                f"{round(float(self.config.get(scale_key, 1.0)) * 100)}%",
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
        opacity_key = "world_map_opacity_percent" if self.world_map_mode else "map_opacity_percent"
        percent = max(30, min(100, int(self.config.get(opacity_key, 100))))
        self.config[opacity_key] = percent
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
            scale_key = "world_map_size_scale" if self.world_map_mode else "map_size_scale"
            self.map_resize_start_scale = float(self.config.get(scale_key, 1.0))
            self.map_resize_start_size = (self.map_window.winfo_width(), self.map_window.winfo_height())
            return
        if self.world_map_mode:
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
            scale_key = "world_map_size_scale" if self.world_map_mode else "map_size_scale"
            maximum = 1.0 if self.world_map_mode else 5.0
            self.config[scale_key] = round(max(0.4, min(maximum, self.map_resize_start_scale * ratio)), 4)
            self.scale_indicator_until = time.monotonic() + 1.0
            if self.world_map_mode:
                self.world_map_render_key = None
                self.render_world_map()
                percent = round(self.config[scale_key] * 100)
                self.set_status("world_size", "#ffe27a", percent=percent)
                return
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
            percent = round(self.config[scale_key] * 100)
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
            if not self.world_map_mode:
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

    def create_region_window(self, kind):
        win = tk.Toplevel(self.root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.attributes("-alpha", 0.62)
        win.configure(bg="#ff00ff")
        win.wm_attributes("-transparentcolor", "#ff00ff")
        canvas = tk.Canvas(win, bg="#ff00ff", highlightthickness=0, cursor="fleur")
        canvas.pack(fill="both", expand=True)
        canvas.bind("<ButtonPress-1>", lambda event: self.region_press(event, kind))
        canvas.bind("<B1-Motion>", lambda event: self.region_drag(event, kind))
        canvas.bind("<ButtonRelease-1>", lambda event: self.region_release(event, kind))
        canvas.bind("<Motion>", lambda event: self.region_pointer_motion(event, kind))
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
        favorite_root = user32.GetAncestor(self.favorite_window.winfo_id(), GA_ROOT) or self.favorite_window.winfo_id()
        if foreground == favorite_root:
            return True
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
        favorite_root = user32.GetAncestor(self.favorite_window.winfo_id(), GA_ROOT) or self.favorite_window.winfo_id()
        if foreground_root == favorite_root:
            return True
        if self.calibration_mode:
            for region_window in (self.region_window, self.coordinate_region_window):
                region_root = user32.GetAncestor(region_window.winfo_id(), GA_ROOT) or region_window.winfo_id()
                if foreground_root == region_root:
                    return True
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
                if self.world_map_mode:
                    self.render_world_map()
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
        kind = kind or "name"
        region_key = "coordinate_region" if kind == "coordinates" else "capture_region"
        reference_key = "coordinate_reference_size" if kind == "coordinates" else "capture_reference_size"
        self.config[region_key] = [left - cl, top - ct, right - cl, bottom - ct]
        self.config[reference_key] = [cr - cl, cb - ct]
        save_config(self.config)

    def toggle_calibration(self):
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
        if self.calibration_mode:
            for kind in ("name", "coordinates"):
                bbox = self.capture_bboxes.get(kind) or self.current_bbox(kind, allow_default=True)
                if bbox:
                    self.store_bbox(bbox, kind)
            self.calibration_mode = None
            self.region_window.withdraw()
            self.coordinate_region_window.withdraw()
        else:
            if self.world_map_mode:
                self.toggle_world_map()
            self.calibration_mode = "both"
            for kind in ("name", "coordinates"):
                self.capture_bboxes[kind] = self.current_bbox(kind, allow_default=True)
            self.hide_map()
            self.update_region_windows()

    def update_region_windows(self):
        self.update_region_window("name", self.region_window)
        self.update_region_window("coordinates", self.coordinate_region_window)

    def update_region_window(self, kind, region_window):
        bbox = self.current_bbox(kind, allow_default=True)
        if not bbox:
            return
        self.capture_bboxes[kind] = bbox
        left, top, right, bottom = bbox
        width = max(40, right - left)
        height = max(24, bottom - top)
        region_window.geometry(f"{width}x{height}+{left}+{top}")
        canvas = region_window.winfo_children()[0]
        canvas.configure(width=width, height=height)
        canvas.delete("all")
        color = "#ffd400" if kind == "coordinates" else "#ff3535"
        fill = "#947d00" if kind == "coordinates" else "#b51f1f"
        canvas.create_rectangle(2, 2, width - 3, height - 3, outline=color, fill=fill, width=4)
        handle = 12
        x = width - handle - 2
        y = height - handle - 2
        canvas.create_oval(x, y, x + handle, y + handle, fill="white", outline=color, width=2)
        region_window.deiconify()
        keep_topmost(region_window)

    def region_press(self, event, kind):
        region_window = self.coordinate_region_window if kind == "coordinates" else self.region_window
        width = max(1, region_window.winfo_width())
        height = max(1, region_window.winfo_height())
        margin = 24
        right = event.x >= width - margin
        bottom = event.y >= height - margin
        self.drag_kind = "br" if right and bottom else "move"
        self.drag_region_kind = kind
        self.drag_start = (event.x_root, event.y_root)
        self.drag_bbox = self.capture_bboxes.get(kind) or self.current_bbox(kind, allow_default=True)

    def region_pointer_motion(self, event, kind):
        region_window = self.coordinate_region_window if kind == "coordinates" else self.region_window
        width = max(1, region_window.winfo_width())
        height = max(1, region_window.winfo_height())
        if event.x >= width - 24 and event.y >= height - 24:
            event.widget.configure(cursor="size_nw_se")
        else:
            event.widget.configure(cursor="fleur")

    def region_drag(self, event, kind):
        if self.drag_region_kind != kind or not self.drag_start or not self.drag_bbox:
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
        self.capture_bboxes[kind] = (round(l), round(t), round(r), round(b))
        self.store_bbox(self.capture_bboxes[kind], kind)
        region_window = self.coordinate_region_window if kind == "coordinates" else self.region_window
        self.update_region_window(kind, region_window)

    def region_release(self, _event, kind):
        if self.drag_region_kind == kind and self.capture_bboxes.get(kind):
            self.store_bbox(self.capture_bboxes[kind], kind)
        self.drag_region_kind = None
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
        if self.world_map_mode:
            self.render_world_map()
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
        if self.world_map_mode:
            self.show_world_map()
            return
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
            alt_down = bool(user32.GetAsyncKeyState(VK_MENU) & 0x8000)
            if control_down:
                self.toggle_map_resize_mode()
            elif shift_down:
                self.toggle_calibration()
            elif not alt_down:
                self.toggle_world_map()
        self.last_toggle_down = toggle_down

        favorite_should_show = (
            self.ui_language in ("KR", "JP")
            and bool(self.config.get("favorite_overlay_visible"))
            and bool(self.favorite_entries())
            and bool(self.target_hwnd)
            and not user32.IsIconic(self.target_hwnd)
        )
        if favorite_should_show:
            if not self.favorite_drag_start:
                self.position_favorite_overlay()
            if not self.favorite_window.winfo_viewable():
                show_above_owner(self.favorite_window, self.target_hwnd)
        elif self.favorite_window.winfo_viewable():
            self.favorite_window.withdraw()

        if self.calibration_mode:
            self.update_region_windows()
        elif not self.target_hwnd:
            self.set_status("target_missing", "#ff7777")
            self.hide_map()
            self.hide_world_map()
        elif user32.IsIconic(self.target_hwnd):
            self.set_status("minimized")
            self.hide_map()
            self.hide_world_map()
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
        if self.world_map_mode and self.map_window.winfo_viewable() and self.target_hwnd:
            self.render_world_map()
        elif self.world_map_mode and self.target_hwnd and not user32.IsIconic(self.target_hwnd):
            self.show_world_map()

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
