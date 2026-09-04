import base64
import io
import json
import secrets
import threading
import time

import mss
import pyautogui
from flask import Flask, jsonify, render_template_string, request
from PIL import Image

from config import USER_VIEW
from utils_gui import focus_game_window, get_game_window

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.1

app = Flask(__name__)
REMOTE_SESSION_TIMEOUT = 30
remote_session_lock = threading.Lock()
remote_session = None

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
  <title>ROK Bot Controller</title>
  <style>
    body {
      margin: 0;
      font-family: Arial, sans-serif;
      background: #1b1b2f;
      color: white;
      text-align: center;
    }
    h2 {
      margin: 12px 0 8px;
      color: #f7d6ff;
    }
    .stream-container {
      width: 98%;
      max-width: 820px;
      display: inline-block;
      border: 2px solid #7dc1ff;
      border-radius: 10px;
      overflow: hidden;
      background: #000;
      box-shadow: 0 4px 12px rgba(0,0,0,0.4);
      margin-bottom: 8px;
    }
    img {
      display: block;
      width: 100%;
      height: auto;
      cursor: crosshair;
      user-select: none;
    }
    .info {
      font-size: 13px;
      color: #b9fbc0;
      margin: 8px 10px 12px;
      background: #101320;
      border-radius: 6px;
      padding: 8px;
    }
    #keyboard-status {
      min-height: 18px;
      font-size: 13px;
      color: #ffd166;
      margin: 6px 10px 12px;
    }
    #loading {
      display: none;
      position: fixed;
      top: 50%;
      left: 50%;
      transform: translate(-50%, -50%);
      background: rgba(0,0,0,0.8);
      padding: 12px 18px;
      border-radius: 8px;
      z-index: 1000;
    }
    #keyboard-input {
      position: fixed;
      left: -100px;
      top: 0;
      width: 1px;
      height: 1px;
      opacity: 0;
    }
  </style>
</head>
<body>
  <h2>🎮 Bảng điều khiển ROK Bot</h2>
  <div class="stream-container">
    <img id="stream-screen" src="" alt="Đang tải hình ảnh..." onclick="handleClick(event)" />
  </div>
  <div class="info">💡 Chạm vào màn hình để click đúng vị trí trong game.</div>
  <div id="keyboard-status" aria-live="polite">Bàn phím web đã sẵn sàng.</div>
  <input id="keyboard-input" type="text" autocomplete="off" autocapitalize="off" spellcheck="false" aria-label="Bàn phím game" />
  <div id="loading">Đang xử lý...</div>

  <script>
    const sessionToken = "{{ session_token }}";
    const img = document.getElementById('stream-screen');
    const loading = document.getElementById('loading');
    const keyboardStatus = document.getElementById('keyboard-status');
    const keyboardInput = document.getElementById('keyboard-input');
    let keyQueue = Promise.resolve();

    function endpoint(path) {
      return path + '?session=' + encodeURIComponent(sessionToken);
    }

    function sendKey(key) {
      keyQueue = keyQueue.then(() => fetch(endpoint('/key'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ key: key })
        })
        .then(res => res.json())
        .then(data => {
          if (data.status === 'success') {
            keyboardStatus.textContent = 'Đã gửi phím: ' + key;
          }
        })
        .catch(() => {
          keyboardStatus.textContent = 'Không gửi được phím.';
        }));
      return keyQueue;
    }

    function focusKeyboard() {
      keyboardInput.focus({ preventScroll: true });
    }

    function updateScreen() {
      fetch(endpoint('/stream_frame'))
        .then(res => res.json())
        .then(data => {
          if (data.image) {
            img.src = 'data:image/jpeg;base64,' + data.image;
          }
        })
        .catch(() => {});
    }

    setInterval(updateScreen, 500);

    function handleClick(event) {
      focusKeyboard();
      loading.style.display = 'block';
      const rect = img.getBoundingClientRect();
      const clientX = event.clientX - rect.left;
      const clientY = event.clientY - rect.top;
      const scaleX = img.naturalWidth / rect.width;
      const scaleY = img.naturalHeight / rect.height;

      const realX = Math.round(clientX * scaleX);
      const realY = Math.round(clientY * scaleY);

      fetch(endpoint('/click'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ x: realX, y: realY })
      })
      .then(() => {
        loading.style.display = 'none';
      })
      .catch(() => {
        loading.style.display = 'none';
      });
    }

    document.addEventListener('keydown', function(event) {
      if (event.ctrlKey || event.altKey || event.metaKey) {
        return;
      }

      event.preventDefault();
      sendKey(event.key);
    });

    keyboardInput.addEventListener('keydown', function(event) {
      event.stopPropagation();
      if (event.ctrlKey || event.altKey || event.metaKey) {
        return;
      }
      if (event.key.length === 1 && event.key !== ' ') {
        return;
      }
      event.preventDefault();
      sendKey(event.key);
    });

    keyboardInput.addEventListener('input', function() {
      const value = keyboardInput.value;
      if (value) {
        sendKey(value[value.length - 1]);
        keyboardInput.value = '';
      }
    });

    document.addEventListener('touchstart', focusKeyboard, { passive: true });
    window.addEventListener('pagehide', function() {
      navigator.sendBeacon(endpoint('/release'));
    });
  </script>
</body>
</html>
"""

def open_remote_session(owner, account_name, owner_id=None):
    global remote_session
    now = time.monotonic()
    with remote_session_lock:
        if remote_session and now - remote_session["last_seen"] < REMOTE_SESSION_TIMEOUT:
            return None, remote_session["owner"]

        token = secrets.token_urlsafe(24)
        remote_session = {
            "token": token,
            "owner": owner,
            "owner_id": str(owner_id) if owner_id is not None else None,
            "account": account_name,
            "last_seen": now,
        }
        return token, owner


def close_remote_session(owner_id):
    global remote_session
    with remote_session_lock:
        if not remote_session:
            return False, None
        if remote_session["owner_id"] != str(owner_id):
            return False, remote_session["owner"]
        owner = remote_session["owner"]
        remote_session = None
        return True, owner


def remote_session_owner():
  global remote_session
  now = time.monotonic()
  with remote_session_lock:
    if not remote_session:
      return None
    if now - remote_session["last_seen"] >= REMOTE_SESSION_TIMEOUT:
      remote_session = None
      return None
    return remote_session["owner"]


def remote_session_url(base_url, token):
  separator = "&" if "?" in base_url else "?"
  return f"{base_url}{separator}session={token}"


def _touch_remote_session(token):
  global remote_session
  now = time.monotonic()
  with remote_session_lock:
    if not remote_session or remote_session["token"] != token:
      return False
    if now - remote_session["last_seen"] >= REMOTE_SESSION_TIMEOUT:
      remote_session = None
      return False
    remote_session["last_seen"] = now
    return True


def _require_remote_session():
  token = request.args.get("session")
  if not _touch_remote_session(token):
    return None, (jsonify({"status": "error", "message": "Remote session expired or busy"}), 403)
  return token, None


def get_game_view_rect():
    win = get_game_window()
    if not win:
        return None

    left = max(0, int(getattr(win, "left", 0)))
    top = max(0, int(getattr(win, "top", 0)))
    width = max(1, int(getattr(win, "width", 0)))
    height = max(1, int(getattr(win, "height", 0)))

    crop_left = left + max(USER_VIEW["margin_left"], int(USER_VIEW["offset_x"]))
    crop_top = top + max(USER_VIEW["margin_top"], int(USER_VIEW["offset_y"]))

    crop_width = min(max(USER_VIEW["min_width"], int(USER_VIEW["width"])), max(1, width - 20))
    crop_height = min(max(USER_VIEW["min_height"], int(USER_VIEW["height"])), max(1, height - 20))

    max_right = left + width - 10
    max_bottom = top + height - 12

    if crop_left + crop_width > max_right:
        crop_width = max(USER_VIEW["min_width"], max_right - crop_left)
    if crop_top + crop_height > max_bottom:
        crop_height = max(USER_VIEW["min_height"], max_bottom - crop_top)

    if crop_left < left:
        crop_left = left
    if crop_top < top:
        crop_top = top

    return {
        "left": crop_left,
        "top": crop_top,
        "width": max(1, crop_width),
        "height": max(1, crop_height),
    }


@app.route("/")
def home():
    token = request.args.get("session")
    if not _touch_remote_session(token):
        return "Phiên điều khiển không hợp lệ hoặc đã hết hạn.", 403
    return render_template_string(HTML_TEMPLATE, session_token=token)


@app.route("/stream_frame")
def stream_frame():
    _, error = _require_remote_session()
    if error:
        return error
    crop_area = get_game_view_rect()
    if not crop_area:
        return jsonify({"image": None})

    try:
        with mss.mss() as sct:
            sct_img = sct.grab(crop_area)
            image = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=85)
            img_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
            return jsonify({"image": img_base64})
    except Exception as exc:
        print(f"⚠️ Lỗi chụp màn hình: {exc}")
        return jsonify({"image": None})


@app.route("/click", methods=["POST"])
def handle_click():
    _, error = _require_remote_session()
    if error:
        return error
    data = request.get_json(force=True, silent=True) or {}
    rel_x = data.get("x")
    rel_y = data.get("y")

    if rel_x is None or rel_y is None:
        return jsonify({"status": "error", "message": "Missing click coordinates"})

    crop_area = get_game_view_rect()
    if not crop_area:
        return jsonify({"status": "error", "message": "Window not found"})

    focus_game_window()

    left = crop_area["left"]
    top = crop_area["top"]
    width = crop_area["width"]
    height = crop_area["height"]

    target_x = left + min(max(int(rel_x), 0), width)
    target_y = top + min(max(int(rel_y), 0), height)

    if left <= target_x <= (left + width) and top <= target_y <= (top + height):
        pyautogui.click(target_x, target_y)
        return jsonify({"status": "success", "x": target_x, "y": target_y})

    return jsonify({"status": "out_of_bounds", "x": target_x, "y": target_y})


@app.route("/key", methods=["POST"])
def handle_key():
    _, error = _require_remote_session()
    if error:
        return error
    data = request.get_json(force=True, silent=True) or {}
    key = data.get("key")

    if not isinstance(key, str) or not key or len(key) > 20:
        return jsonify({"status": "error", "message": "Invalid key"}), 400

    key_map = {
        " ": "space",
        "ArrowUp": "up",
        "ArrowDown": "down",
        "ArrowLeft": "left",
        "ArrowRight": "right",
        "Backspace": "backspace",
        "Delete": "delete",
        "Enter": "enter",
        "Escape": "esc",
        "Tab": "tab",
        "Home": "home",
        "End": "end",
        "PageUp": "pageup",
        "PageDown": "pagedown",
        "Insert": "insert",
    }
    pyautogui_keys = set(key_map.values()) | {
        "shift", "ctrl", "alt", "capslock", "escape", "win",
    }

    try:
        if not focus_game_window():
            return jsonify({"status": "error", "message": "Window not found"}), 404

        if key in key_map:
            pyautogui.press(key_map[key])
        elif key.lower() in pyautogui_keys:
            pyautogui.press(key.lower())
        elif len(key) == 1 and key.isprintable():
            pyautogui.write(key)
        else:
            return jsonify({"status": "error", "message": "Unsupported key"}), 400
    except Exception as exc:
        print(f"⚠️ Lỗi gửi phím: {exc}")
        return jsonify({"status": "error", "message": "Could not send key"}), 500

    return jsonify({"status": "success", "key": key})

@app.route("/release", methods=["POST", "GET"])
def release_remote_session():
    global remote_session
    token = request.args.get("session")
    with remote_session_lock:
        if remote_session and remote_session["token"] == token:
            remote_session = None
    return jsonify({"status": "released"})


def run_flask_in_thread():
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)


if __name__ == "__main__":
    focus_game_window()
    print("🌐 Web Server đang khởi động tại cổng 5000...")
    flask_thread = threading.Thread(target=run_flask_in_thread, daemon=True)
    flask_thread.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("⏹️ Đã dừng Web Server.")