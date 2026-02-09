import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.types import Message

from services import process_new_photo, process_ok

API_TOKEN = "8426118781:AAGvjG3LWWE5AJYF8saT8SSEW-5UD2X9pA0"  # сюда вставь токен своего основного бота

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()


@dp.message(F.photo)
async def handle_photo(message: Message):
    await process_new_photo(bot, message)


@dp.message(F.text.lower() == "ок")
async def handle_ok(message: Message):
    await process_ok(bot, message)


@dp.message(F.text)
async def handle_text(message: Message):
    await message.answer("Жду фото с подписью‑тезисами или «ок».")


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

