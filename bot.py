from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, ConversationHandler,
    filters, CallbackContext
)
from tinydb import TinyDB, Query
import logging, datetime, asyncio, os

BOT_TOKEN = os.getenv("7378411294:AAG02Noxl3PCpA9F7-7eLFlmJVEtejd87vo")
ADMIN_ID  = int(os.getenv("ADMIN_ID", "6979709628"))
CHANNEL   = "@TekafayitEthiopia"

db = TinyDB("db.json")
logging.basicConfig(level=logging.INFO)

POST, PHOTO = range(2)

async def start(update: Update, context: CallbackContext):
    await update.message.reply_text(
        "Welcome to Tekafayit!\nUse /post to share an item or /search to find one."
    )

async def post(update: Update, context: CallbackContext):
    keyboard = [
        [InlineKeyboardButton("🆓 Free", callback_data="Free"),
         InlineKeyboardButton("🔁 Exchange", callback_data="Exchange"),
         InlineKeyboardButton("💰 Sell", callback_data="Sell")]
    ]
    await update.message.reply_text("Choose post type:", 
                                    reply_markup=InlineKeyboardMarkup(keyboard))
    return POST

async def handle_type(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    context.user_data["type"] = query.data
    await query.message.reply_text("Send item description:")
    return PHOTO

async def handle_photo(update: Update, context: CallbackContext):
    photos = context.user_data.get("photos", [])
    if update.message.photo:
        photos.append(update.message.photo[-1].file_id)
        context.user_data["photos"] = photos
        if len(photos) < 3:
            await update.message.reply_text(
                f"Photo {len(photos)} saved. Send another or type /done."
            )
            return PHOTO
    await done(update, context)
    return ConversationHandler.END

async def done(update: Update, context: CallbackContext):
    item = {
        "user": update.effective_user.username,
        "type": context.user_data.get("type"),
        "desc": update.message.text or "",
        "photos": context.user_data.get("photos", []),
        "time": str(datetime.datetime.now())
    }
    db.insert(item)
    try:
        media = [InputMediaPhoto(p) for p in item["photos"]]
        if media:
            await context.bot.send_media_group(CHANNEL, media)
        await context.bot.send_message(
            CHANNEL, f"{item['type']} item from @{item['user']}:\n{item['desc']}"
        )
    except Exception as e:
        await context.bot.send_message(ADMIN_ID, f"⚠️ Error posting: {e}")
    await update.message.reply_text("✅ Posted to Tekafayit!")
    return ConversationHandler.END

async def search(update: Update, context: CallbackContext):
    q = " ".join(context.args)
    if not q:
        await update.message.reply_text("Usage: /search <keyword>")
        return
    Post = Query()
    results = db.search(Post.desc.test(lambda s: q.lower() in s.lower()))
    if not results:
        await update.message.reply_text("😕 No items found.")
        return
    for r in results[-5:]:
        await update.message.reply_text(
            f"{r['type']} by @{r['user']}:\n{r['desc']}"
        )

app = ApplicationBuilder().token(BOT_TOKEN).build()
conv = ConversationHandler(
    entry_points=[CommandHandler("post", post)],
    states={
        POST: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_type)],
        PHOTO: [
            MessageHandler(filters.PHOTO, handle_photo),
            CommandHandler("done", done)
        ],
    },
    fallbacks=[CommandHandler("done", done)],
)
app.add_handler(CommandHandler("start", start))
app.add_handler(conv)
app.add_handler(CommandHandler("search", search))

if __name__ == "__main__":
    app.run_polling()
