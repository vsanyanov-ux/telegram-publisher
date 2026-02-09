import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.types import Message

from services import process_new_photo, process_text

API_TOKEN = "8426118781:AAGvjG3LWWE5AJYF8saT8SSEW-5UD2X9pA0"  # тот же, что BOT_TOKEN в services.py

logging.basicConfig(level=logging.INFO)

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


async def main():
    await dp.start_polling(bot, on_startup=on_startup)


if __name__ == "__main__":
    asyncio.run(main())

