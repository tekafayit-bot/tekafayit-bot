"""
bot.py — Harar Ethiopost NID Registration Bot
Admin: @gech_2721  |  Bot: @HararEthiopostNIDreport_bot
"""

import os, logging
from datetime import date, datetime
from dotenv import load_dotenv
load_dotenv()

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)
import database as db
from excel_report import generate_daily_excel, generate_weekly_excel, generate_monthly_excel

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ── states ────────────────────────────────────────────────────────────────────
(
    S_ADD_NAME, S_ADD_KIT,
    S_EDIT_VALUE,
    S_REG, S_UPLOADED,
    S_ASSIGN_KIT,
    S_FWD_GROUP,
    S_ASSIGN_PENDING_KIT,   # new: kit entry for a pending user
    S_ASSIGN_PENDING_NAME,  # new: officer name for a pending user
) = range(9)

# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def today_str(): return date.today().isoformat()

def report_html(date_iso: str) -> str:
    officers = db.get_all_officers()
    rpts     = db.get_reports_for_date(date_iso)
    d        = datetime.strptime(date_iso, "%Y-%m-%d")
    dfmt     = d.strftime("%-d/%-m/%Y")

    lines = [
        "📊 <b>STATION 2 — Harar Post Office</b>",
        f"📅 <b>Date: {dfmt}</b>",
        "",
        "<pre>",
        f"{'No':<4}{'Name':<11}{'KIT':<10}{'Reg':<6}{'Up'}",
        "─" * 42,
    ]
    tr = tu = 0; n = 1
    for o in officers:
        for kit in o["kits"]:
            e   = rpts.get(kit, {})
            reg = e.get("reg", 0); upl = e.get("uploaded", 0)
            tr += reg; tu += upl
            lines.append(f"{n:<4}{o['name']:<11}{kit:<10}{reg:<6}{upl}")
            n += 1
    lines += ["─" * 42, f"{'':4}{'🔢 TOTAL':<21}{tr:<6}{tu}", "</pre>"]
    return "\n".join(lines)

def report_plain(date_iso: str) -> str:
    officers = db.get_all_officers()
    rpts     = db.get_reports_for_date(date_iso)
    d        = datetime.strptime(date_iso, "%Y-%m-%d")
    dfmt     = d.strftime("%-d/%-m/%Y")

    lines = [
        f"📊  STATION 2 (Harar Post office) and Station 16 (Kersa)",
        f"                              Date {dfmt}",
        f"{'No':<4}{'Name':<11}{'KIT':<10}{'Reg':<6}Uploaded",
        "─" * 44,
    ]
    tr = tu = 0; n = 1
    for o in officers:
        for kit in o["kits"]:
            e   = rpts.get(kit, {})
            reg = e.get("reg", 0); upl = e.get("uploaded", 0)
            tr += reg; tu += upl
            lines.append(f"{n:<4}{o['name']:<11}{kit:<10}{reg:<6}{upl}")
            n += 1
    lines += ["─" * 44, f"     🔢   TOTAL{'':12}{tr:<6}{tu}"]
    return "\n".join(lines)

# ══════════════════════════════════════════════════════════════════════════════
# KEYBOARDS
# ══════════════════════════════════════════════════════════════════════════════

def kb_main(adm: bool, is_officer: bool) -> InlineKeyboardMarkup:
    kb = [[InlineKeyboardButton("📋 Today's Report", callback_data="view_today")],
          [InlineKeyboardButton("📊 Download Reports (Excel)", callback_data="menu_excel")]]
    if is_officer or adm:
        kb.append([InlineKeyboardButton("✏️ Enter My Data", callback_data="enter_data")])
    if adm:
        pending_count = len(db.get_pending_users())
        pending_label = f"🆕 New Users ({pending_count})" if pending_count else "🆕 New Users"
        kb += [
            [InlineKeyboardButton("👮 Manage Officers",  callback_data="manage_officers"),
             InlineKeyboardButton("📤 Forward Report",   callback_data="forward_menu")],
            [InlineKeyboardButton("➕ Add Officer",      callback_data="add_officer"),
             InlineKeyboardButton("🔗 Assign Extra KIT", callback_data="assign_kit_menu")],
            [InlineKeyboardButton(pending_label,          callback_data="pending_users")],
        ]
    return InlineKeyboardMarkup(kb)

def kb_excel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 Daily Excel",   callback_data="excel_daily")],
        [InlineKeyboardButton("📆 Weekly Excel",  callback_data="excel_weekly")],
        [InlineKeyboardButton("🗓 Monthly Excel", callback_data="excel_monthly")],
        [InlineKeyboardButton("🔙 Back",          callback_data="back_main")],
    ])

def kb_officers(officers) -> InlineKeyboardMarkup:
    kb = []
    for i, o in enumerate(officers):
        icon = "✅" if o["chat_id"] else "⭕"
        kb.append([InlineKeyboardButton(
            f"{icon} {o['name']} — {', '.join(o['kits'])}",
            callback_data=f"off_{i}"
        )])
    kb.append([InlineKeyboardButton("🔙 Back", callback_data="back_main")])
    return InlineKeyboardMarkup(kb)

def kb_officer_edit(idx: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Edit Name",      callback_data=f"oe_name_{idx}")],
        [InlineKeyboardButton("✏️ Edit KIT(s)",    callback_data=f"oe_kit_{idx}")],
        [InlineKeyboardButton("🗑 Delete Officer",  callback_data=f"oe_del_{idx}")],
        [InlineKeyboardButton("🔙 Back",            callback_data="manage_officers")],
    ])

def kb_forward() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Forward Today Now",  callback_data="fwd_now")],
        [InlineKeyboardButton("➕ Add Group ID",       callback_data="fwd_add")],
        [InlineKeyboardButton("📋 List Groups",        callback_data="fwd_list")],
        [InlineKeyboardButton("🔙 Back",               callback_data="back_main")],
    ])

def kb_pending(pending) -> InlineKeyboardMarkup:
    kb = []
    for i, u in enumerate(pending):
        uname = f"@{u['username']}" if u['username'] else "no username"
        kb.append([InlineKeyboardButton(
            f"👤 {u['first_name']} ({uname})",
            callback_data=f"pu_{i}"
        )])
    kb.append([InlineKeyboardButton("🔙 Back", callback_data="back_main")])
    return InlineKeyboardMarkup(kb)

def kb_pending_action(idx: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🆕 Create as New Officer", callback_data=f"pu_new_{idx}")],
        [InlineKeyboardButton("🔗 Link to Existing Officer", callback_data=f"pu_link_{idx}")],
        [InlineKeyboardButton("🗑 Dismiss",                callback_data=f"pu_dismiss_{idx}")],
        [InlineKeyboardButton("🔙 Back",                   callback_data="pending_users")],
    ])

def kb_officers_link(officers, pending_idx: int) -> InlineKeyboardMarkup:
    kb = []
    for i, o in enumerate(officers):
        kb.append([InlineKeyboardButton(
            f"{o['name']} — {', '.join(o['kits'])}",
            callback_data=f"pu_link_off_{pending_idx}_{i}"
        )])
    kb.append([InlineKeyboardButton("🔙 Back", callback_data=f"pu_{pending_idx}")])
    return InlineKeyboardMarkup(kb)

def back_btn(dest="back_main"):
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data=dest)]])

# ══════════════════════════════════════════════════════════════════════════════
# /start  — capture EVERY user's chat_id + username immediately
# ══════════════════════════════════════════════════════════════════════════════

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user   = update.effective_user
    uname  = (user.username or "").lower()
    adm    = db.is_admin(uname, user.id)

    # ── always capture admin chat_id ──
    if adm:
        db.add_admin_chat_id(user.id)

    # ── check if already a known officer ──
    officer = db.get_officer_by_chat_id(user.id)

    # ── try matching by username (fallback for pre-existing officers) ──
    if not officer and uname:
        all_off = db.get_all_officers()
        for o in all_off:
            if (o.get("username") or "").lower() == uname or o["name"].lower() == uname:
                db.capture_officer_chat_id(o["name"], user.id, user.username)
                officer = db.get_officer_by_chat_id(user.id)
                break

    # ── unknown user → save to pending so admin can assign them ──
    if not officer and not adm:
        db.upsert_pending_user(user.id, user.username or "", user.first_name)
        # notify admins
        s = db.get_settings()
        note = (
            f"🆕 <b>New user started the bot</b>\n"
            f"Name: <b>{user.first_name}</b>\n"
            f"Username: @{user.username or 'none'}\n"
            f"Chat ID: <code>{user.id}</code>\n\n"
            f"Go to <b>🆕 New Users</b> in the admin panel to assign a KIT."
        )
        for admin_id in s.get("admin_chat_ids", []):
            try:
                await ctx.bot.send_message(chat_id=admin_id, text=note, parse_mode="HTML")
            except Exception:
                pass

    if adm:
        role = "🔑 <b>Admin</b>"
    elif officer:
        role = f"👮 <b>Officer: {officer['name']}</b> | KIT: {', '.join(officer['kits'])}"
    else:
        role = (
            "👁 <b>Viewer</b> — you are not yet assigned to a KIT.\n"
            "The admin has been notified and will assign you shortly."
        )

    await update.message.reply_html(
        f"👋 Welcome, <b>{user.first_name}</b>!\n{role}\n\nChoose an option:",
        reply_markup=kb_main(adm, officer is not None)
    )

# ══════════════════════════════════════════════════════════════════════════════
# CALLBACKS
# ══════════════════════════════════════════════════════════════════════════════

async def on_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q    = update.callback_query
    await q.answer()
    data = q.data
    user = q.from_user
    uname= (user.username or "").lower()
    adm  = db.is_admin(uname, user.id)
    off  = db.get_officer_by_chat_id(user.id)

    # ── back ──
    if data == "back_main":
        await q.edit_message_text("Choose an option:", reply_markup=kb_main(adm, off is not None))

    # ── today report ──
    elif data == "view_today":
        await q.edit_message_text(
            report_html(today_str()), parse_mode="HTML",
            reply_markup=back_btn()
        )

    # ── excel menu ──
    elif data == "menu_excel":
        await q.edit_message_text(
            "📊 <b>Download Reports</b>\nChoose period:",
            parse_mode="HTML", reply_markup=kb_excel()
        )

    # ── excel generate ──
    elif data in ("excel_daily", "excel_weekly", "excel_monthly"):
        await q.edit_message_text("⏳ Generating Excel… please wait.")
        try:
            if data == "excel_daily":
                path    = generate_daily_excel(today_str())
                caption = f"📅 Daily Report — {today_str()}"
            elif data == "excel_weekly":
                path    = generate_weekly_excel()
                caption = "📆 Weekly Report"
            else:
                path    = generate_monthly_excel()
                caption = "🗓 Monthly Report"
            with open(path, "rb") as f:
                await q.message.reply_document(document=f, filename=os.path.basename(path), caption=caption)
        except Exception as e:
            await q.message.reply_text(f"❌ Error: {e}")
        await q.message.reply_text("Choose an option:", reply_markup=kb_main(adm, off is not None))

    # ── enter data ──
    elif data == "enter_data":
        officer = db.get_officer_by_chat_id(user.id) if not adm else None
        if not officer and not adm:
            await q.edit_message_text("❌ You are not registered yet.\nAsk @gech_2721 to assign you a KIT.")
            return
        if adm and not officer:
            # Show all officers so admin can pick whose kit to enter data for
            officers = db.get_all_officers()
            kb = [
                [InlineKeyboardButton(
                    f"{o['name']} — {', '.join(o['kits'])}",
                    callback_data=f"admin_enter_{i}"
                )]
                for i, o in enumerate(officers)
            ]
            kb.append([InlineKeyboardButton("🔙 Back", callback_data="back_main")])
            await q.edit_message_text(
                "👮 <b>Enter data as admin</b>\nSelect an officer:",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(kb)
            )
            return
        if len(officer["kits"]) > 1:
            kb = [[InlineKeyboardButton(k, callback_data=f"kit_{k}")] for k in officer["kits"]]
            await q.edit_message_text("Select your KIT for today:", reply_markup=InlineKeyboardMarkup(kb))
        else:
            ctx.user_data["kit"] = officer["kits"][0]
            ctx.user_data["officer_name"] = officer["name"]
            await q.edit_message_text(
                f"📝 <b>{officer['name']}</b> — KIT <code>{officer['kits'][0]}</code>\n\nEnter <b>REG</b> count:",
                parse_mode="HTML"
            )
            return S_REG

    elif data.startswith("admin_enter_"):
        if not adm: return
        idx = int(data[12:])
        officers = db.get_all_officers()
        o = officers[idx]
        ctx.user_data["officer_name"] = o["name"]
        if len(o["kits"]) > 1:
            kb = [[InlineKeyboardButton(k, callback_data=f"admin_kit_{k}")] for k in o["kits"]]
            kb.append([InlineKeyboardButton("🔙 Back", callback_data="enter_data")])
            await q.edit_message_text(
                f"👮 <b>{o['name']}</b> — select KIT:",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(kb)
            )
        else:
            ctx.user_data["kit"] = o["kits"][0]
            await q.edit_message_text(
                f"📝 <b>{o['name']}</b> — KIT <code>{o['kits'][0]}</code>\n\nEnter <b>REG</b> count:",
                parse_mode="HTML"
            )
            return S_REG

    elif data.startswith("admin_kit_"):
        if not adm: return
        kit = data[10:]
        ctx.user_data["kit"] = kit
        name = ctx.user_data.get("officer_name", "?")
        await q.edit_message_text(
            f"📝 <b>{name}</b> — KIT <code>{kit}</code>\n\nEnter <b>REG</b> count:",
            parse_mode="HTML"
        )
        return S_REG

    elif data.startswith("kit_"):
        kit = data[4:]
        ctx.user_data["kit"] = kit
        await q.edit_message_text(f"📝 KIT <code>{kit}</code>\n\nEnter <b>REG</b> count:", parse_mode="HTML")
        return S_REG

    # ── manage officers ──
    elif data == "manage_officers":
        if not adm: return
        officers = db.get_all_officers()
        await q.edit_message_text(
            "👮 <b>Officers</b> (✅=registered ⭕=pending):",
            parse_mode="HTML", reply_markup=kb_officers(officers)
        )

    elif data.startswith("off_"):
        if not adm: return
        idx = int(data[4:])
        officers = db.get_all_officers()
        o = officers[idx]
        uname_display = f"@{o['username']}" if o.get("username") else "—"
        await q.edit_message_text(
            f"👤 <b>{o['name']}</b>\n"
            f"KIT(s): {', '.join(o['kits'])}\n"
            f"Username: {uname_display}\n"
            f"Chat ID: <code>{o['chat_id'] or 'Not captured yet'}</code>",
            parse_mode="HTML", reply_markup=kb_officer_edit(idx)
        )

    elif data.startswith("oe_name_"):
        if not adm: return
        idx = int(data[8:])
        officers = db.get_all_officers()
        ctx.user_data["edit_officer"] = officers[idx]["name"]
        ctx.user_data["edit_field"]   = "name"
        await q.edit_message_text(f"✏️ Enter new name for <b>{officers[idx]['name']}</b>:", parse_mode="HTML")
        return S_EDIT_VALUE

    elif data.startswith("oe_kit_"):
        if not adm: return
        idx = int(data[7:])
        officers = db.get_all_officers()
        ctx.user_data["edit_officer"] = officers[idx]["name"]
        ctx.user_data["edit_field"]   = "kit"
        await q.edit_message_text(
            f"✏️ Enter new KIT(s) for <b>{officers[idx]['name']}</b>\n(comma-separated for multiple):",
            parse_mode="HTML"
        )
        return S_EDIT_VALUE

    elif data.startswith("oe_del_"):
        if not adm: return
        idx = int(data[7:])
        officers = db.get_all_officers()
        name = officers[idx]["name"]
        db.delete_officer(name)
        await q.edit_message_text(
            f"🗑 <b>{name}</b> deleted.", parse_mode="HTML",
            reply_markup=kb_officers(db.get_all_officers())
        )

    # ── add officer ──
    elif data == "add_officer":
        if not adm: return
        await q.edit_message_text("➕ Enter new officer's <b>Name</b>:", parse_mode="HTML")
        return S_ADD_NAME

    # ── assign extra kit ──
    elif data == "assign_kit_menu":
        if not adm: return
        officers = db.get_all_officers()
        kb = [[InlineKeyboardButton(o["name"], callback_data=f"asn_{i}")] for i, o in enumerate(officers)]
        kb.append([InlineKeyboardButton("🔙 Cancel", callback_data="back_main")])
        await q.edit_message_text("🔗 Select officer to assign extra KIT:", reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("asn_"):
        if not adm: return
        idx = int(data[4:])
        officers = db.get_all_officers()
        ctx.user_data["asn_officer"] = officers[idx]["name"]
        await q.edit_message_text(
            f"Enter extra KIT number for <b>{officers[idx]['name']}</b>:", parse_mode="HTML"
        )
        return S_ASSIGN_KIT

    # ══════════════════════════════════════════════════════════════════════════
    # PENDING USERS panel
    # ══════════════════════════════════════════════════════════════════════════

    elif data == "pending_users":
        if not adm: return
        pending = db.get_pending_users()
        if not pending:
            await q.edit_message_text(
                "✅ No new unassigned users.",
                reply_markup=back_btn()
            )
            return
        await q.edit_message_text(
            f"🆕 <b>Unassigned Users ({len(pending)})</b>\n"
            "Select a user to assign them a KIT:",
            parse_mode="HTML",
            reply_markup=kb_pending(pending)
        )

    elif data.startswith("pu_") and not any(data.startswith(x) for x in ("pu_new_", "pu_link_", "pu_dismiss_")):
        if not adm: return
        idx = int(data[3:])
        pending = db.get_pending_users()
        if idx >= len(pending):
            await q.edit_message_text("⚠️ User not found.", reply_markup=back_btn("pending_users"))
            return
        u = pending[idx]
        uname_display = f"@{u['username']}" if u['username'] else "no username"
        await q.edit_message_text(
            f"👤 <b>{u['first_name']}</b> ({uname_display})\n"
            f"Chat ID: <code>{u['chat_id']}</code>\n\n"
            "What would you like to do?",
            parse_mode="HTML",
            reply_markup=kb_pending_action(idx)
        )

    # Create as brand new officer
    elif data.startswith("pu_new_"):
        if not adm: return
        idx = int(data[7:])
        pending = db.get_pending_users()
        if idx >= len(pending): return
        ctx.user_data["pending_idx"] = idx
        ctx.user_data["pending_user"] = pending[idx]
        await q.edit_message_text(
            f"Enter the <b>officer name</b> for this user\n"
            f"(their Telegram name: {pending[idx]['first_name']}):",
            parse_mode="HTML"
        )
        return S_ASSIGN_PENDING_NAME

    # Link to an existing officer record
    elif data.startswith("pu_link_") and "_off_" not in data:
        if not adm: return
        idx = int(data[8:])
        officers = db.get_all_officers()
        await q.edit_message_text(
            "Select existing officer to link this user to:",
            reply_markup=kb_officers_link(officers, idx)
        )

    elif data.startswith("pu_link_off_"):
        if not adm: return
        parts = data.split("_")  # pu_link_off_<pidx>_<oidx>
        pidx  = int(parts[3])
        oidx  = int(parts[4])
        pending  = db.get_pending_users()
        officers = db.get_all_officers()
        if pidx >= len(pending) or oidx >= len(officers): return
        u = pending[pidx]
        o = officers[oidx]
        db.capture_officer_chat_id(o["name"], u["chat_id"], u["username"])
        db.delete_pending_user(u["chat_id"])
        # notify the user
        try:
            await ctx.bot.send_message(
                chat_id=u["chat_id"],
                text=(
                    f"✅ You have been assigned as officer <b>{o['name']}</b>\n"
                    f"KIT(s): <code>{', '.join(o['kits'])}</code>\n\n"
                    "Press /start to begin."
                ),
                parse_mode="HTML"
            )
        except Exception:
            pass
        await q.edit_message_text(
            f"✅ <b>{u['first_name']}</b> linked to officer <b>{o['name']}</b>.",
            parse_mode="HTML",
            reply_markup=back_btn("pending_users")
        )

    # Dismiss (ignore) a pending user
    elif data.startswith("pu_dismiss_"):
        if not adm: return
        idx = int(data[11:])
        pending = db.get_pending_users()
        if idx >= len(pending): return
        u = pending[idx]
        db.delete_pending_user(u["chat_id"])
        await q.edit_message_text(
            f"🗑 <b>{u['first_name']}</b> dismissed.",
            parse_mode="HTML",
            reply_markup=back_btn("pending_users")
        )

    # ── forward ──
    elif data == "forward_menu":
        if not adm: return
        await q.edit_message_text("📤 <b>Forward Report</b>", parse_mode="HTML", reply_markup=kb_forward())

    elif data == "fwd_now":
        if not adm: return
        s      = db.get_settings()
        groups = s.get("forward_groups", [])
        if not groups:
            await q.edit_message_text("❌ No groups configured. Add a group ID first.", reply_markup=kb_forward())
            return
        text = report_plain(today_str())
        sent = 0
        for gid in groups:
            try:
                await ctx.bot.send_message(chat_id=gid, text=f"<pre>{text}</pre>", parse_mode="HTML")
                sent += 1
            except Exception as e:
                logger.warning(f"Failed to send to {gid}: {e}")
        await q.edit_message_text(
            f"✅ Report forwarded to {sent}/{len(groups)} group(s).",
            reply_markup=back_btn("forward_menu")
        )

    elif data == "fwd_add":
        if not adm: return
        await q.edit_message_text("Enter Telegram group chat ID\n(e.g. <code>-1001234567890</code>):", parse_mode="HTML")
        return S_FWD_GROUP

    elif data == "fwd_list":
        if not adm: return
        s      = db.get_settings()
        groups = s.get("forward_groups", [])
        if not groups:
            text = "📋 No groups added yet."
        else:
            text = "📋 <b>Forward Groups:</b>\n" + "\n".join(f"• <code>{g}</code>" for g in groups)
        await q.edit_message_text(text, parse_mode="HTML", reply_markup=back_btn("forward_menu"))

# ══════════════════════════════════════════════════════════════════════════════
# MESSAGE HANDLERS (conversation steps)
# ══════════════════════════════════════════════════════════════════════════════

async def recv_reg(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip()
    if not txt.isdigit():
        await update.message.reply_text("❌ Enter a valid number for REG:"); return S_REG
    ctx.user_data["reg"] = int(txt)
    await update.message.reply_text("📤 Now enter <b>UPLOADED</b> count:", parse_mode="HTML")
    return S_UPLOADED

async def recv_uploaded(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip()
    if not txt.isdigit():
        await update.message.reply_text("❌ Enter a valid number for UPLOADED:"); return S_UPLOADED
    user = update.effective_user
    adm  = db.is_admin((user.username or "").lower(), user.id)
    off  = db.get_officer_by_chat_id(user.id)
    kit  = ctx.user_data.get("kit")
    reg  = ctx.user_data.get("reg", 0)
    upl  = int(txt)
    db.save_report(today_str(), kit, reg, upl)
    await update.message.reply_html(
        f"✅ <b>Saved!</b>\nKIT: <code>{kit}</code> | REG: {reg} | Uploaded: {upl}\n\n"
        + report_html(today_str()),
        reply_markup=kb_main(adm, off is not None)
    )
    ctx.user_data.clear()
    return ConversationHandler.END

async def recv_edit_value(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user  = update.effective_user
    adm   = db.is_admin((user.username or "").lower(), user.id)
    off   = db.get_officer_by_chat_id(user.id)
    name  = ctx.user_data.get("edit_officer")
    field = ctx.user_data.get("edit_field")
    val   = update.message.text.strip()
    if field == "name":
        db.update_officer_name(name, val)
        msg = f"✅ Name updated to <b>{val}</b>"
    else:
        kits = [k.strip() for k in val.split(",")]
        db.update_officer_kits(name, kits)
        msg = f"✅ KITs updated to <b>{', '.join(kits)}</b>"
    await update.message.reply_html(msg, reply_markup=kb_officers(db.get_all_officers()))
    ctx.user_data.clear()
    return ConversationHandler.END

async def recv_add_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["new_name"] = update.message.text.strip()
    await update.message.reply_text("Enter KIT number(s) (comma-separated for multiple):")
    return S_ADD_KIT

async def recv_add_kit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    adm  = db.is_admin((user.username or "").lower(), user.id)
    off  = db.get_officer_by_chat_id(user.id)
    name = ctx.user_data.get("new_name", "Unknown")
    kits = [k.strip() for k in update.message.text.split(",")]
    db.add_officer(name, kits)
    await update.message.reply_html(
        f"✅ Officer <b>{name}</b> added with KIT(s): {', '.join(kits)}",
        reply_markup=kb_main(adm, off is not None)
    )
    ctx.user_data.clear()
    return ConversationHandler.END

async def recv_assign_kit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    adm  = db.is_admin((user.username or "").lower(), user.id)
    off  = db.get_officer_by_chat_id(user.id)
    name = ctx.user_data.get("asn_officer")
    kit  = update.message.text.strip()
    db.assign_kit(name, kit)
    await update.message.reply_html(
        f"✅ KIT <code>{kit}</code> assigned to <b>{name}</b>.",
        reply_markup=kb_main(adm, off is not None)
    )
    ctx.user_data.clear()
    return ConversationHandler.END

async def recv_pending_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Admin entered a name for a pending user → now ask for the KIT."""
    ctx.user_data["pending_officer_name"] = update.message.text.strip()
    await update.message.reply_text("Enter KIT number(s) for this officer (comma-separated):")
    return S_ASSIGN_PENDING_KIT

async def recv_pending_kit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Admin entered the KIT → create the officer and notify the user."""
    user = update.effective_user
    adm  = db.is_admin((user.username or "").lower(), user.id)
    off  = db.get_officer_by_chat_id(user.id)

    o_name   = ctx.user_data.get("pending_officer_name", "Unknown")
    kits     = [k.strip() for k in update.message.text.split(",")]
    pu       = ctx.user_data.get("pending_user", {})
    pu_id    = pu.get("chat_id")
    pu_uname = pu.get("username", "")

    db.add_officer(o_name, kits, chat_id=pu_id, username=pu_uname)
    if pu_id:
        db.delete_pending_user(pu_id)
        try:
            await update.get_bot().send_message(
                chat_id=pu_id,
                text=(
                    f"✅ You have been registered as officer <b>{o_name}</b>\n"
                    f"KIT(s): <code>{', '.join(kits)}</code>\n\n"
                    "Press /start to enter your data."
                ),
                parse_mode="HTML"
            )
        except Exception:
            pass

    await update.message.reply_html(
        f"✅ Officer <b>{o_name}</b> created with KIT(s): {', '.join(kits)}",
        reply_markup=kb_main(adm, off is not None)
    )
    ctx.user_data.clear()
    return ConversationHandler.END

async def recv_fwd_group(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    adm  = db.is_admin((user.username or "").lower(), user.id)
    off  = db.get_officer_by_chat_id(user.id)
    try:
        gid = int(update.message.text.strip())
        db.add_forward_group(gid)
        await update.message.reply_html(
            f"✅ Group <code>{gid}</code> added to forward list.",
            reply_markup=kb_main(adm, off is not None)
        )
    except ValueError:
        await update.message.reply_text("❌ Invalid ID. Must be a number like -1001234567890.")
        return S_FWD_GROUP
    ctx.user_data.clear()
    return ConversationHandler.END

async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    adm  = db.is_admin((user.username or "").lower(), user.id)
    off  = db.get_officer_by_chat_id(user.id)
    ctx.user_data.clear()
    await update.message.reply_text("❌ Cancelled.", reply_markup=kb_main(adm, off is not None))
    return ConversationHandler.END

from telegram.ext import ConversationHandler

# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    token = os.environ["BOT_TOKEN"]

    # Init DB
    db.init_officers()

    app = Application.builder().token(token).build()

    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(on_callback)],
        states={
            S_REG:                 [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_reg)],
            S_UPLOADED:            [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_uploaded)],
            S_EDIT_VALUE:          [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_edit_value)],
            S_ADD_NAME:            [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_add_name)],
            S_ADD_KIT:             [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_add_kit)],
            S_ASSIGN_KIT:          [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_assign_kit)],
            S_FWD_GROUP:           [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_fwd_group)],
            S_ASSIGN_PENDING_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_pending_name)],
            S_ASSIGN_PENDING_KIT:  [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_pending_kit)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_user=True, per_chat=True,
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(conv)

    logger.info("🚀 Harar NID Bot is running…")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
