import os
import requests
import speech_recognition as sr
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.request import HTTPXRequest
from gtts import gTTS
from langdetect import detect
from deep_translator import GoogleTranslator
from pydub import AudioSegment

#configurations
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")



SUPPORTED_LANGUAGES = {
    "en": "English", "hi": "Hindi", "mr": "Marathi", "gu": "Gujarati"
}
DEFAULT_LANGUAGE = "en"

#detection and transalation
def normalize_language(lang):
    if lang in ['ur', 'so', 'id', 'fa', 'ps', 'sd', 'ne']:
        return "hi"
    return lang if lang in SUPPORTED_LANGUAGES else "hi"

def detect_language(text):
    try:
        return normalize_language(detect(text))
    except:
        return DEFAULT_LANGUAGE

def translate_to_english(text, source_lang):
    if source_lang == "en":
        return text
    try:
        return GoogleTranslator(source=source_lang, target="en").translate(text)
    except:
        return text

def translate_to_lang(text, target_lang):
    if target_lang == "en":
        return text
    try:
        return GoogleTranslator(source="en", target=target_lang).translate(text)
    except:
        return text

#gpt logic
def get_gpt_reply(user_input):
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "anthropic/claude-3-haiku",
        "messages": [
            {
                "role": "system",
                "content": "You are a friendly health assistant. Respond in simple English with bullet points and emojis. Keep replies short and helpful."
            },
            {
                "role": "user",
                "content": user_input
            }
        ]
    }

    try:
        response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload)
        return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print("OpenRouter API error:", e)
        return "❌ I'm sorry, I couldn't process your message."

#text to voice
def generate_tts(text, lang="en", filename="reply.mp3"):
    lang = lang if lang in SUPPORTED_LANGUAGES else "hi"
    tts = gTTS(text, lang=lang)
    tts.save(filename)
    return filename

#text handler
async def process_input_text(user_text, update: Update):
    lang = detect_language(user_text)
    print("🌐 Detected language:", lang)

    translated_input = translate_to_english(user_text, lang)
    gpt_reply_en = get_gpt_reply(translated_input)
    reply_local = translate_to_lang(gpt_reply_en, lang)

    await update.message.reply_text(reply_local)

    voice_path = generate_tts(reply_local, lang=lang)
    await update.message.reply_voice(voice=open(voice_path, "rb"))
    os.remove(voice_path)

#voice handler
async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    voice = await update.message.voice.get_file()
    voice_path = await voice.download_to_drive()

    #Convert .ogg to .wav
    audio = AudioSegment.from_file(voice_path, format="ogg")
    audio.export("input.wav", format="wav")
    os.remove(voice_path)

    recognizer = sr.Recognizer()
    with sr.AudioFile("input.wav") as source:
        audio_data = recognizer.record(source)
    os.remove("input.wav")

    try:
        text = recognizer.recognize_google(audio_data)
        print("🔊 Transcribed:", text)
        await process_input_text(text, update)
    except sr.UnknownValueError:
        await update.message.reply_text("❌ Sorry, I couldn't understand the voice.")
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error: {e}")

#start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Hello! I'm your multilingual AI Health Bot. Send a message or a voice note!")

#run command bot
request = HTTPXRequest(connect_timeout=30.0, read_timeout=30.0)
app = ApplicationBuilder().token(TELEGRAM_TOKEN).request(request).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, lambda u, c: process_input_text(u.message.text, u)))
app.add_handler(MessageHandler(filters.VOICE, handle_voice))

print("✅ Bot is running...")
app.run_polling()