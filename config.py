import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

BOT_TOKEN = os.getenv("BOT_TOKEN")
VPS_IP = os.getenv("VPS_IP")
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN chưa được set trong .env")
if not VPS_IP:
    raise ValueError("❌ VPS_IP chưa được set trong .env")


DOTS_OFFSET_X = 648
WINDOW_TITLES = ("Rise of Kingdoms Bot", "Rise of Kingdoms")

ACCOUNT_ROW_Y_BASE = 12
ACCOUNT_ROW_HEIGHT = 21
ACCOUNT_VISIBLE_ROWS = 7
ACCOUNT_CAPTURE_WIDTH = 560


GAME_VIEW = {
    "offset_x": 5,
    "offset_y": 40,
    "width": 692,
    "height": 148,
    "margin_left": 0,
    "margin_top": 0,
    "min_width": 500,
    "min_height": 140,
}

USER_VIEW = {
    "offset_x": 0,
    "offset_y":190,
    "width": 960,
    "height": 630,     
    "margin_left": 0,
    "margin_top": 150,
    "min_width": 650,
    "min_height": 300,
}

USER_ACCOUNTS_FILE = os.path.join(BASE_DIR, "user_accounts.json")
ADMIN_USERS_FILE = os.path.join(BASE_DIR, "admin_users.json")
ACCS_DIR = os.path.join(BASE_DIR, "assets", "accs")
os.makedirs(ACCS_DIR, exist_ok=True)