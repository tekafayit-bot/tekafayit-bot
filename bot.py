from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    ContextTypes
)
from tinydb import TinyDB, Query
from datetime import datetime, timedelta
from flask import Flask
import threading, time, pandas as pd

# === CONFIG ===
TOKEN = "7378411294:AAG02Noxl3PCpA9F7-7eLFlmJVEtejd87vo"
CHANNEL = "@TekafayitEthiopia"
ADMIN_ID = 6979709628        # replace with your numeric Telegram ID
DB_FILE = "tekafayit.json"

# === DATABASE ===
db = TinyDB(DB_FILE)
posts = db.table("posts")

# === WEB APP PLACEHOLDER (for Step 3 dashboard) ===
web_app = Flask(__name__)

@web_app.route("/")
def home():
    return "🌍 Tekafayit bot core running..."

# === UTILITIES ===
def clean_old_posts():
    cutoff = datetime.now() - timedelta(days=7)
    old = [p for p in posts if datetime.strptime(p["Date"], "%Y-%m-%d %H:%M:%S") < cutoff]
    for p in old:
        posts.remove(Query().ID == p["ID"])
    return len(old)

def schedule_cleanup():
    while True:
        clean_old_posts()
        time.sleep(24 * 60 * 60)  # daily

# === BOT COMMANDS ===
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = (
        "👋 እንኳን ወደ *Tekafayit* በደህና መጡ!\n"
        "Share | Exchange | Sell low-cost items 🇪🇹\n\n"
        "Commands:\n"
        "/post City | Item | OfferType | Category\n"
        "/search keyword | city\n"
        "/myposts — your own posts\n"
        "/browse — buttons for city & offer type\n"
        "/cleanup — admin only\n"
    )
    await update.message.reply_markdown(msg)

async def post(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        text = update.message.text.split(" ", 1)[1]
        parts = [p.strip() for p in text.split("|")]
        if len(parts) < 4:
            await update.message.reply_text("⚠️ Format: /post City | Item | OfferType | Category")
            return
        city, item, offer, cat = parts
        user = update.message.from_user
        name = user.username or user.first_name
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        pid = len(posts) + 1
        post_data = {
            "ID": pid, "Date": now, "City": city, "Item": item,
            "Offer": offer, "Category": cat, "User": name,
            "UserID": user.id
        }
        posts.insert(post_data)

        msg = (
            f"🏙 {city}\n📦 {item}\n💬 {offer}\n🏷 {cat}\n👤 @{name}"
        )
        await update.message.reply_text("✅ ልጥፍዎ ተቀምጧል!")
        await ctx.bot.send_message(chat_id=CHANNEL, text=msg)

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def myposts(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    mine = [p for p in posts if p["UserID"] == user_id]
    if not mine:
        await update.message.reply_text("😕 No posts found.")
        return
    text = "\n\n".join(
        f"#{p['ID']} 🏙 {p['City']} | {p['Item']} | {p['Offer']} | {p['Category']}"
        for p in mine[-5:]
    )
    await update.message.reply_text(f"Your latest posts:\n\n{text}")

async def delete(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        pid = int(update.message.text.split(" ", 1)[1])
    except:
        await update.message.reply_text("⚠️ Use: /delete ID")
        return
    user = update.message.from_user
    p = posts.get(Query().ID == pid)
    if not p:
        await update.message.reply_text("❌ Post not found.")
    elif p["UserID"] != user.id and user.id != ADMIN_ID:
        await update.message.reply_text("🚫 You can delete only your own posts.")
    else:
        posts.remove(Query().ID == pid)
        await update.message.reply_text("🗑️ Deleted.")

async def update_post(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        text = update.message.text.split(" ", 1)[1]
        pid, new_item = [t.strip() for t in text.split("|", 1)]
        pid = int(pid)
    except:
        await update.message.reply_text("⚠️ Format: /update ID | New item text")
        return
    user = update.message.from_user
    p = posts.get(Query().ID == pid)
    if not p:
        await update.message.reply_text("❌ Post not found.")
    elif p["UserID"] != user.id and user.id != ADMIN_ID:
        await update.message.reply_text("🚫 You can update only your own posts.")
    else:
        posts.update({"Item": new_item}, Query().ID == pid)
        await update.message.reply_text("✅ Updated!")

async def search(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        text = update.message.text.split(" ", 1)[1]
        key, city = [t.strip().lower() for t in text.split("|")]
    except:
        await update.message.reply_text("⚠️ Format: /search keyword | city")
        return
    res = [
        p for p in posts
        if key in p["Item"].lower() and city in p["City"].lower()
    ]
    if not res:
        await update.message.reply_text(f"😕 No items found for '{key}' in {city.title()}.")
        return
    text = "\n\n".join(
        f"🏙 {p['City']} | {p['Item']} | {p['Offer']} | {p['Category']} | 👤 @{p['User']}"
        for p in res[-5:]
    )
    await update.message.reply_text(f"🔍 Results:\n\n{text}")

# === BROWSE with BUTTONS ===
cities = ["Addis Ababa", "Hawassa", "Adama", "Dire Dawa"]
offers = ["Free", "Exchange", "Sell"]

async def browse(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    buttons = [[InlineKeyboardButton(c, callback_data=f"city:{c}")] for c in cities]
    await update.message.reply_text("🏙 Choose a city:", reply_markup=InlineKeyboardMarkup(buttons))

async def handle_buttons(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith("city:"):
        city = data.split(":", 1)[1]
        btns = [[InlineKeyboardButton(o, callback_data=f"offer:{city}:{o}")] for o in offers]
        await query.edit_message_text(f"Select offer type for {city}:", reply_markup=InlineKeyboardMarkup(btns))
    elif data.startswith("offer:"):
        _, city, offer = data.split(":")
        res = [p for p in posts if p["City"] == city and p["Offer"].lower() == offer.lower()]
        if not res:
            await query.edit_message_text(f"No {offer} posts in {city}.")
            return
        text = "\n\n".join(
            f"📦 {p['Item']} | {p['Offer']} | 👤 @{p['User']}"
            for p in res[-5:]
        )
        await query.edit_message_text(f"{offer} items in {city}:\n\n{text}")

async def cleanup(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        await update.message.reply_text("🚫 Admin only.")
        return
    n = clean_old_posts()
    await update.message.reply_text(f"🧹 Removed {n} old posts.")

# === START BOT ===
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("post", post))
app.add_handler(CommandHandler("myposts", myposts))
app.add_handler(CommandHandler("delete", delete))
app.add_handler(CommandHandler("update", update_post))
app.add_handler(CommandHandler("search", search))
app.add_handler(CommandHandler("browse", browse))
app.add_handler(CallbackQueryHandler(handle_buttons))
app.add_handler(CommandHandler("cleanup", cleanup))

threading.Thread(target=schedule_cleanup, daemon=True).start()
threading.Thread(target=lambda: web_app.run(host="0.0.0.0", port=8080), daemon=True).start()

print("🤖 Tekafayit core running...")
app.run_polling()
