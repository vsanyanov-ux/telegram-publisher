import os
import tempfile
from typing import Dict

import aiofiles
import httpx
from aiogram import Bot
from aiogram.types import Message
import mistralai

# === КОНФИГ ===
BOT_TOKEN = "8426118781:AAGvjG3LWWE5AJYF8saT8SSEW-5UD2X9pA0"         # тот же, что в polling_bot.py
CHANNEL_TOKEN = "8426118781:AAGvjG3LWWE5AJYF8saT8SSEW-5UD2X9pA0"          # один и тот же бот публикует в канал
CHANNEL_USERNAME = "@forma_test"
MISTRAL_API_KEY = "hj83AvvrZjredFYcMIyAN3fDbpYmmpit"

# === КЛИЕНТ MISTRAL И СОСТОЯНИЯ ===
client = mistralai.Mistral(api_key=MISTRAL_API_KEY)
user_states: Dict[int, dict] = {}


async def send_message(chat_id: int, text: str):
    """
    Служебная функция для отправки текста через HTTP API Telegram.
    Используем её там, где нет объекта Message.
    """
    url = f"https://api.telegram.org/bot8426118781:AAGvjG3LWWE5AJYF8saT8SSEW-5UD2X9pA0/sendMessage"
    data = {"chat_id": chat_id, "text": text}  # без parse_mode
    async with httpx.AsyncClient() as http:
        await http.post(url, data=data)


async def generate_article_for_chat(chat_id: int):
    """
    Полная логика генерации статьи через Mistral (из твоего FastAPI).
    """
    state = user_states[chat_id]
    theses = state["caption"] or "Напишите тезисы в подписи к картинке"

    messages = [
        {
            "role": "system",
            "content": (
            "Ты пишешь КОРОТКИЕ тексты для подписи к фото в Telegram-канале. "
            "Длина не больше 800–900 символов. "
            "Стиль живой, понятный, можно использовать эмодзи, но немного. "
            "Не делай заголовки и длинные вступления, сразу к сути."
            ),
        },
        {
            "role": "user",
            "content": f"Тезисы: {theses}\nНапиши статью для Telegram.",
        },
    ]

    try:
        response = client.chat.complete(
            model="mistral-large-latest",
            messages=messages,
            temperature=0.7,
            max_tokens=300, # вместо 1500
        )
        article = response.choices[0].message.content.strip()
        state["articles"].append(article)

        await send_message(
            chat_id,
            "Новая статья сгенерирована.\n\n"
            "Сейчас я буду отправлять её в виде файла, чтобы избежать проблем с форматированием."
        )
    except Exception as e:
        await send_message(chat_id, f"❌ Ошибка Mistral: {str(e)}")


async def publish_to_channel(file_id: str, article: str):
    url = f"https://api.telegram.org/bot7454321131:AAENfNcpoHu1cnsJcNQJwLoRvfv2ioljVeE/sendPhoto"
    data = {
        "chat_id": CHANNEL_USERNAME,
        "photo": file_id,
        "caption": article[:1024], #вместо 4000
        "parse_mode": "Markdown",
    }
    print("DEBUG file_id:", file_id)
    async with httpx.AsyncClient() as http:
        await http.post(url, data=data)


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

    await message.answer("✅ Фото получено!\n🤖 Генерирую статью...")
    await generate_article_for_chat(chat_id)


async def process_ok(bot: Bot, message: Message):
    """
    Пользователь отвечает «ок» / «да» / «yes» — публикуем последнюю статью.
    """
    chat_id = message.chat.id

    if chat_id not in user_states:
        await message.answer("❌ Сначала отправьте фото с тезисами!")
        return

    state = user_states[chat_id]
    article = state["articles"][-1]

    await publish_to_channel(state["file_id"], article)

    try:
        os.unlink(state["file_path"])
    except Exception:
        pass

    del user_states[chat_id]
    await message.answer("🎉 Статья опубликована в канал!")


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

    if text_lower in ["ок", "ok", "да", "yes"]:
        await process_ok(bot, message)

    elif text_lower in ["нет", "no"]:
        await message.answer("🔄 Генерирую новую статью...")
        await generate_article_for_chat(chat_id)

    else:
        await message.answer(
            "❓ Напишите:\n"
            "• `ок` — опубликовать в канал\n"
            "• `нет` — новую статью\n\n"
            f"Текущая статья:\n{state['articles'][-1][:500]}..."
        )

