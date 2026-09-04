import threading

from bot_discord import start_bot
from web_server import run_flask_in_thread


def start_web_server_thread():
    thread = threading.Thread(target=run_flask_in_thread, daemon=True)
    thread.start()
    return thread


if __name__ == "__main__":
    start_web_server_thread()
    start_bot()