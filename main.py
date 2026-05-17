import asyncio
import logging

from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.exceptions import TelegramForbiddenError

from config import BOT_TOKEN
from database import (
    get_user, update_user, get_rank_info, get_level_from_xp,
    get_xp_for_level, LEVEL_XP, RANKS, get_top_users,
    get_admin_level, can_moderate, add_warn, reset_warns,
    is_muted, mute_user, unmute_user, set_admin_level, get_chat_admins,
    create_application, get_application, vote_application,
    get_pending_applications, update_application_status,
    set_join_date, get_weekly_activity, load_data, save_data
)
from config import ADMIN_CHAT_ID, MAIN_CHAT_ID, APPLICATIONS_TOPIC_ID, MY_USER_ID, ADMIN_VOTES_NEEDED

from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

class ApplicationForm(StatesGroup):
    waiting_name = State()
    waiting_age = State()
    waiting_district = State()
    waiting_visit = State()
    waiting_hobbies = State()
    waiting_photo = State()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

async def set_tag(chat_id: int, user_id: int, tag: str):
    """Устанавливает тег участника в чате"""
    try:
        # По документации aiogram [citation:1]
        result: bool = await bot.set_chat_member_tag(
            chat_id=chat_id,
            user_id=user_id,
            tag=tag
        )
        logger.info(f"Тег установлен: chat={chat_id}, user={user_id}, tag={tag}, result={result}")
        return result
    except Exception as e:
        logger.error(f"Ошибка установки тега: {e}")
        return False

async def show_all_nicknames(message: types.Message):
    """Показать все ники участников чата"""
    chat_id = message.chat.id
    data = load_data()
    cid = str(chat_id)

    if cid not in data or "users" not in data[cid]:
        await message.answer("Пока никто не установил ник")
        return

    users = data[cid]["users"]
    nicknames = []

    for uid, u in users.items():
        nick = u.get("nickname", "")
        if nick:
            # Пробуем получить имя из Telegram
            name = u.get("full_name", "")
            if not name:
                try:
                    member = await bot.get_chat_member(chat_id, int(uid))
                    name = member.user.full_name
                except:
                    name = f"Участник {uid}"

            nicknames.append((name, nick))

    if not nicknames:
        await message.answer("Пока никто не установил ник")
        return

    nicknames.sort(key=lambda x: x[1].lower())

    text = "📛 <b>Все ники участников</b>\n\n"
    for name, nick in nicknames:
        text += f"• {name} — <b>{nick}</b>\n"

    await message.answer(text, parse_mode="HTML")

async def show_participant(message: types.Message):
    """Показать информацию об участнике"""
    chat_id = message.chat.id

    target_id = None
    target_name = "Неизвестный"

    # Способ 1: Ответ на сообщение
    if message.reply_to_message:
        target_id = message.reply_to_message.from_user.id
        target_name = message.reply_to_message.from_user.full_name

    # Способ 2: Тег @username
    elif "@" in message.text:
        parts = message.text.split("@", 1)
        if len(parts) > 1:
            username = parts[1].split()[0].strip()
            data = load_data()
            for cid, chat_data in data.items():
                for uid, u in chat_data.get("users", {}).items():
                    if u.get("username", "").lower() == username.lower():
                        target_id = int(uid)
                        target_name = u.get("full_name", f"@{username}")
                        break
                if target_id:
                    break

    if target_id is None:
        await message.answer("❌ Не удалось найти пользователя. Ответь на его сообщение или укажи @username\n"
                             "Пример: <b>Бот участник @username</b>", parse_mode="HTML")
        return

    # Получаем данные пользователя
    user = get_user(chat_id, target_id)

    xp = user.get("xp", 0)
    msgs = user.get("messages", 0)
    warns = user.get("warns", 0)
    level = get_level_from_xp(xp)
    rank_name = get_rank_info(level)

    # Админ-уровень
    admin_level = get_admin_level(chat_id, target_id)
    admin_names = {1: "🛡️ Модератор", 2: "⚔️ Ст. модератор", 3: "👑 Главный админ"}

    # Дата вступления
    join_date_str = user.get("join_date", "Неизвестно")
    if join_date_str and join_date_str != "Неизвестно":
        try:
            join_date = datetime.fromisoformat(join_date_str)
            join_date_str = join_date.strftime("%d.%m.%Y")
        except:
            pass

    # Средняя активность
    weekly_activity = get_weekly_activity(chat_id, target_id)

    # Ник (пока пусто)
    nickname = user.get("nickname", "") or "—"

    # Username
    username = user.get("username", "")
    if username:
        username = f"@{username}"
    else:
        username = "скрыт"

    # Формируем ответ
    text = (
        f"👤 <b>Участник: {target_name}</b>\n\n"
        f"📌 Username: {username}\n"
        f"{rank_name}\n"
        f"├ Уровень: <b>{level}</b>\n"
        f"├ Опыт: <b>{xp} XP</b>\n"
    )

    if admin_level > 0:
        text += f"├ Админ: <b>{admin_names.get(admin_level, '?')}</b> (ур. {admin_level})\n"

    text += (
        f"├ Сообщений: <b>{msgs}</b>\n"
        f"├ Активность: <b>~{weekly_activity} сообщ./день</b>\n"
        f"├ Предов: <b>{warns}/3</b>\n"
        f"├ В чате с: <b>{join_date_str}</b>\n"
        f"├ Ник: <b>{nickname}</b>\n"
        f"└ ID: <code>{target_id}</code>"
    )

    await message.answer(text, parse_mode="HTML")

async def show_application(message: types.Message):
    """Показать анкету пользователя по @username или пересланному сообщению"""
    chat_id = message.chat.id

    target_id = None
    target_name = "Неизвестный"

    if message.reply_to_message:
        target_id = message.reply_to_message.from_user.id
        target_name = message.reply_to_message.from_user.full_name
    elif "@" in message.text:
        parts = message.text.split("@", 1)
        if len(parts) > 1:
            username = parts[1].split()[0].strip()
            data = load_data()
            for cid, chat_data in data.items():
                for uid, u in chat_data.get("users", {}).items():
                    if u.get("username", "").lower() == username.lower():
                        target_id = int(uid)
                        target_name = u.get("full_name", f"@{username}")
                        break
                if target_id:
                    break

    if target_id is None:
        await message.answer("❌ Не удалось найти пользователя. Ответь на его сообщение или укажи @username")
        return

    data = load_data()
    apps = data.get("applications", {})

    user_apps = []
    for app_id, app in apps.items():
        if app.get("user_id") == target_id and app.get("status") == "approved":
            user_apps.append(app)

    if not user_apps:
        await message.answer(f"❌ У пользователя {target_name} нет одобренных анкет")
        return

    app = user_apps[-1]
    app_data = app["data"]

    app_text = (
        f"📋 <b>Анкета #{app['id']}</b>\n\n"
        f"👤 Имя: <b>{app_data.get('name', '—')}</b>\n"
        f"🎂 Возраст: <b>{app_data.get('age', '—')}</b>\n"
        f"📍 Район: <b>{app_data.get('district', '—')}</b>\n"
        f"📅 Посещение: <b>{app_data.get('visit', '—')}</b>\n"
        f"📌 Username: {app_data.get('username', '—')}\n\n"
        f"💬 Увлечения:\n{app_data.get('hobbies', '—')}"
    )

    # Отправляем прямо в этот чат
    photo_id = app_data.get('photo_id')
    if photo_id:
        await bot.send_photo(
            chat_id,
            photo_id,
            caption=app_text,
            message_thread_id=message.message_thread_id,
            parse_mode="HTML"
        )
    else:
        await message.answer(app_text, parse_mode="HTML")

async def show_my_rank(message: types.Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    user = get_user(chat_id, user_id)

    xp = user["xp"]
    msgs = user["messages"]
    warns = user.get("warns", 0)
    level = get_level_from_xp(xp)

    if level != user["level"]:
        update_user(chat_id, user_id, {"level": level})

    current_xp, next_xp, _ = get_xp_for_level(level)
    progress = xp - current_xp
    needed = next_xp - current_xp if next_xp > current_xp else progress

    rank_name = get_rank_info(level)
    next_rank_name = get_rank_info(level + 1)

    if next_rank_name != rank_name:
        next_line = f"└ Следующий статус: **{next_rank_name}**"
    else:
        next_line = f"└ До следующего статуса: **{needed - progress} XP**"

    admin_level = get_admin_level(chat_id, user_id)
    admin_line = f"├ Админ-уровень: **{admin_level}**\n" if admin_level > 0 else ""

    text = (
        f"📊 {message.from_user.full_name}\n"
        f"{rank_name}\n"
        f"├ Уровень: **{level}**\n"
        f"{admin_line}"
        f"├ Опыт: **{progress}/{needed}**\n"
        f"├ Сообщений: **{msgs}**\n"
        f"├ Предов: **{warns}/3**\n"
        f"{next_line}"
    )

    await message.answer(text, parse_mode="Markdown")


async def show_help(message: types.Message):
    admin_level = get_admin_level(message.chat.id, message.from_user.id)

    text = "🤖 <b>Доступные команды</b>\n\n"
    text += "• <b>Бот мой статус</b> — личная статистика\n"
    text += "• <b>Бот статусы</b> — все статусы и уровни\n"
    text += "• <b>Бот топ</b> — топ участников\n"
    text += "• <b>Бот анкета</b> — анкета пользователя\n"
    text += "• <b>Бот справка</b> — этот список\n"
    text += "• <b>Бот участник</b> — информация об участнике\n"
    text += "• <b>Бот дай мне ник</b> — установить себе ник\n"
    text += "• <b>Бот все ники</b> — список всех ников\n"

    if admin_level >= 1:
        text += "\n🛡️ <b>Модератор (ур. 1+):</b>\n"
     
        text += "• <b>Бот мут [минуты]</b> — замутить\n"
        text += "• <b>Бот снять мут</b> — досрочно снять мут\n"
        text += "• <b>Бот тег всех</b> — отметить всех участников чата\n"

    if admin_level >= 2:
        text += "\n⚔️ <b>Ст. модератор (ур. 2+):</b>\n"
        text += "• <b>Бот кик</b> — исключить из чата\n"
        text += "• Бот пред [причина] — выдать предупреждение\n"
        text += "• <b>Бот снять пред</b> — сбросить предупреждения\n"
        text += "• <b>Бот бан</b> — забанить навсегда\n"

    if admin_level >= 3:
        text += "\n👑 <b>Главный админ (ур. 3):</b>\n"
        text += "• <b>Бот назначить [уровень]</b> — назначить админа\n"
        text += "• <b>Бот снять админ</b> — разжаловать админа\n"
        text += "• <b>Бот админы</b> — список администраторов\n"
        text += "• <b>Бот очистка</b> — удалить из базы вышедших участников\n"
        text += "• <b>Бот разбан</b> — снять бан участника\n"

    await message.answer(text, parse_mode="HTML")


async def show_ranks_info(message: types.Message):
    text = "📊 <b>Система статусов</b>\n\n"

    for level, (emoji_name, role_name) in sorted(RANKS.items()):
        xp_needed = LEVEL_XP.get(level, "?")
        text += f"{emoji_name} — с <b>{level}</b> уровня (нужно <b>{xp_needed} XP</b>)\n"
        text += f"   Роль: <i>{role_name}</i>\n\n"

    text += "💡 <b>Как получить опыт:</b>\n"
    text += "• 1 XP за 10 символов (минимум 1)\n"
    text += "• Бот мой статус — проверить свой статус\n"
    text += "• Бот справка — список команд"

    await message.answer(text, parse_mode="HTML")


async def show_top(message: types.Message):
    chat_id = message.chat.id
    top_users = get_top_users(chat_id)

    if not top_users:
        await message.answer("Пока никто не заработал опыт в этом чате!")
        return

    text = "🏆 <b>Топ по опыту</b>\n\n"
    for i, (uid, u) in enumerate(top_users, 1):
        level = get_level_from_xp(u["xp"])
        rank = get_rank_info(level)

        try:
            member = await bot.get_chat_member(chat_id, int(uid))
            name = member.user.full_name
            username = member.user.username
            if username:
                name = f"{name}"
        except:
            name = f"Участник {uid}"

        text += f"{i}. {rank} — <b>{name}</b>\n"
        text += f"   └ {u['xp']} XP (ур. {level}, {u['messages']} сообщ.)\n\n"

    await message.answer(text, parse_mode="HTML")

# ==================== ВСПОМОГАТЕЛЬНАЯ: ПОЛУЧИТЬ ЦЕЛЬ ====================

async def get_target(message: types.Message):
    """
    Получает цель: либо из ответа на сообщение, либо по тегу/username в тексте.
    Возвращает (user_id, full_name) или (None, None)
    """
    # Способ 1: Ответ на сообщение
    if message.reply_to_message:
        return message.reply_to_message.from_user.id, message.reply_to_message.from_user.full_name

    # Способ 2: Тег в тексте
    text = message.text
    if "@" in text:
        # Ищем username после @
        parts = text.split("@", 1)
        if len(parts) > 1:
            username = parts[1].split()[0].strip()  # Берём до первого пробела
            try:
                # Пытаемся найти пользователя в чате по username
                chat_id = message.chat.id
                # Telegram API не даёт прямой поиск по username в чате,
                # поэтому пробуем через get_chat_member
                # Но нам нужен user_id... Самый надёжный способ — попросить цель написать что-то
                # Упростим: сохраняем маппинг username -> user_id при каждом сообщении
                from database import load_data, save_data
                data = load_data()
                cid = str(chat_id)

                # Ищем пользователя по username в данных чата
                for uid, u in data.get(cid, {}).get("users", {}).items():
                    if u.get("username", "").lower() == username.lower():
                        return int(uid), u.get("full_name", f"@{username}")

                return None, f"@{username} (не найден в базе)"
            except:
                return None, f"@{username}"

    return None, None


# ==================== АДМИН-ДЕЙСТВИЯ ====================

async def do_unban(message: types.Message, admin_id: int, admin_level: int):
    """Разбанить пользователя (уровень 3+)"""
    if admin_level < 3:
        await message.answer("❌ Недостаточно прав (нужен уровень 3+)")
        return

    target_id, target_name = await get_target(message)

    if target_id is None:
        if target_name:
            await message.answer(f"❌ Пользователь {target_name} не найден.")
        else:
            await message.answer("❌ Ответь на сообщение или укажи @username\nПример: <b>Бот разбан @user</b>", parse_mode="HTML")
        return

    chat_id = message.chat.id

    try:
        await bot.unban_chat_member(chat_id, target_id)
        await message.answer(f"✅ <b>{target_name}</b> разбанен и может вернуться в чат", parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

async def clean_users(message: types.Message):
    """Удаляет из базы пользователей, которых нет в чате"""
    chat_id = message.chat.id
    user_id = message.from_user.id
    admin_level = get_admin_level(chat_id, user_id)

    if admin_level < 3:
        await message.answer("❌ Только главный админ может очищать базу")
        return

    await message.answer("🔄 Проверяю список участников...")

    data = load_data()
    cid = str(chat_id)

    if cid not in data or "users" not in data[cid]:
        await message.answer("✅ База пуста, нечего очищать")
        return

    users = data[cid]["users"]
    removed = 0
    total = len(users)

    # Проверяем каждого пользователя
    for uid in list(users.keys()):
        try:
            member = await bot.get_chat_member(chat_id, int(uid))
            if member.status in ["left", "kicked"]:
                del users[uid]
                removed += 1
        except:
            # Не удалось получить — значит пользователь не в чате
            del users[uid]
            removed += 1

    save_data(data)

    await message.answer(
        f"✅ Очистка завершена!\n\n"
        f"👥 Было в базе: <b>{total}</b>\n"
        f"🗑 Удалено: <b>{removed}</b>\n"
        f"👤 Осталось: <b>{len(users)}</b>",
        parse_mode="HTML"
    )

async def tag_all(message: types.Message):
    """Отметить всех участников чата"""
    chat_id = message.chat.id
    user_id = message.from_user.id
    admin_level = get_admin_level(chat_id, user_id)

    if admin_level < 1:
        await message.answer("❌ Недостаточно прав (нужен уровень 1+)")
        return

    text = message.text
    prefix = "бот тег всех"
    reason = text[len(prefix):].strip() if text.lower().startswith(prefix) else ""

    try:
        data = load_data()
        cid = str(chat_id)
        
        mentions = []
        if cid in data and "users" in data[cid]:
            for uid in data[cid]["users"]:
                try:
                    member = await bot.get_chat_member(chat_id, int(uid))
                    user = member.user
                    
                    # Используем HTML-mention — это работает как отметка
                    if user.username:
                        mentions.append(f"@{user.username}")
                    else:
                        # Для пользователей без username используем HTML mention
                        mentions.append(f"<a href=\"tg://user?id={uid}\">{user.first_name}</a>")
                except:
                    pass

        if not mentions:
            await message.answer("❌ Не удалось получить список участников")
            return

        # Разбиваем на части
        header = "📢 <b>Внимание всем!</b>\n" if not reason else f"📢 <b>{reason}</b>\n\n"
        
        # Отправляем одним сообщением, если влазит
        full_text = header + " ".join(mentions)
        
        if len(full_text) <= 4096:
            await message.answer(full_text, parse_mode="HTML")
        else:
            # Разбиваем на части
            part = header
            for mention in mentions:
                if len(part) + len(mention) + 1 > 4000:
                    await message.answer(part, parse_mode="HTML")
                    part = header
                part += mention + " "
            if part != header:
                await message.answer(part, parse_mode="HTML")

    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

async def show_admins(message: types.Message):
    """Показать список админов чата"""
    chat_id = message.chat.id
    chat_admins = get_chat_admins(chat_id)

    if not chat_admins:
        await message.answer("В этом чате нет назначенных администраторов")
        return

    level_names = {1: "Модератор", 2: "Ст. модератор", 3: "Главный админ"}
    text = "👑 <b>Администраторы чата</b>\n\n"

    for uid, level in sorted(chat_admins.items(), key=lambda x: x[1], reverse=True):
        try:
            member = await bot.get_chat_member(chat_id, int(uid))
            name = member.user.full_name
        except:
            name = f"Участник {uid}"

        text += f"• {name} — <b>{level_names.get(level, '?')}</b> (ур. {level})\n"

    await message.answer(text, parse_mode="HTML")

async def do_warn(message: types.Message, admin_id: int, admin_level: int):
    """Выдать предупреждение"""
    target_id, target_name = await get_target(message)

    if target_id is None:
        if target_name:
            await message.answer(f"❌ Пользователь {target_name} не найден в базе чата. Попроси его написать любое сообщение.")
        else:
            await message.answer("❌ Ответь на сообщение или укажи @username\nПример: <b>Бот пред @user причина</b>", parse_mode="HTML")
        return

    chat_id = message.chat.id

    if not can_moderate(chat_id, admin_id, target_id):
        await message.answer("❌ Нельзя выдать пред этому пользователю (равный или выше по уровню)")
        return

    # Извлекаем причину
    text = message.text
    # Убираем команду и username из текста для причины
    parts = text.split(maxsplit=2)
    reason = parts[2] if len(parts) > 2 else "Без причины"
    # Если причина содержит @, убираем его
    if "@" in reason:
        reason = reason.split("@", 1)[0].strip() or "Без причины"

    warns = add_warn(chat_id, target_id, reason)

    if warns >= 3:
        try:
            await bot.ban_chat_member(chat_id, target_id)
            reset_warns(chat_id, target_id)
            await message.answer(
                f"🚫 <b>{target_name}</b> забанен (3/3 предов)\nПричина: {reason}",
                parse_mode="HTML"
            )
        except Exception as e:
            await message.answer(f"❌ Ошибка при бане: {e}")
    else:
        await message.answer(
            f"⚠️ <b>{target_name}</b> получил пред ({warns}/3)\nПричина: {reason}",
            parse_mode="HTML"
        )


async def do_mute(message: types.Message, admin_id: int, admin_level: int):
    """Замутить пользователя"""
    target_id, target_name = await get_target(message)

    if target_id is None:
        if target_name:
            await message.answer(f"❌ Пользователь {target_name} не найден в базе чата.")
        else:
            await message.answer("❌ Ответь на сообщение или укажи @username\nПример: <b>Бот мут @user 30</b>", parse_mode="HTML")
        return

    chat_id = message.chat.id

    if not can_moderate(chat_id, admin_id, target_id):
        await message.answer("❌ Нельзя замутить этого пользователя")
        return

    # Извлекаем минуты
    parts = message.text.split()
    minutes = 30
    for part in parts:
        if part.isdigit():
            minutes = int(part)
            break

    mute_user(chat_id, target_id, minutes)

    await message.answer(
        f"🔇 <b>{target_name}</b> замучен на <b>{minutes}</b> минут",
        parse_mode="HTML"
    )

    try:
        from datetime import datetime
        await bot.restrict_chat_member(
            chat_id, target_id,
            permissions=types.ChatPermissions(can_send_messages=False),
            until_date=datetime.now().timestamp() + minutes * 60
        )
    except:
        pass


async def do_kick(message: types.Message, admin_id: int, admin_level: int):
    """Кикнуть пользователя"""
    if admin_level < 2:
        await message.answer("❌ Недостаточно прав (нужен уровень 2+)")
        return

    target_id, target_name = await get_target(message)

    if target_id is None:
        if target_name:
            await message.answer(f"❌ Пользователь {target_name} не найден в базе чата.")
        else:
            await message.answer("❌ Ответь на сообщение или укажи @username\nПример: <b>Бот кик @user</b>", parse_mode="HTML")
        return

    chat_id = message.chat.id

    if not can_moderate(chat_id, admin_id, target_id):
        await message.answer("❌ Нельзя кикнуть этого пользователя")
        return

    try:
        await bot.ban_chat_member(chat_id, target_id)
        await bot.unban_chat_member(chat_id, target_id)
        await message.answer(f"👢 <b>{target_name}</b> исключён из чата", parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


async def do_ban(message: types.Message, admin_id: int, admin_level: int):
    """Забанить пользователя"""
    if admin_level < 2:
        await message.answer("❌ Недостаточно прав (нужен уровень 2+)")
        return

    target_id, target_name = await get_target(message)

    if target_id is None:
        if target_name:
            await message.answer(f"❌ Пользователь {target_name} не найден в базе чата.")
        else:
            await message.answer("❌ Ответь на сообщение или укажи @username\nПример: <b>Бот бан @user</b>", parse_mode="HTML")
        return

    chat_id = message.chat.id

    if not can_moderate(chat_id, admin_id, target_id):
        await message.answer("❌ Нельзя забанить этого пользователя")
        return

    try:
        await bot.ban_chat_member(chat_id, target_id)
        await message.answer(f"🚫 <b>{target_name}</b> забанен навсегда", parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


async def do_appoint(message: types.Message, admin_id: int, admin_level: int):
    """Назначить админа (только уровень 3)"""
    if admin_level < 3:
        await message.answer("❌ Только главный админ может назначать")
        return

    target_id, target_name = await get_target(message)

    if target_id is None:
        if target_name:
            await message.answer(f"❌ Пользователь {target_name} не найден в базе.")
        else:
            await message.answer("❌ Ответь на сообщение или укажи @username\nПример: <b>Бот назначить @user 2</b>", parse_mode="HTML")
        return

    chat_id = message.chat.id

    parts = message.text.split()
    new_level = 1
    for part in parts:
        if part.isdigit():
            new_level = int(part)
            if new_level < 1 or new_level > 3:
                await message.answer("❌ Уровень должен быть 1, 2 или 3")
                return
            break

    set_admin_level(chat_id, target_id, new_level)

    level_names = {1: "Модератор", 2: "Ст. модератор", 3: "Главный админ"}

    await message.answer(
        f"✅ <b>{target_name}</b> назначен администратором\n"
        f"Уровень: <b>{new_level}</b> ({level_names.get(new_level, 'Неизвестно')})",
        parse_mode="HTML"
    )


async def do_remove_admin(message: types.Message, admin_id: int, admin_level: int):
    """Снять админа (только уровень 3)"""
    if admin_level < 3:
        await message.answer("❌ Только главный админ может снимать")
        return

    target_id, target_name = await get_target(message)

    if target_id is None:
        if target_name:
            await message.answer(f"❌ Пользователь {target_name} не найден в базе.")
        else:
            await message.answer("❌ Ответь на сообщение или укажи @username\nПример: <b>Бот снять админ @user</b>", parse_mode="HTML")
        return

    chat_id = message.chat.id

    if get_admin_level(chat_id, target_id) == 0:
        await message.answer("❌ Этот пользователь не администратор")
        return

    set_admin_level(chat_id, target_id, 0)
    await message.answer(f"✅ <b>{target_name}</b> больше не администратор", parse_mode="HTML")

# ==================== КОМАНДЫ ====================

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    if message.chat.type == "private":
        # Проверяем, не подавал ли уже заявку
        await message.answer(
            "👋 Привет! Чтобы попасть в чат, нужно заполнить анкету.\n\n"
            "Напиши <b>анкета</b>, чтобы начать.\n"
            "Или <b>отмена</b>, чтобы выйти.",
            parse_mode="HTML"
        )
    else:
        await message.answer("👋 Я в чате! Команды: Бот справка")

# ==================== АНКЕТА В ЛИЧКЕ ====================

@dp.message(F.text.lower() == "анкета")
async def start_application(message: types.Message, state: FSMContext):
    if message.chat.type != "private":
        return

    user_id = message.from_user.id

    # Проверяем, есть ли уже одобренная анкета
    data = load_data()
    apps = data.get("applications", {})

    has_approved = False
    for app in apps.values():
        if app.get("user_id") == user_id and app.get("status") == "approved":
            has_approved = True
            break

    # Проверяем, не в чате ли уже пользователь
    try:
        member = await bot.get_chat_member(MAIN_CHAT_ID, user_id)
        if member.status in ["member", "administrator", "creator"]:
            await message.answer("✅ Ты уже в чате! Команды: Бот справка")
            return
    except:
        pass  # Не в чате — продолжаем

    # Если был в чате ранее, но вышел/кикнут — нужно заполнить заново
    if has_approved:
        await message.answer(
            "⚠️ Ты уже подавал анкету ранее, но покинул чат.\n\n"
            "Для повторного вступления нужно заполнить анкету заново."
        )

    await state.set_state(ApplicationForm.waiting_name)
    await message.answer("📝 <b>Анкета на вступление в чат</b>\n\n"
                         "Шаг 1/6: Как тебя зовут? (имя или ник)",
                         parse_mode="HTML")


@dp.message(F.text.lower() == "отмена")
async def cancel_application(message: types.Message, state: FSMContext):
    if message.chat.type != "private":
        return

    current_state = await state.get_state()
    if current_state is None:
        return

    await state.clear()
    await message.answer("❌ Анкета отменена. Напиши <b>анкета</b> чтобы начать заново.", parse_mode="HTML")


@dp.message(ApplicationForm.waiting_name)
async def process_name(message: types.Message, state: FSMContext):
    if message.text and message.text.lower() == "отмена":
        await cancel_application(message, state)
        return

    await state.update_data(name=message.text)
    await state.set_state(ApplicationForm.waiting_age)
    await message.answer("Шаг 2/6: Сколько тебе лет?")


@dp.message(ApplicationForm.waiting_age)
async def process_age(message: types.Message, state: FSMContext):
    if message.text and message.text.lower() == "отмена":
        await cancel_application(message, state)
        return

    await state.update_data(age=message.text)
    await state.set_state(ApplicationForm.waiting_district)
    await message.answer("Шаг 3/6: В каком районе ты живёшь?")


@dp.message(ApplicationForm.waiting_district)
async def process_district(message: types.Message, state: FSMContext):
    if message.text and message.text.lower() == "отмена":
        await cancel_application(message, state)
        return

    await state.update_data(district=message.text)
    await state.set_state(ApplicationForm.waiting_visit)
    await message.answer("Шаг 4/6: Как часто можешь посещать события?\n"
                         "(например: каждую неделю, раз в месяц, редко)")


@dp.message(ApplicationForm.waiting_visit)
async def process_visit(message: types.Message, state: FSMContext):
    if message.text and message.text.lower() == "отмена":
        await cancel_application(message, state)
        return

    await state.update_data(visit=message.text)
    await state.set_state(ApplicationForm.waiting_hobbies)
    await message.answer("Шаг 5/6: Расскажи о своих увлечениях, хобби, интересах?")


@dp.message(ApplicationForm.waiting_hobbies)
async def process_hobbies(message: types.Message, state: FSMContext):
    if message.text and message.text.lower() == "отмена":
        await cancel_application(message, state)
        return

    await state.update_data(hobbies=message.text)
    await state.set_state(ApplicationForm.waiting_photo)
    await message.answer("Шаг 6/6: Пришли свою фотографию 📸\n"
                         "(просто отправь фото как обычно, без сжатия)")


@dp.message(ApplicationForm.waiting_photo, F.photo)
async def process_photo(message: types.Message, state: FSMContext):
    # Получаем фото в лучшем качестве
    photo = message.photo[-1]
    file_id = photo.file_id

    # Собираем все данные
    data = await state.get_data()
    await state.clear()

    user_id = message.from_user.id
    username = message.from_user.username or "нет"

    # Создаём анкету
    app_id = create_application(user_id, {
        "name": data["name"],
        "age": data["age"],
        "district": data["district"],
        "visit": data["visit"],
        "hobbies": data["hobbies"],
        "photo_id": file_id,
        "username": f"@{username}",
        "user_id": user_id
    })

    # Отправляем в админский чат
    admin_text = (
        f"📝 <b>Новая анкета #{app_id}</b>\n\n"
        f"👤 Имя: <b>{data['name']}</b>\n"
        f"🎂 Возраст: <b>{data['age']}</b>\n"
        f"📍 Район: <b>{data['district']}</b>\n"
        f"📅 Посещение: <b>{data['visit']}</b>\n"
        f"📌 Username: @{username}\n\n"
        f"💬 Увлечения:\n{data['hobbies']}\n\n"
        f"<i>Проголосуйте:</i>"
    )

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Принять", callback_data=f"vote_{app_id}_yes"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"vote_{app_id}_no")
        ]
    ])

    # Сначала отправляем фото с подписью
    await bot.send_photo(
        ADMIN_CHAT_ID,
        file_id,
        caption=admin_text,
        parse_mode="HTML",
        reply_markup=keyboard
    )

    await message.answer(
        "✅ Твоя анкета отправлена администраторам на рассмотрение!\n"
        "Я напишу тебе, когда будет решение.",
        parse_mode="HTML"
    )


# Если прислал не фото на шаге 6
@dp.message(ApplicationForm.waiting_photo)
async def process_photo_invalid(message: types.Message):
    await message.answer("❌ Пожалуйста, пришли именно фотографию (не документ, не текст).")


# ==================== ГОЛОСОВАНИЕ (колбэки) ====================

from aiogram.types import CallbackQuery

@dp.callback_query(F.data.startswith("vote_"))
async def process_vote(callback: CallbackQuery):
    print(f"DEBUG VOTE: Старт голосования")
    print(f"DEBUG VOTE: admin_id={callback.from_user.id}, data={callback.data}")
    
    admin_id = callback.from_user.id
    admin_level = get_admin_level(ADMIN_CHAT_ID, admin_id)
    print(f"DEBUG VOTE: admin_level={admin_level}")
    
    if admin_level < 1:
        await callback.answer("❌ Только администраторы могут голосовать", show_alert=True)
        return
    
    parts = callback.data.split("_")
    app_id = parts[1]
    vote = parts[2]
    print(f"DEBUG VOTE: app_id={app_id}, vote={vote}")
    
    vote_application(app_id, admin_id, vote)
    print(f"DEBUG VOTE: Голос сохранён")
    
    app = get_application(app_id)
    if not app:
        await callback.answer("Анкета не найдена", show_alert=True)
        return
    
    print(f"DEBUG VOTE: Анкета найдена, статус={app['status']}")
    
    yes_count = sum(1 for v in app["votes"].values() if v == "yes")
    no_count = sum(1 for v in app["votes"].values() if v == "no")
    total_admins = len(get_chat_admins(ADMIN_CHAT_ID))
    voted_count = len(app["votes"])
    
    print(f"DEBUG VOTE: yes={yes_count}, no={no_count}, voted={voted_count}, total_admins={total_admins}")
    
    # Обновляем сообщение
    try:
        vote_text = callback.message.caption or callback.message.text or ""
        status_line = f"\n\n🗳 Голоса: ✅ {yes_count} | ❌ {no_count} (из {total_admins} админов)"
        
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text=f"✅ Принять ({yes_count})", callback_data=f"vote_{app_id}_yes"),
                InlineKeyboardButton(text=f"❌ Отклонить ({no_count})", callback_data=f"vote_{app_id}_no")
            ]
        ])
        
        await callback.message.edit_caption(caption=vote_text + status_line, reply_markup=keyboard, parse_mode="HTML")
        print(f"DEBUG VOTE: Сообщение обновлено")
    except Exception as e:
        print(f"DEBUG VOTE: Ошибка обновления - {e}")
    
    # Проверка на завершение голосования
    if voted_count >= 1:
        print(f"DEBUG VOTE: Голосование завершено, yes={yes_count}, no={no_count}")
        
        if yes_count > no_count:
            print(f"DEBUG VOTE: ПРИНЯТ")
            update_application_status(app_id, "approved")
            
            # Отправляем пользователю
            try:
                invite_link = await bot.create_chat_invite_link(
                    MAIN_CHAT_ID,
                    member_limit=1,
                    name=f"Приглашение для {app['data']['name']}"
                )
                await bot.send_message(
                    app["user_id"],
                    f"🎉 <b>Твоя анкета одобрена!</b>\n\n"
                    f"Добро пожаловать в чат!\n"
                    f"Твоя ссылка: {invite_link.invite_link}",
                    parse_mode="HTML"
                )
                print(f"DEBUG VOTE: Приглашение отправлено")
            except Exception as e:
                print(f"DEBUG VOTE: Ошибка приглашения - {e}")
            
                        # Отправляем в основной чат
            try:
                app_text = (
                    f"📋 <b>Анкета #{app_id} — ПРИНЯТ</b>\n\n"
                    f"👤 {app['data']['name']}\n"
                    f"🎂 {app['data']['age']}\n"
                    f"📍 {app['data']['district']}\n"
                    f"📅 {app['data']['visit']}\n"
                    f"📌 {app['data']['username']}\n"
                    f"💬 {app['data']['hobbies']}"
                )

                # Отправляем фото с подписью
                photo_id = app['data'].get('photo_id')
                if photo_id:
                    if APPLICATIONS_TOPIC_ID:
                        await bot.send_photo(
                            MAIN_CHAT_ID,
                            photo_id,
                            caption=app_text,
                            message_thread_id=APPLICATIONS_TOPIC_ID,
                            parse_mode="HTML"
                        )
                    else:
                        await bot.send_photo(
                            MAIN_CHAT_ID,
                            photo_id,
                            caption=app_text,
                            parse_mode="HTML"
                        )
                else:
                    # Если фото нет — просто текст
                    if APPLICATIONS_TOPIC_ID:
                        await bot.send_message(
                            MAIN_CHAT_ID,
                            app_text,
                            message_thread_id=APPLICATIONS_TOPIC_ID,
                            parse_mode="HTML"
                        )
                    else:
                        await bot.send_message(
                            MAIN_CHAT_ID,
                            app_text,
                            parse_mode="HTML"
                        )
                print(f"DEBUG VOTE: Анкета в основной чат отправлена")
            except Exception as e:
                print(f"DEBUG VOTE: Ошибка отправки в чат - {e}")
            
            await callback.message.edit_caption(
                caption=vote_text + f"\n\n✅ <b>ПРИНЯТ</b>",
                parse_mode="HTML"
            )
            
        else:
            print(f"DEBUG VOTE: ОТКЛОНЁН")
            update_application_status(app_id, "rejected")
            
            await bot.send_message(
                app["user_id"],
                f"😔 <b>Твоя анкета отклонена.</b>",
                parse_mode="HTML"
            )
            
            await callback.message.edit_caption(
                caption=vote_text + f"\n\n❌ <b>ОТКЛОНЁН</b>",
                parse_mode="HTML"
            )
        
        print(f"DEBUG VOTE: Готово")
    
    await callback.answer()


@dp.message(Command("rank"))
async def cmd_rank(message: types.Message):
    await show_my_rank(message)


# ==================== ОБРАБОТЧИК СООБЩЕНИЙ ====================

@dp.message()
async def on_message(message: types.Message):
     if message.sticker:
        print(f"Sticker file_id: {message.sticker.file_id}")
        await message.answer(f"file_id: `{message.sticker.file_id}`", parse_mode="Markdown")
    if message.chat.type == "private":
        await message.answer("🚫 Я работаю только в группах. Добавь меня в чат!")
        return

    if message.text is None:
        return
    if message.text.startswith("/"):
        return

    text_lower = message.text.lower()
    chat_id = message.chat.id
    user_id = message.from_user.id
    admin_level = get_admin_level(chat_id, user_id)
    print(f"DEBUG: chat_id={chat_id}, thread_id={message.message_thread_id}")
     # --- Временный отлов стикеров (показывает file_id) ---
    if message.sticker:
        sticker_id = message.sticker.file_id
        await message.answer(f"ID стикера:\n`{sticker_id}`", parse_mode="Markdown")
        return

    # --- Триггеры на стикеры ---

    for word in STICKER_TRIGGERS:
        if word in text_lower:
            sticker_id = STICKER_TRIGGERS[word]
            await message.answer_sticker(sticker_id)
            return

    # --- Команды для всех --
    
    if text_lower.startswith("бот дай мне ник"):
        prefix = "бот дай мне ник"
        nickname = message.text[len(prefix):].strip()

        if not nickname:
            await message.answer("❌ Укажи ник после команды\n"
                                 "Пример: <b>Бот дай мне ник КрутойЧел</b>\n\n"
                                 "Максимум 20 символов",
                                 parse_mode="HTML")
            return

        nickname = nickname[:20].replace("@", "")

        update_user(chat_id, user_id, {"nickname": nickname})

        await message.answer(f"✅ Твой ник установлен: <b>{nickname}</b>\n"
                             f"Смотреть все ники: Бот все ники", parse_mode="HTML")
        return

    if text_lower == "бот все ники":
        await show_all_nicknames(message)
        return
    if text_lower.startswith("бот участник"):
        await show_participant(message)
        return
    if text_lower.startswith("бот анкета"):
        await show_application(message)
        return
    if text_lower == "бот мой статус":
        await show_my_rank(message)
        return
    if text_lower == "бот статусы":
        await show_ranks_info(message)
        return
    if text_lower == "бот топ":
        await show_top(message)
        return
    if text_lower == "бот справка":
        await show_help(message)
        return

        # --- Админ-команды ---
    if text_lower.startswith("бот разбан"):
        if admin_level < 3:
            await message.answer("❌ Недостаточно прав")
            return
        await do_unban(message, user_id, admin_level)
        return
    if text_lower == "бот очистка":
        if admin_level < 3:
            await message.answer("❌ Только главный админ")
            return
        await clean_users(message)
        return
    if text_lower.startswith("бот тег всех"):
        await tag_all(message)
        return
    # Сначала точные совпадения (до startswith!)
    if text_lower == "бот снять мут":
        if admin_level < 1:
            await message.answer("❌ Недостаточно прав")
            return

        target_id, target_name = await get_target(message)

        if target_id is None:
            if target_name:
                await message.answer(f"❌ Пользователь {target_name} не найден в базе.")
            else:
                await message.answer("❌ Ответь на сообщение или укажи @username\nПример: <b>Бот снять мут @user</b>", parse_mode="HTML")
            return

        if not is_muted(chat_id, target_id):
            await message.answer(f"❌ {target_name} не в муте")
            return

        unmute_user(chat_id, target_id)

        try:
            await bot.restrict_chat_member(
                chat_id, target_id,
                permissions=types.ChatPermissions(
                    can_send_messages=True,
                    can_send_media=True,
                    can_send_other=True,
                    can_add_web_page_previews=True
                )
            )
        except:
            pass

        await message.answer(f"🔊 <b>{target_name}</b> размучен досрочно", parse_mode="HTML")
        return

    if text_lower == "бот снять пред":
        if admin_level < 2:
            await message.answer("❌ Недостаточно прав")
            return
        target_id, target_name = await get_target(message)
        if target_id is None:
            await message.answer("❌ Ответь на сообщение или укажи @username")
            return
        reset_warns(chat_id, target_id)
        await message.answer(f"✅ Преды сброшены для {target_name}")
        return

    if text_lower == "бот кик":
        if admin_level < 2:
            await message.answer("❌ Недостаточно прав")
            return
        await do_kick(message, user_id, admin_level)
        return

    if text_lower == "бот бан":
        if admin_level < 2:
            await message.answer("❌ Недостаточно прав")
            return
        await do_ban(message, user_id, admin_level)
        return

    if text_lower == "бот снять админ":
        if admin_level < 3:
            await message.answer("❌ Только главный админ")
            return
        await do_remove_admin(message, user_id, admin_level)
        return

    if text_lower == "бот админы":
        await show_admins(message)
        return

    # Теперь startswith (порядок важен!)
    if text_lower.startswith("бот мут"):
        if admin_level < 1:
            await message.answer("❌ Недостаточно прав")
            return
        await do_mute(message, user_id, admin_level)
        return

    if text_lower.startswith("бот пред"):
        if admin_level < 2:
            await message.answer("❌ Недостаточно прав")
            return
        await do_warn(message, user_id, admin_level)
        return

    if text_lower.startswith("бот назначить"):
        if admin_level < 3:
            await message.answer("❌ Только главный админ")
            return
        await do_appoint(message, user_id, admin_level)
        return

    # --- Проверка мута ---
    if is_muted(chat_id, user_id):
        await message.delete()
        return

    # --- Начисление опыта ---
    user = get_user(chat_id, user_id)

    xp_gain = len(message.text) // 10 + 1
    new_xp = user["xp"] + xp_gain
    new_level = get_level_from_xp(new_xp)

    update_user(chat_id, user_id, {
        "xp": new_xp,
        "messages": user["messages"] + 1,
        "level": new_level,
        "username": message.from_user.username or "",
        "full_name": message.from_user.full_name
    })
    
    # Устанавливаем дату вступления при первом сообщении
    if not user.get("join_date"):
        update_user(chat_id, user_id, {"join_date": datetime.now().isoformat()})

    if new_level > user["level"] and message.chat.type != "private":
        new_rank = get_rank_info(new_level)
        await message.answer(
            f"🎉 {message.from_user.full_name} получил новый статус: **{new_rank}** (уровень {new_level})!",
            parse_mode="Markdown"
        )


# ==================== ЗАПУСК ====================
# ==================== ОБРАБОТЧИКИ СИСТЕМНЫХ СОБЫТИЙ ====================

@dp.chat_member()
async def on_chat_member_update(update: types.ChatMemberUpdated):
    chat_id = update.chat.id
    user_id = update.from_user.id
    old_status = update.old_chat_member.status
    new_status = update.new_chat_member.status

    if old_status in ["member", "administrator", "creator"] and new_status in ["left", "kicked"]:
        # Удаляем данные пользователя из этого чата
        data = load_data()
        cid = str(chat_id)
        uid = str(user_id)

        if cid in data and "users" in data[cid] and uid in data[cid]["users"]:
            del data[cid]["users"][uid]
            logger.info(f"Пользователь {user_id} удалён из чата {chat_id}, данные очищены")

        # Аннулируем все одобренные анкеты пользователя
        if "applications" in data:
            for app_id, app in data["applications"].items():
                if app.get("user_id") == user_id and app.get("status") == "approved":
                    data["applications"][app_id]["status"] = "expired"
                    logger.info(f"Анкета {app_id} пользователя {user_id} аннулирована")

        save_data(data)

async def main():
    print("DEBUG: Начало main()")
    logger.info("Запуск бота...")

    # Авто-назначение тебя главным админом в обоих чатах
    MY_USER_ID = 635717705

    # Основной чат
    if get_admin_level(MAIN_CHAT_ID, MY_USER_ID) == 0:
        set_admin_level(MAIN_CHAT_ID, MY_USER_ID, 3)
        logger.info(f"Назначен главный админ в основном чате: {MY_USER_ID}")

    # Админский чат (для голосования)
    if get_admin_level(ADMIN_CHAT_ID, MY_USER_ID) == 0:
        set_admin_level(ADMIN_CHAT_ID, MY_USER_ID, 3)
        logger.info(f"Назначен главный админ в админском чате: {MY_USER_ID}")

    print("DEBUG: Запуск polling...")
    await dp.start_polling(bot, drop_pending_updates=True)

if __name__ == "__main__":
    print("DEBUG: Старт скрипта")
    import traceback
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"DEBUG: ОШИБКА - {e}")
        traceback.print_exc()