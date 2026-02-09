from aiogram import Bot
from aiogram.types import Message

# TODO: подставь реальный ID канала
CHANNEL_ID = 7454321131


async def generate_article(thesis: str) -> str:
    """
    Здесь будет реальный вызов Mistral.
    Пока заглушка, чтобы протестировать цепочку.
    """
    return f"Черновик статьи по тезисам:\n\n{thesis}"


async def send_draft(bot: Bot, message: Message, article: str):
    """
    Отправляет пользователю черновик.
    """
    await message.answer(
        "Вот черновик статьи:\n\n"
        f"{article}\n\n"
        "Если всё ок, ответь сообщением «ок»."
    )


async def publish_to_channel(bot: Bot, message: Message, article: str):
    """
    Публикует фото + текст в канал.
    """
    photo = message.photo[-1].file_id if message.photo else None
    if photo:
        await bot.send_photo(chat_id=CHANNEL_ID, photo=photo, caption=article)
    else:
        await bot.send_message(chat_id=CHANNEL_ID, text=article)


async def process_new_photo(bot: Bot, message: Message):
    """
    Пользователь прислал фото с подписью‑тезисами.
    """
    thesis = message.caption or "(пустые тезисы)"
    article = await generate_article(thesis)
    await send_draft(bot, message, article)


async def process_ok(bot: Bot, message: Message):
    """
    Пользователь подтвердил «ок».
    Пока используем текст сообщения как статью.
    Потом сюда подставим сохранённый article.
    """
    article = message.text
    await publish_to_channel(bot, message, article)
    await message.answer("Опубликовал пост в канал ✅")

