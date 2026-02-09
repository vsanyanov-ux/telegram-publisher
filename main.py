import os
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import tempfile
import aiofiles
import httpx
import mistralai
from typing import Optional, Dict
import json

load_dotenv()

app = FastAPI(title="Telegram Post Publisher")
client = mistralai.Mistral(api_key="7nf9fCMHEhPZa0nkQSgq0F5alCO80NhS")
user_states: Dict[int, dict] = {}


# Токены
BOT_TOKEN = "8426118781:AAGvjG3LWWE5AJYF8saT8SSEW-5UD2X9pA0"
CHANNEL_TOKEN = "7454321131:AAENfNcpoHu1cnsJcNQJwLoRvfv2ioljVeE"
MISTRAL_API_KEY = "7nf9fCMHEhPZa0nkQSgq0F5alCO80NhS"
CHANNEL_USERNAME = "@FormaVolgodonskChanelBot"
DOMAIN = "https://158.255.1.153"

class Update(BaseModel):
    update_id: int
    message: Optional[dict] = None

@app.post("/webhook")
async def webhook(update: Update):
    if not update.message:
        return {"ok": True}
    
    message = update.message
    chat_id = message["chat"]["id"]
    
    if "text" in message:
        await handle_text(chat_id, message["text"])
    elif "photo" in message:
        await handle_photo(chat_id, message)
    
    return {"ok": True}

async def handle_photo(chat_id: int, message: dict):
    photo = message["photo"][-1]
    file_id = photo["file_id"]
    
    # Получаем file_path
    async with httpx.AsyncClient() as http:
        resp = await http.post(f"https://api.telegram.org/bot{BOT_TOKEN}/getFile", json={"file_id": file_id})
        file_info = resp.json()
        if not file_info["ok"]:
            await send_message(chat_id, "❌ Ошибка получения файла")
            return
        
        file_path = file_info["result"]["file_path"]
        download_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
        
        # Скачиваем и сохраняем
        file_resp = await http.get(download_url)
        suffix = '.jpg' if 'jpeg' in file_resp.headers.get('content-type', '') else '.png'
        fd, temp_path = tempfile.mkstemp(suffix=suffix)
        os.close(fd)
        
        async with aiofiles.open(temp_path, 'wb') as f:
            await f.write(file_resp.content)
        
        caption = message.get("caption", "")
        user_states[chat_id] = {
            "file_id": file_id,
            "file_path": temp_path,
            "caption": caption,
            "articles": []
        }
        
        await send_message(chat_id, "✅ Фото получено!\n🤖 Генерирую статью...")
        await generate_article(chat_id)

async def handle_text(chat_id: int, text: str):
    if chat_id not in user_states:
        await send_message(chat_id, "❌ Сначала отправьте фото с тезисами!")
        return
    
    state = user_states[chat_id]
    text_lower = text.lower().strip()
    
    if text_lower in ["ок", "ok", "да", "yes"]:
        article = state["articles"][-1]
        await publish_to_channel(state["file_id"], article)
        # Очистка временного файла
        try:
            os.unlink(state["file_path"])
        except:
            pass
        del user_states[chat_id]
        await send_message(chat_id, "🎉 Статья опубликована в канал!")
        
    elif text_lower in ["нет", "no"]:
        await send_message(chat_id, "🔄 Генерирую новую статью...")
        await generate_article(chat_id)
        
    else:
        await send_message(chat_id, 
            "❓ Напишите:\n"
            "• `ок` — опубликовать в канал\n"
            "• `нет` — новую статью\n\n"
            f"Текущая статья:\n{state['articles'][-1][:500]}...")

async def generate_article(chat_id: int):
    state = user_states[chat_id]
    theses = state["caption"] or "Напишите тезисы в подписи к фото"
    
    messages = [
        ChatMessage(role="system", content="""Ты пишешь короткие статьи для Telegram-канала. 
        Сделай текст живым, интересным, 400-600 слов. 
        Добавь эмодзи, markdown форматирование (## заголовки, **жирный**).
        Структура: заголовок, введение, основная часть, вывод."""), 
        ChatMessage(role="user", content=f"Тезисы: {theses}\nНапиши статью для Telegram.")
    ]
    
    try:
        response = client.chat.complete(
            model="mistral-large-latest",
            messages=messages,
            temperature=0.7,
            max_tokens=1500
        )
        article = response.choices[0].message.content.strip()
        
        state["articles"].append(article)
        
        await send_message(chat_id, 
            f"📝 **Новая статья:**\n\n{article}\n\n"
            f"_✅ `ок` — опубликовать | ❌ `нет` — новая_")
            
    except Exception as e:
        await send_message(chat_id, f"❌ Ошибка Mistral: {str(e)}")

async def publish_to_channel(file_id: str, article: str):
    url = f"https://api.telegram.org/bot{CHANNEL_TOKEN}/sendPhoto"
    data = {
        "chat_id": CHANNEL_USERNAME,
        "photo": file_id,
        "caption": article[:4000],  # Лимит Telegram
        "parse_mode": "Markdown"
    }
    async with httpx.AsyncClient() as http:
        resp = await http.post(url, data=data)
        return resp.json()

async def send_message(chat_id: int, text: str):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    async with httpx.AsyncClient() as http:
        await http.post(url, data=data)

@app.on_event("startup")
async def startup():
    webhook_url = f"{DOMAIN}/webhook"
    async with httpx.AsyncClient() as http:
        # Устанавливаем webhook
        resp = await http.post(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook", 
                              json={"url": webhook_url})
        print(f"Webhook set: {resp.json()}")

@app.get("/")
def root():
    return {"status": "Telegram Post Publisher готов!", "domain": DOMAIN}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

