import io
import os
import time

import pyautogui
import pygetwindow as gw

from config import (
    DOTS_OFFSET_X,
    GAME_VIEW,
    WINDOW_TITLES,
    ACCOUNT_ROW_Y_BASE,
    ACCOUNT_ROW_HEIGHT,
    ACCOUNT_VISIBLE_ROWS,
    ACCOUNT_CAPTURE_WIDTH,
)
from utils_user import normalize_account_name

ACTION_SPEED = 0.6


def _action_delay(seconds):
    return seconds / ACTION_SPEED

try:
    import win32api
    import win32con
    import win32gui

    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False


def get_game_window():
    all_matches = []
    for title in WINDOW_TITLES:
        all_matches.extend(gw.getWindowsWithTitle(title))

    if not all_matches:
        return None

    for win in all_matches:
        if getattr(win, "title", "").strip() == "Rise of Kingdoms Bot":
            return win

    for win in sorted(all_matches, key=lambda w: (getattr(w, "isMinimized", False), getattr(w, "left", 0))):
        if not getattr(win, "isMinimized", False):
            return win

    return all_matches[0]


def focus_game_window():
    win = get_game_window()
    if not win:
        return False

    if getattr(win, "isMinimized", False):
        win.restore()

    try:
        win.activate()
    except Exception:
        pass

    if HAS_WIN32:
        try:
            hwnd = getattr(win, "_hWnd", None)
            if hwnd is not None:
                if win32gui.IsIconic(hwnd):
                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                win32gui.SetWindowPos(
                    hwnd,
                    win32con.HWND_TOPMOST,
                    0,
                    0,
                    0,
                    0,
                    win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW,
                )
                win32gui.SetWindowPos(
                    hwnd,
                    win32con.HWND_NOTOPMOST,
                    0,
                    0,
                    0,
                    0,
                    win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW,
                )
                win32gui.SetForegroundWindow(hwnd)
                win32gui.SetActiveWindow(hwnd)
        except Exception:
            pass

    time.sleep(0.3)
    return True


def _asset_path(*parts):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(base_dir, *parts))


def _get_primary_game_region(focus=True):
    win = get_game_window()
    if not win:
        return None

    if focus:
        focus_game_window()

    left = max(0, int(getattr(win, 'left', 0)))
    top = max(0, int(getattr(win, 'top', 0)))
    width = max(1, int(getattr(win, 'width', 0)))
    height = max(1, int(getattr(win, 'height', 0)))

    region_left = left + max(GAME_VIEW["margin_left"], int(GAME_VIEW["offset_x"]))
    region_top = top + max(GAME_VIEW["margin_top"], int(GAME_VIEW["offset_y"]))
    region_width = min(max(GAME_VIEW["min_width"], int(GAME_VIEW["width"])), max(1, width - 10))
    region_height = min(max(GAME_VIEW["min_height"], int(GAME_VIEW["height"])), max(1, height - 20))

    return (
        region_left,
        region_top,
        region_width,
        region_height,
    )


def get_account_row_for_name(acc_name):
    if not acc_name:
        return None

    normalized = normalize_account_name(acc_name)
    if not normalized or not normalized.isdigit():
        return None

    row = int(normalized)
    return row if row >= 1 else None


def _detect_account_row_centers(region):
    try:
        screenshot = pyautogui.screenshot(region=region).convert("L")
        width, height = screenshot.size
        pixels = screenshot.load()
        signals = [
            sum(abs(pixels[x, y] - pixels[x, y - 1]) for x in range(width)) / width
            for y in range(1, height)
        ]
        if not signals:
            return []

        ordered = sorted(signals)
        baseline = ordered[len(ordered) // 2]
        threshold = max(baseline + 2, baseline * 1.35)
        peaks = [
            y + 1
            for y, signal in enumerate(signals)
            if signal >= threshold
            and signal >= (signals[y - 1] if y else signal)
            and signal >= (signals[y + 1] if y + 1 < len(signals) else signal)
        ]

        centers = []
        for y in peaks:
            if not centers or y - centers[-1] > 5:
                centers.append(y)
            else:
                centers[-1] = (centers[-1] + y) // 2

        if len(centers) < 2:
            return []

        gaps = [right - left for left, right in zip(centers, centers[1:])]
        average_gap = sum(gaps) / len(gaps)
        if not 12 <= average_gap <= 40:
            return []
        if any(abs(gap - average_gap) > max(4, average_gap * 0.3) for gap in gaps):
            return []
        return centers
    except Exception:
        return []


def get_account_layout(region):
    row_height = max(1, int(ACCOUNT_ROW_HEIGHT))
    first_row_offset = max(1, int(ACCOUNT_ROW_Y_BASE))
    visible_rows = max(1, int(ACCOUNT_VISIBLE_ROWS))

    return first_row_offset, row_height, visible_rows


def capture_account_row_image(acc_name, output_path=None, x_coord=None, y_coord=None):
    
    if not acc_name:
        return None

    region = _get_primary_game_region()
    if not region:
        return None

    game_left, game_top, game_width, game_height = region
    _, row_height, _ = get_account_layout(region)

    if x_coord is None or y_coord is None:
        x_coord, y_coord = find_account_dots(acc_name)
        if x_coord is None or y_coord is None:
            return None

    capture_width = min(max(1, int(ACCOUNT_CAPTURE_WIDTH)), game_width)
    row_left = game_left + (game_width - capture_width) // 2
    row_top = max(
        game_top,
        int(y_coord - (row_height // 2) - 2),
    )
    row_right = row_left + capture_width
    row_bottom = min(
        game_top + game_height,
        int(y_coord + (row_height - row_height // 2) + 2),
    )

    row_region = (
        int(row_left),
        int(row_top),
        int(row_right - row_left),
        int(row_bottom - row_top),
    )

    try:
        screenshot = pyautogui.screenshot(region=row_region)
        buffer = io.BytesIO()
        screenshot.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer
    except Exception:
        return None


def find_account_dots_for_check(acc_name):
    if not acc_name:
        return None, None

    normalized = normalize_account_name(acc_name)
    if not normalized or not normalized.isdigit():
        return None, None

    target_row = int(normalized)
    if target_row < 1:
        return None, None

    if not scroll_account_list_to_top():
        return None, None

    region = _get_primary_game_region(focus=False)
    if not region:
        return None, None

    left, top, width, _ = region
    x_account = left + width // 2
    focus_x = x_account
    first_row_offset, row_height, visible_rows = get_account_layout(region)
    first_row_y = top + first_row_offset
    focus_y = first_row_y

    pyautogui.moveTo(focus_x, focus_y)
    pyautogui.click(focus_x, focus_y)
    time.sleep(_action_delay(0.1))
    pyautogui.press("home")
    time.sleep(_action_delay(0.1))

    down_count = target_row - 1
    for _ in range(down_count):
        pyautogui.press("down")
        time.sleep(_action_delay(0.05))

    first_row_offset, row_height, visible_rows = get_account_layout(region)
    visible_row = min(target_row, visible_rows)
    y_account = (
        top + first_row_offset + (visible_row - 1) * row_height
    )
    return x_account, y_account


def scroll_game_window(delta_steps, focus=True):
    win = get_game_window()
    if not win:
        return False

    if focus:
        focus_game_window()

    if HAS_WIN32:
        try:
            hwnd = getattr(win, "_hWnd", None)
            if hwnd is not None:
                if win32gui.IsIconic(hwnd):
                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                win32gui.SetForegroundWindow(hwnd)
                win32gui.SetActiveWindow(hwnd)

                region = _get_primary_game_region(focus=False)
                if region is not None:
                    left, top, width, height = region
                    x = left + max(40, width // 2)
                    y = top + max(40, height // 2)
                else:
                    rect = win32gui.GetWindowRect(hwnd)
                    x = rect[0] + max(40, int(getattr(win, "width", 500)) // 2)
                    y = rect[1] + max(40, int(getattr(win, "height", 260)) // 2)

                win32api.SetCursorPos((x, y))
                win32api.mouse_event(win32con.MOUSEEVENTF_WHEEL, x, y, int(delta_steps), 0)
                time.sleep(0.05)
                return True
        except Exception:
            pass

    region = _get_primary_game_region(focus=False)
    if region is not None:
        left, top, width, height = region
        x = left + max(40, width // 2)
        y = top + max(40, height // 2)
        pyautogui.moveTo(x, y)
        pyautogui.scroll(delta_steps)
        time.sleep(0.05)
        return True

    pyautogui.scroll(delta_steps)
    return True


def scroll_account_list_to_top(focus=True):
    print("\n⬆️  Cuộn danh sách tài khoản lên đầu...")
    region = _get_primary_game_region(focus=focus)
    if not region:
        return False

    left, top, width, _ = region
    list_x = left + width // 2
    list_y = top + ACCOUNT_ROW_Y_BASE
    pyautogui.moveTo(list_x, list_y)
    time.sleep(0.15)

    for _ in range(12):
        pyautogui.scroll(1)
        time.sleep(0.03)

    pyautogui.click(list_x, list_y)
    pyautogui.press("home")
    time.sleep(0.10)
    return True


def scroll_to_target_row(target_row, focus=True):
    if target_row is None or target_row < 1:
        return False

    region = _get_primary_game_region(focus=focus)
    if not region:
        return False

    left, top, _, _ = region
    x_click = left + DOTS_OFFSET_X
    first_row_offset, row_height, page_rows = get_account_layout(region)

    page_index = (target_row - 1) // page_rows
    pos_in_page = (target_row - 1) % page_rows

    for _ in range(page_index):
        scroll_game_window(-400, focus=False)
        time.sleep(0.12)

    y_click = top + first_row_offset + pos_in_page * row_height
    pyautogui.moveTo(x_click, y_click)
    pyautogui.click(x_click, y_click)
    time.sleep(0.05)

    return True


def find_account_dots(acc_name):
    if not acc_name:
        return None, None

    region = _get_primary_game_region()
    if not region:
        print("❌ Không tìm thấy cửa sổ game.")
        return None, None

    left, top, width, height = region
    x_dots_column = left + DOTS_OFFSET_X

    print(f"\n🔍 Đang tìm tài khoản '{acc_name}' bằng cách đếm hàng")
    print(f"📍 Vùng quét: {width}×{height}px")

    row = get_account_row_for_name(acc_name)
    if row is None:
        print(f"❌ Không xác định được dòng của tài khoản '{acc_name}'")
        return None, None

    scroll_account_list_to_top(focus=False)
    scroll_to_target_row(row, focus=False)

    first_row_offset, row_height, page_rows = get_account_layout(region)
    relative_row = ((row - 1) % page_rows) + 1

    y_account = top + first_row_offset + (relative_row - 1) * row_height
    click_x = x_dots_column
    click_y = y_account + (row_height // 2)

    print(f"✅ Xác định được dòng tài khoản")
    print(f"   Hàng: {row}")
    print(f"   Y: {y_account}")
    print(f"✅ Đã click qua từng hàng tới row {row} tài khoản '{acc_name}' tại ({click_x}, {click_y})")
    return x_dots_column, y_account


def do_action_on(acc_name):
    if not focus_game_window():
        return False, "❌ Không thể đưa cửa sổ game lên trước."

    x, y = find_account_dots_for_check(acc_name)
    if x is None or y is None:
        return False, f"❌ Không tìm thấy tài khoản **{acc_name}** trên màn hình!"

    pyautogui.moveTo(x, y)
    pyautogui.click(x, y)
    time.sleep(_action_delay(0.45))
    pyautogui.click(x - 70, y + ACCOUNT_ROW_HEIGHT)
    return True, f"✅ Đã bấm **Chạy/dừng** để BẬT tài khoản **{acc_name}**!"


def do_action_off(acc_name):
    x, y = find_account_dots(acc_name)
    if x is None or y is None:
        return False, f"❌ Không tìm thấy tài khoản **{acc_name}** trên màn hình!"

    pyautogui.click(x, y)
    time.sleep(0.35)
    pyautogui.click(x - 20, y + 75)
    time.sleep(0.5)
    pyautogui.press("enter")
    return True, f"🛑 Đã ĐÓNG tab tài khoản **{acc_name}** và xác nhận **Yes**!"


def do_action_check(acc_name, capture_row=False):
    region = _get_primary_game_region()
    if not region:
        return None if capture_row else f"❌ Không tìm thấy cửa sổ game để kiểm tra **{acc_name}**!"

    x, y = find_account_dots_for_check(acc_name)
    if x is None or y is None:
        return None if capture_row else f"❌ Không tìm thấy tài khoản **{acc_name}** trong cửa sổ game chính!"

    pyautogui.click(x, y)
    time.sleep(_action_delay(0.45))

    if capture_row:
        return capture_account_row_image(acc_name, x_coord=x, y_coord=y)

    status_region = (x - 320, y - 12, 120, 24)
    offline_path = _asset_path("assets", "status_offline.png")

    try:
        if os.path.exists(offline_path):
            is_offline = pyautogui.locateOnScreen(
                offline_path,
                region=status_region,
                confidence=0.7,
            )
            if is_offline:
                return f"🔴 Tài khoản **{acc_name}**: **OFFLINE** (Đang dừng)"
    except Exception:
        pass

    return f"🟢 Tài khoản **{acc_name}**: **ONLINE** (Đang chạy)"