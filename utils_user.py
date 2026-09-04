import json
import os

from config import ADMIN_USERS_FILE, USER_ACCOUNTS_FILE


def normalize_account_name(acc_name):
    if acc_name is None:
        return None
    
    acc_str = str(acc_name).strip()
    
    if acc_str.isdigit():
        return acc_str.zfill(3)
    
    return acc_str


def load_user_accounts():
    if not os.path.exists(USER_ACCOUNTS_FILE):
        return {}

    try:
        with open(USER_ACCOUNTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_user_account(user_id, acc_name):
    normalized = normalize_account_name(acc_name)
    if not normalized:
        return
    
    accounts = load_user_accounts()
    accounts[str(user_id)] = normalized

    with open(USER_ACCOUNTS_FILE, "w", encoding="utf-8") as f:
        json.dump(accounts, f, ensure_ascii=False, indent=4)


def get_acc_for_user(user_id, provided_acc=None):
    if provided_acc is not None and str(provided_acc).strip():
        return normalize_account_name(provided_acc)

    accounts = load_user_accounts()
    user_key = str(user_id)
    value = accounts.get(user_key)
    return normalize_account_name(value) if value else None


def load_admin_users():
    if not os.path.exists(ADMIN_USERS_FILE):
        return set()

    try:
        with open(ADMIN_USERS_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
        return {str(user_id) for user_id in data} if isinstance(data, list) else set()
    except Exception:
        return set()


def save_admin_user(user_id):
    admin_users = load_admin_users()
    admin_users.add(str(user_id))
    with open(ADMIN_USERS_FILE, "w", encoding="utf-8") as file:
        json.dump(sorted(admin_users), file, ensure_ascii=False, indent=4)


def is_admin_user(user_id):
    return str(user_id) in load_admin_users()
