import json
import os
from datetime import datetime

DATA_FILE = "data.json"


def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_chat(data, chat_id: int):
    """Получить данные чата (или создать новый)"""
    cid = str(chat_id)
    if cid not in data:
        data[cid] = {"users": {}}
    return data[cid]


def get_user(chat_id: int, user_id: int):
    """Получить данные пользователя в конкретном чате"""
    data = load_data()
    chat = get_chat(data, chat_id)
    uid = str(user_id)

    if uid not in chat["users"]:
        chat["users"][uid] = {
            "xp": 0,
            "level": 1,
            "messages": 0,
            "warns": 0,
            "bio": "",
            "nickname": ""
        }
        save_data(data)

    return chat["users"][uid]


def update_user(chat_id: int, user_id: int, updates: dict):
    """Обновить данные пользователя в конкретном чате"""
    data = load_data()
    chat = get_chat(data, chat_id)
    uid = str(user_id)

    if uid not in chat["users"]:
        chat["users"][uid] = {"xp": 0, "level": 1, "messages": 0, "warns": 0, "bio": "", "nickname": ""}

    chat["users"][uid].update(updates)
    save_data(data)


def get_top_users(chat_id: int, limit: int = 10):
    """Топ пользователей по опыту в конкретном чате"""
    data = load_data()
    chat = get_chat(data, chat_id)
    users = chat.get("users", {})

    sorted_users = sorted(users.items(), key=lambda x: x[1].get("xp", 0), reverse=True)
    return sorted_users[:limit]


# Названия рангов по уровням
RANKS = {
    1: ("🆕 Новичок", "новичок"),
    2: ("↔️ Туда-Сюда", "туда-сюда"),
    3: ("🤸 На опыте", "на опыте"),
    4: ("🐁 Почти мышь", "почти мышь"),
    5: ("🐭 Мышь", "мышь"),
    6: ("🐀 Крыска", "крыска"),
    7: ("🐀 Взрослая осознанная Крыса", "взрослая осознанная крыса"),
    8: ("👑 Легенда", "легенда"),
    9: ("💀 Правая рука Надин", "правая рука Надин"),
}

# Таблица опыта
LEVEL_XP = {
    1: 0,      # Стартовый уровень
    2: 1000,   # 1000 XP для 2-го уровня
    3: 3000,
    4: 5000,
    5: 10000,
    6: 20000,
    7: 25000,
    8: 40000,
    9: 70000   # 1000 + 5000 = 6000 XP для 3-го
    # Продолжи сам по образцу:
    # 4: 16000,  # +10000
    # 5: 36000,  # +20000
}


def get_level_from_xp(xp: int) -> int:
    level = 1
    for lvl, needed in sorted(LEVEL_XP.items()):
        if xp >= needed:
            level = lvl
    return level


def get_xp_for_level(level: int) -> tuple[int, int, int]:
    current = LEVEL_XP.get(level, 0)
    next_level = None
    for lvl in sorted(LEVEL_XP.keys()):
        if lvl > level:
            next_level = lvl
            break
    if next_level:
        needed = LEVEL_XP[next_level]
    else:
        needed = current
    return current, needed, needed - current


def get_rank_info(level: int):
    rank_name = "💬 Участник"
    for lvl, (name, _) in sorted(RANKS.items()):
        if level >= lvl:
            rank_name = name
    return rank_name

# ==================== АДМИНИСТРИРОВАНИЕ ====================

def get_admin_level(chat_id: int, user_id: int) -> int:
    """Возвращает уровень админа (0 если не админ)"""
    from config import ADMINS
    cid = str(chat_id)
    uid = str(user_id)
    return ADMINS.get(cid, {}).get(uid, 0)


def can_moderate(chat_id: int, admin_id: int, target_id: int) -> bool:
    """Проверяет, может ли админ модерировать цель (уровень админа выше)"""
    admin_level = get_admin_level(chat_id, admin_id)
    target_level = get_admin_level(chat_id, target_id)

    if admin_level == 0:
        return False
    if target_level >= admin_level:
        return False  # Нельзя трогать равного или старшего
    return True


def add_warn(chat_id: int, user_id: int, reason: str = "") -> int:
    """Добавляет предупреждение, возвращает общее количество предов"""
    user = get_user(chat_id, user_id)
    warns = user.get("warns", 0) + 1

    # Сохраняем историю предов
    warn_history = user.get("warn_history", [])
    warn_history.append({
        "reason": reason,
        "date": __import__("datetime").datetime.now().isoformat()
    })

    update_user(chat_id, user_id, {
        "warns": warns,
        "warn_history": warn_history
    })
    return warns


def reset_warns(chat_id: int, user_id: int):
    """Сбрасывает все предупреждения"""
    update_user(chat_id, user_id, {"warns": 0, "warn_history": []})


def is_muted(chat_id: int, user_id: int) -> bool:
    """Проверяет, замучен ли пользователь"""
    from datetime import datetime
    user = get_user(chat_id, user_id)
    muted_until = user.get("muted_until", "")
    if not muted_until:
        return False
    try:
        until = datetime.fromisoformat(muted_until)
        if datetime.now() > until:
            # Мут истёк — снимаем
            update_user(chat_id, user_id, {"muted_until": ""})
            return False
        return True
    except:
        return False


def mute_user(chat_id: int, user_id: int, minutes: int):
    """Выдаёт мут на N минут"""
    from datetime import datetime, timedelta
    until = datetime.now() + timedelta(minutes=minutes)
    update_user(chat_id, user_id, {"muted_until": until.isoformat()})


def unmute_user(chat_id: int, user_id: int):
    """Снимает мут досрочно"""
    update_user(chat_id, user_id, {"muted_until": ""})

# ==================== АДМИНИСТРИРОВАНИЕ (С СОХРАНЕНИЕМ) ====================

def get_chat_admins(chat_id: int) -> dict:
    """Получает всех админов чата из базы"""
    data = load_data()
    cid = str(chat_id)
    if cid not in data:
        data[cid] = {"users": {}, "admins": {}}
        save_data(data)
    return data[cid].get("admins", {})


def save_chat_admins(chat_id: int, admins: dict):
    """Сохраняет админов чата в базу"""
    data = load_data()
    cid = str(chat_id)
    if cid not in data:
        data[cid] = {"users": {}, "admins": {}}
    data[cid]["admins"] = admins
    save_data(data)


def get_admin_level(chat_id: int, user_id: int) -> int:
    """Возвращает уровень админа (0 если не админ)"""
    admins = get_chat_admins(chat_id)
    return admins.get(str(user_id), 0)


def set_admin_level(chat_id: int, user_id: int, level: int):
    """Устанавливает уровень админа (0 = удалить)"""
    admins = get_chat_admins(chat_id)
    if level == 0:
        admins.pop(str(user_id), None)
    else:
        admins[str(user_id)] = level
    save_chat_admins(chat_id, admins)


def can_moderate(chat_id: int, admin_id: int, target_id: int) -> bool:
    """Проверяет, может ли админ модерировать цель"""
    admin_level = get_admin_level(chat_id, admin_id)
    target_level = get_admin_level(chat_id, target_id)
    if admin_level == 0:
        return False
    if target_level >= admin_level:
        return False
    return True


# ==================== АНКЕТЫ И ГОЛОСОВАНИЕ ====================

def create_application(user_id: int, data: dict):
    """Создаёт анкету пользователя"""
    app_id = str(int(datetime.now().timestamp()))
    app = {
        "id": app_id,
        "user_id": user_id,
        "data": data,
        "votes": {},
        "status": "pending",
        "created_at": datetime.now().isoformat()
    }
    all_apps = load_data()
    if "applications" not in all_apps:
        all_apps["applications"] = {}
    all_apps["applications"][app_id] = app
    save_data(all_apps)
    return app_id


def get_application(app_id: str) -> dict | None:
    """Получает анкету по ID"""
    data = load_data()
    return data.get("applications", {}).get(app_id)


def vote_application(app_id: str, admin_id: int, vote: str):
    """Голосование за анкету"""
    data = load_data()
    if "applications" not in data:
        return
    app = data["applications"].get(app_id)
    if not app:
        return
    app["votes"][str(admin_id)] = vote
    save_data(data)


def get_pending_applications() -> list:
    """Возвращает все нерассмотренные анкеты"""
    data = load_data()
    apps = data.get("applications", {})
    return [a for a in apps.values() if a["status"] == "pending"]


def update_application_status(app_id: str, status: str):
    """Обновляет статус анкеты"""
    data = load_data()
    if "applications" in data and app_id in data["applications"]:
        data["applications"][app_id]["status"] = status
        save_data(data)


def set_join_date(chat_id: int, user_id: int):
    """Устанавливает дату вступления в чат"""
    user = get_user(chat_id, user_id)
    if not user.get("join_date"):
        update_user(chat_id, user_id, {"join_date": datetime.now().isoformat()})


def get_weekly_activity(chat_id: int, user_id: int) -> int:
    """Среднее количество сообщений за день"""
    user = get_user(chat_id, user_id)
    total_msgs = user.get("messages", 0)
    join_date_str = user.get("join_date")
    if join_date_str:
        try:
            join_date = datetime.fromisoformat(join_date_str)
            days_in_chat = (datetime.now() - join_date).days + 1
            return round(total_msgs / days_in_chat, 1)
        except:
            pass
    return total_msgs