import asyncio
import logging
import os
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.types import Message, CallbackQuery

from services import process_new_photo, process_text, process_ok, process_cancel, generate_article_for_chat

load_dotenv()

API_TOKEN = os.getenv("BOT_TOKEN")  # тот же, что BOT_TOKEN в services.py

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)

bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode="Markdown"))
dp = Dispatcher()

async def on_startup(dispatcher):
    await bot.delete_webhook(drop_pending_updates=True)  # отключаем webhook


@dp.message(F.photo)
async def handle_photo(message: Message):
    await process_new_photo(bot, message)


@dp.message(F.text)
async def handle_text(message: Message):
    await process_text(bot, message)


@dp.callback_query(F.data == "publish_ok")
async def callback_publish_ok(callback: CallbackQuery):
    await process_ok(bot, callback.message)
    await callback.answer()


@dp.callback_query(F.data == "publish_no")
async def callback_publish_no(callback: CallbackQuery):
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.message.answer("🔄 Генерирую новую статью...")
    await generate_article_for_chat(bot, callback.message.chat.id)
    await callback.answer()


@dp.callback_query(F.data == "publish_cancel")
async def callback_publish_cancel(callback: CallbackQuery):
    await process_cancel(bot, callback.message)
    await callback.answer()


async def main():
    await dp.start_polling(bot, on_startup=on_startup)


if __name__ == "__main__":
    asyncio.run(main())

