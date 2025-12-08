from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from tinydb import TinyDB, Query
from datetime import datetime, timedelta
from flask import Flask
import threading
import time
import pandas as pd

# === CONFIG ===
TELEGRAM_TOKEN="7378411294:AAG02Noxl3PCpA9F7-7eLFlmJVEtejd87vo"
ADMIN_ID = 6979709628  # Replace with your Telegram numeric ID
DB_FILE = "tekafayit_db.json"

# === DATABASE ===
db = TinyDB(DB_FILE)
posts = db.table("posts")

# === FLASK WEB SERVER ===
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "🌍 Tekafayit bot is running!"

# === BOT COMMANDS ===

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "👋 እንኳን ወደ Tekafayit በደህና መጡ!\n"
        "Welcome to Tekafayit — Ethiopia’s sharing and exchange bot 🇪🇹\n\n"
        "📋 Commands:\n"
        "/post <City> | <Item> | <OfferType>\n"
        "e.g. /post Addis Ababa | old shoes | Free\n\n"
        "/get — see recent posts\n"
        "/search <City> | <OfferType> — filter posts\n"
        "/cleanup — admin only (remove old posts)\n"
    )
    await update.message.reply_text(msg)

async def post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        text = update.message.text.split(" ", 1)[1]
        parts = [p.strip() for p in text.split("|")]
        if len(parts) < 3:
            await update.message.reply_text("⚠️ Format: /post City | Item | OfferType")
            return

        city, message, offertype = parts
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        user = update.message.from_user.username or update.message.from_user.first_name
        post_id = len(posts) + 1

        posts.insert({
            "ID": post_id,
            "Date": now,
            "City": city,
            "Message": message,
            "Username": user,
            "OfferType": offertype
        })

        await update.message.reply_text("✅ ልጥፍዎ ተቀምጧል! (Post saved successfully!)")

    except IndexError:
        await update.message.reply_text("⚠️ Try again using: /post City | Item | OfferType")

async def get_posts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = posts.all()
    if not data:
        await update.message.reply_text("No posts yet.")
        return

    df = pd.DataFrame(data)
    recent = df.tail(5)
    text = "\n\n".join(
        f"🏙 {row.City}\n📦 {row.Message}\n💬 {row.OfferType}\n👤 @{row.Username}"
        for row in recent.itertuples()
    )
    await update.message.reply_text(f"Here are the latest posts:\n\n{text}")

async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        text = update.message.text.split(" ", 1)[1]
        parts = [p.strip() for p in text.split("|")]
        if len(parts) < 2:
            await update.message.reply_text("⚠️ Format: /search City | OfferType")
            return

        city, offertype = parts
        city = city.lower()
        offertype = offertype.lower()

        data = posts.all()
        results = [
            p for p in data
            if city in p["City"].lower() and offertype in p["OfferType"].lower()
        ]

        if not results:
            await update.message.reply_text("❌ No matching posts found.")
            return

        df = pd.DataFrame(results)
        text = "\n\n".join(
            f"🏙 {row.City}\n📦 {row.Message}\n💬 {row.OfferType}\n👤 @{row.Username}"
            for row in df.itertuples()
        )
        await update.message.reply_text(f"🔍 Results:\n\n{text}")

    except IndexError:
        await update.message.reply_text("⚠️ Try again using: /search City | OfferType")

async def cleanup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Only admin can clean up posts.")
        return
    removed = clean_old_posts()
    await update.message.reply_text(f"🧹 Removed {removed} old posts.")

def clean_old_posts():
    data = posts.all()
    if not data:
        return 0
    cutoff = datetime.now() - timedelta(days=7)
    old = [p for p in data if datetime.strptime(p["Date"], "%Y-%m-%d %H:%M:%S") < cutoff]
    for p in old:
        posts.remove(Query().ID == p["ID"])
    return len(old)

def schedule_cleanup():
    while True:
        clean_old_posts()
        time.sleep(24 * 60 * 60)  # once per day

# === START BOT ===
app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("post", post))
app.add_handler(CommandHandler("get", get_posts))
app.add_handler(CommandHandler("search", search))
app.add_handler(CommandHandler("cleanup", cleanup))

threading.Thread(target=schedule_cleanup, daemon=True).start()
threading.Thread(target=lambda: web_app.run(host="0.0.0.0", port=8080), daemon=True).start()

print("🤖 Tekafayit bot is running...")
app.run_polling()