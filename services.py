import os
import tempfile
from typing import Dict
from dotenv import load_dotenv

import aiofiles
import httpx
from aiogram import Bot
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
from mistralai.client import Mistral
from mistralai.client.models import SystemMessage, UserMessage

load_dotenv()

def get_action_keyboard():
    """Возвращает инлайн-клавиатуру с кнопками выбора действий."""
    buttons = [
        [
            InlineKeyboardButton(text="✅ Опубликовать", callback_data="publish_ok"),
            InlineKeyboardButton(text="🔄 Еще вариант", callback_data="publish_no")
        ],
        [
            InlineKeyboardButton(text="❌ Отмена", callback_data="publish_cancel")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# === КОНФИГ ===
BOT_TOKEN = os.getenv("BOT_TOKEN")         # тот же, что в polling_bot.py
CHANNEL_TOKEN = os.getenv("CHANNEL_TOKEN")          # один и тот же бот публикует в канал
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")

# === КЛИЕНТ MISTRAL И СОСТОЯНИЯ ===
client = Mistral(api_key=MISTRAL_API_KEY)
user_states: Dict[int, dict] = {}


async def send_message(chat_id: int, text: str):
    """
    Служебная функция для отправки текста через HTTP API Telegram.
    Используем её там, где нет объекта Message.
    """
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {"chat_id": chat_id, "text": text}  # без parse_mode
    async with httpx.AsyncClient() as http:
        await http.post(url, data=data)


async def generate_article_for_chat(bot: Bot, chat_id: int):
    """
    Полная логика генерации статьи через Mistral (из твоего FastAPI).
    """
    if chat_id not in user_states:
        await bot.send_message(chat_id, "❌ Ошибка: Сессия не найдена. Пожалуйста, отправьте фото еще раз.")
        return

    state = user_states[chat_id]
    theses = state["caption"] or "Напишите тезисы в подписи к картинке"

    messages = [
        SystemMessage(
            content=(
            "Ты пишешь статьи для Telegram-канала, которые будут использоваться как подпись к фото. "
            "Длина СТРОГО 800–900 символов (это критически важно, чтобы не превысить лимит). "
            "Стиль живой, понятный, используй среднее количество эмодзи. "
            "Не делай длинные заголовки и вступления, сразу к сути."
            ),
        ),
        UserMessage(
            content=f"Тезисы: {theses}\nНапиши короткую статью (800–900 символов) для Telegram.",
        ),
    ]

    try:
        response = client.chat.complete(
            model="mistral-large-latest",
            messages=messages,
            temperature=0.7,
            max_tokens=1500, 
        )
        article = response.choices[0].message.content.strip()
        state["articles"].append(article)

        # 1) сначала отправляем текст статьи на согласование
        await bot.send_message(chat_id, article)
        
        # 2) затем короткую подсказку с клавиатурой
        await bot.send_message(
            chat_id, 
            "Готово! Нажмите кнопку ниже 👇",
            reply_markup=get_action_keyboard()
        )

    except Exception as e:
        await bot.send_message(chat_id, f"❌ Ошибка Mistral: {str(e)}")


async def publish_to_channel(file_id: str, article: str):
    """
    Публикует статью в канал. 
    Если статья > 1024 символов — отправляем фото отдельно, а текст следом.
    """
    url_photo = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    url_message = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    async with httpx.AsyncClient() as http:
        if len(article) <= 1024:
            # Вариант 1: Короткая статья — всё в подписи
            data = {
                "chat_id": CHANNEL_USERNAME,
                "photo": file_id,
                "caption": article,
                "parse_mode": "Markdown",
            }
            await http.post(url_photo, data=data)
        else:
            # Вариант 2: Длинная статья — фото + текст отдельным сообщением
            # 1) Отправляем фото
            await http.post(url_photo, data={"chat_id": CHANNEL_USERNAME, "photo": file_id})
            # 2) Отправляем полный текст
            await http.post(url_message, data={
                "chat_id": CHANNEL_USERNAME, 
                "text": article,
                "parse_mode": "Markdown"
            })


# === ФУНКЦИИ ДЛЯ POLLING-БОТА ===

async def process_new_photo(bot: Bot, message: Message):
    """
    Пользователь прислал фото с подписью-тезисами (polling).
    Скачиваем файл, сохраняем состояние, запускаем генерацию статьи.
    """
    chat_id = message.chat.id

    # получаем file_path через getFile
    photo = message.photo[-1]
    file_id = photo.file_id

    async with httpx.AsyncClient() as http:
        resp = await http.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/getFile",
            json={"file_id": file_id},
        )
        file_info = resp.json()
        if not file_info.get("ok"):
            await message.answer("❌ Ошибка получения файла")
            return

        file_path = file_info["result"]["file_path"]
        download_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"

        file_resp = await http.get(download_url)
        suffix = ".jpg" if "jpeg" in file_resp.headers.get("content-type", "") else ".png"
        fd, temp_path = tempfile.mkstemp(suffix=suffix)
        os.close(fd)

        async with aiofiles.open(temp_path, "wb") as f:
            await f.write(file_resp.content)

    caption = message.caption or ""
    user_states[chat_id] = {
        "file_id": file_id,
        "file_path": temp_path,
        "caption": caption,
        "articles": [],
    }

    if not caption:
        await message.answer("✅ Фото получено! Теперь, пожалуйста, отправьте **текст (тезисы)** для статьи.")
    else:
        await message.answer("✅ Фото получено!\n🤖 Генерирую статью...")
        await generate_article_for_chat(bot, chat_id)


async def process_ok(bot: Bot, message: Message):
    """
    Пользователь отвечает «ок» / «да» / «yes» — публикуем последнюю статью.
    """
    chat_id = message.chat.id

    if chat_id not in user_states:
        await message.answer("❌ Сначала отправьте фото с тезисами!", reply_markup=ReplyKeyboardRemove())
        return

    state = user_states[chat_id]
    article = state["articles"][-1]

    await publish_to_channel(state["file_id"], article)

    try:
        await message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    try:
        os.unlink(state["file_path"])
    except Exception:
        pass

    del user_states[chat_id]
    await message.answer("🎉 Статья опубликована в канал!", reply_markup=ReplyKeyboardRemove())


async def process_cancel(bot: Bot, message: Message):
    """
    Отмена процесса публикации и очистка состояния.
    """
    chat_id = message.chat.id
    
    try:
        await message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    if chat_id in user_states:
        state = user_states[chat_id]
        try:
            os.unlink(state["file_path"])
        except Exception:
            pass
        del user_states[chat_id]
    
    await message.answer("❌ Процесс отменен. Состояние очищено.", reply_markup=ReplyKeyboardRemove())


async def process_text(bot: Bot, message: Message):
    """
    Обработка произвольного текста: 'нет' → новая статья, остальное — подсказка.
    """
    chat_id = message.chat.id
    text_lower = message.text.lower().strip()

    if chat_id not in user_states:
        await message.answer("❌ Сначала отправьте фото с тезисами!")
        return

    state = user_states[chat_id]

    if "отмена" in text_lower or "cancel" in text_lower:
        await process_cancel(bot, message)
        return

    # Если фото есть, а тезисов еще нет — считаем этот текст тезисами
    if not state.get("caption"):
        state["caption"] = text_lower
        await message.answer("✅ Тезисы получены!\n🤖 Генерирую статью...")
        await generate_article_for_chat(bot, chat_id)
        return

    if "ок" in text_lower or "ok" in text_lower or "да" in text_lower or "yes" in text_lower:
        await process_ok(bot, message)

    elif "нет" in text_lower or "no" in text_lower:
        await message.answer("🔄 Генерирую новую статью...")
        await generate_article_for_chat(bot, chat_id)

    elif "отмена" in text_lower or "cancel" in text_lower:
        await process_cancel(bot, message)

    else:
        await message.answer(
            "❓ Выберите действие на клавиатуре или напишите:\n"
            "• `ок` — опубликовать в канал\n"
            "• `нет` — новую статью\n"
            "• `отмена` — сбросить всё\n\n"
            f"Текущая статья:\n{state['articles'][-1][:500]}...",
            reply_markup=get_action_keyboard()
        )

