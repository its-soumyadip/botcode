from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes, ConversationHandler,
    CallbackQueryHandler, MessageHandler, filters
)
import requests
from datetime import datetime
from datetime import datetime, timedelta



import firebase_admin
from firebase_admin import credentials, firestore

# Initialize Firebase app
cred = credentials.Certificate("firebase.json")
firebase_admin.initialize_app(cred)

# Get Firestore client
db = firestore.client()


# API_URL = "http://127.0.0.1:8000/api/orders/"



ADMIN_ID = 5483332703  # Your Telegram ID as int
SUPPORT_ID = "Its_Hungry_cloud"  # Customer support Telegram ID as int

MENU_ITEMS = {
    "Jol Puchka (12 pcs)": 50,
    "Jol Puchka (6 pcs)": 25,
    "Doi Puchka (12 pcs)": 60,
    "Doi Puchka (6 pcs)": 40,
    "Alu Kabli (Full)": 40,
    "Alu Kabli (Half)": 25,
    "Papdi Chaat (Full)": 60,
    "Papdi Chaat (Half)": 40,
    "Chana Masala (Full)": 50,
    "Chana Masala (Half)": 30,
}

CHOOSING_ITEM, ENTER_QUANTITY, ENTER_MOBILE, ENTER_ADDRESS, ORDER_TYPE, ENTER_TIME, ENTER_NOTE, CONFIRM = range(8)

# In-memory store for manual reply
user_sessions = {}

# ------------------------ Utility Handlers ------------------------

async def track_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or str(user_id).lower()
    last_message = ""
    if update.message:
        last_message = update.message.text
    elif update.callback_query:
        last_message = update.callback_query.data
    user_sessions[user_id] = {
        "username": username,
        "last_message": last_message
    }
    db.collection("users").document(str(user_id)).set({
        "username": username,
        "last_message": last_message,
        "updated_at": firestore.SERVER_TIMESTAMP
    }, merge=True)

async def forward_all_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = update.message

    # 1. Send to your inbox (copy the message)
    if message.text:
        text = f"📩 Message from @{user.username or user.id}:\n{message.text}"
        await context.bot.send_message(chat_id=ADMIN_ID, text=text)

        text = update.message.text.lower()
    if text in ["ok", "thanks", "thank you", "hello", "hi"]:
        await send_text(update, "😊 You're welcome! Use /start to place a new order.")
    else:
        await send_text(update, "🤔 I didn't understand. Use /start to place an order or /support for help.")

async def send_text(update: Update, text: str, reply_markup=None):
    """Utility to safely send or edit message text for both message and callback_query updates."""
    if update.message:
        await update.message.reply_text(text, reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.message.edit_text(text, reply_markup=reply_markup)

# def is_order_time(delivery_time=None):
    # now = datetime.now()
    # weekday = now.weekday()  # 0=Mon, 6=Sun
    # current_hour = now.hour
    # if delivery_time:
    #     try:
    #         hours, minutes = map(int, delivery_time.split(":"))
    #         current_hour = hours
    #     except:
    #         return False
    # if weekday < 5:  # Mon-Fri
    #     return 19 <= current_hour <= 23
    # else:  # Sat-Sun
    #     return 16 <= current_hour <= 23
# def is_order_time(delivery_time=None):
#     now = datetime.now()
#     weekday = now.weekday()  # 0 = Monday, 6 = Sunday

#     start_hour = 19 if weekday < 5 else 16
#     end_hour = 23  # You want to allow until 11:00 PM only

#     # Parse the delivery time
#     if delivery_time:
#         try:
#             delivery_dt = datetime.strptime(delivery_time, "%H:%M")
#         except ValueError:
#             return False
#     else:
#         delivery_dt = now

#     # Combine today's date with start and end time
#     today = now.date()
#     start_time = datetime.combine(today, datetime.min.time()) + timedelta(hours=start_hour)
#     end_time = datetime.combine(today, datetime.min.time()) + timedelta(hours=end_hour)

#     return start_time <= delivery_dt <= end_time

def is_order_time(delivery_time=None):
    now = datetime.now()
    weekday = now.weekday()  # 0 = Monday, 6 = Sunday

    start_hour = 19 if weekday < 5 else 16
    end_hour = 23  # until 11 PM

    today = now.date()
    
    start_time = datetime.combine(today, datetime.min.time()) + timedelta(hours=start_hour)
    end_time = datetime.combine(today, datetime.min.time()) + timedelta(hours=end_hour)

    if delivery_time:
        try:
            hours, minutes = map(int, delivery_time.split(":"))
            delivery_dt = datetime.combine(today, datetime.min.time()) + timedelta(hours=hours, minutes=minutes)
        except ValueError:
            return False
    else:
        delivery_dt = now

    return start_time <= delivery_dt <= end_time


# ------------------------ Bot Handlers ------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await track_user(update, context)
    text = "🍽️ Welcome to our food bot!\n\nCommands:\n/start - Show menu\n/support - Contact support\n/cancel - Cancel order (contact support)"
    await send_text(update, text)

    try:
        with open("menu.jpeg", "rb") as menu_img:
            if update.message:
                await update.message.reply_photo(menu_img, caption="📜 Here’s our menu!")
            elif update.callback_query:
                await update.callback_query.message.reply_photo(menu_img, caption="📜 Here’s our menu!")
    except:
        await send_text(update, "📜 Here’s our menu:")

    keyboard = [[InlineKeyboardButton(item, callback_data=item)] for item in MENU_ITEMS.keys()]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await send_text(update, "Select an item to add to your cart:", reply_markup)
    context.user_data['cart'] = []
    return CHOOSING_ITEM

async def choose_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    item = query.data

    if item == "DONE":
        if not context.user_data.get('cart'):
            await query.message.edit_text("⚠️ Your cart is empty! Add at least one item first.")
            return CHOOSING_ITEM
        await query.message.edit_text("📱 Enter your mobile number for delivery:")
        return ENTER_MOBILE

    context.user_data['current_item'] = item
    await query.message.edit_text(f"📦 Enter quantity for {item}:")
    return ENTER_QUANTITY

async def enter_quantity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        quantity = int(update.message.text)
    except ValueError:
        await update.message.reply_text("⚠️ Enter a valid number for quantity.")
        return ENTER_QUANTITY

    item = context.user_data['current_item']
    context.user_data['cart'].append({
        "item_name": item,
        "quantity": quantity,
        "price": MENU_ITEMS[item]
    })

    # Show menu again with DONE button
    keyboard = [[InlineKeyboardButton(it, callback_data=it)] for it in MENU_ITEMS.keys()]
    keyboard.append([InlineKeyboardButton("✅ Done", callback_data="DONE")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("✅ Item added! Select another item or Done:", reply_markup=reply_markup)
    return CHOOSING_ITEM

async def enter_mobile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.text
    if not contact.isdigit() or len(contact) < 10:
        await send_text(update, "⚠️ Enter a valid mobile number.")
        return ENTER_MOBILE
    context.user_data['mobile'] = contact
    await send_text(update, "🏠 Enter your delivery address:")
    return ENTER_ADDRESS

async def enter_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['address'] = update.message.text

    keyboard = [
        [InlineKeyboardButton("🚀 Place Now", callback_data="NOW")],
        [InlineKeyboardButton("📅 Schedule Delivery", callback_data="SCHEDULE")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await send_text(update, "Place order now or schedule delivery?", reply_markup)
    return ORDER_TYPE

# async def order_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     query = update.callback_query
#     await query.answer()
#     if query.data == "NOW":
#         context.user_data['delivery_time'] = datetime.now().strftime("%H:%M")
#         if not is_order_time():
#             await send_text(update, "⚠️ Orders can only be placed between 7-11 PM on weekdays and 4-11 PM on weekends.")
#             return ConversationHandler.END
#         await query.message.edit_text("Optional: Add a note for your order (like spice level) or type 'skip':")
#         return ENTER_NOTE
#     else:
#         await query.message.edit_text("🕒 Enter delivery time (HH:MM):")
#         return ENTER_TIME
from datetime import datetime, timedelta

async def order_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "NOW":
        now_time = datetime.now().strftime("%H:%M")
        context.user_data['delivery_time'] = now_time
        context.user_data['delivery_time_display'] = datetime.now().strftime("%I:%M %p").lstrip("0")

        if not is_order_time(now_time):  # ✅ Pass current full time
            await send_text(update, "⚠️ Orders can only be placed between 7–11 PM on weekdays and 4–11 PM on weekends.")
            return ConversationHandler.END

        await query.message.edit_text("Optional: Add a note for your order (like spice level) or type 'skip':")
        return ENTER_NOTE

    now = datetime.now()
    weekday = now.weekday()
    today = now.date()

    start_hour = 19 if weekday < 5 else 16
    end_hour = 23
    from datetime import timedelta
    # Correctly limit to 11:00 PM
    start_time = datetime.combine(today, datetime.min.time()) + timedelta(hours=start_hour)
    end_time = datetime.combine(today, datetime.min.time()) + timedelta(hours=end_hour, minutes=0)

    # Round current time to next 15-min slot
    from datetime import timedelta

    minutes = (now.minute // 15 + 1) * 15
    if minutes >= 60:
        start_slot = now + timedelta(hours=1)
        start_slot = start_slot.replace(minute=0, second=0, microsecond=0)
    else:
        start_slot = now.replace(minute=minutes, second=0, microsecond=0)

    slot = max(start_slot, start_time)

    available_slots = []
    while slot <= end_time:
        label = slot.strftime("%I:%M %p").lstrip("0")
        value = slot.strftime("%H:%M")
        available_slots.append((label, value))
        slot += timedelta(minutes=15)

    if not available_slots:
        await query.message.edit_text("⚠️ No delivery slots available at this time for today, Orders can only be scheduled for 7–11 PM on weekdays and 4–11 PM on weekends .")
        return ConversationHandler.END

    keyboard = []
    for i in range(0, len(available_slots), 3):
        row = [InlineKeyboardButton(label, callback_data=f"TIME_{value}") for label, value in available_slots[i:i+3]]
        keyboard.append(row)

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text("🕒 Select your delivery time:", reply_markup=reply_markup)
    return ENTER_TIME


    
# Enter time for scheduled order
# async def enter_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        hours, minutes = map(int, update.message.text.split(":"))
        delivery_time = f"{hours:02d}:{minutes:02d}"
        if not is_order_time(delivery_time):
            await send_text(update, "⚠️ Delivery time must be within allowed hours (weekdays 7-11 PM, weekends 4-11 PM).")
            return ENTER_TIME
        context.user_data['delivery_time'] = delivery_time
    except:
        await send_text(update, "⚠️ Invalid time format! Use HH:MM")
        return ENTER_TIME
    await send_text(update, "Optional: Add a note for your order (like spice level) or type 'skip':")
    return ENTER_NOTE

async def enter_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data.startswith("TIME_"):
        selected_time = query.data.replace("TIME_", "")  # e.g., "20:15"

        if not is_order_time(selected_time):
            await query.message.edit_text("⚠️ Invalid delivery time. Please choose within valid hours.")
            return ConversationHandler.END

        # Store delivery time (machine format)
        context.user_data['delivery_time'] = selected_time

        # Store human-readable display time
        try:
            dt_obj = datetime.strptime(selected_time, "%H:%M")
            display_time = dt_obj.strftime("%-I:%M %p")  # Use "%I:%M %p" on Windows
        except:
            display_time = selected_time

        context.user_data['delivery_time_display'] = display_time

        await query.message.edit_text("Optional: Add a note for your order (like spice level) or type 'skip':")
        return ENTER_NOTE


async def enter_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    note = update.message.text
    if note.lower() != "skip":
        context.user_data['note'] = note
    else:
        context.user_data['note'] = ""
    await show_summary(update, context)
    return CONFIRM

async def show_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total_price = sum(i['quantity'] * i['price'] for i in context.user_data['cart'])
    if total_price < 41:
        total_price += 10
        context.user_data['delivery_charge'] = 10
    else:
        context.user_data['delivery_charge'] = 0
    context.user_data['total_price'] = total_price

    order_summary = "\n".join([f"{i['item_name']} x {i['quantity']} (₹{i['price']})" for i in context.user_data['cart']])
    if context.user_data['delivery_charge'] > 0:
        order_summary += f"\n🚚 Delivery charge: ₹{context.user_data['delivery_charge']}"

    text = f"🧾 Order Summary:\n{order_summary}\n🕒 Delivery Time: {context.user_data['delivery_time']}\n📝 Note: {context.user_data.get('note', '')}\n💰 Total: ₹{total_price}\nConfirm order? (yes/no)"
    await send_text(update, text)


async def confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.lower() != "yes":
        await send_text(update, "❌ Order canceled. For cancellation, contact /support.")
        return ConversationHandler.END

    order_data = {
    "telegram_user_id": str(update.effective_user.id),
    "username": update.effective_user.username or str(update.effective_user.id),
    "mobile": context.user_data['mobile'],
    "address": context.user_data['address'],
    "total_price": context.user_data['total_price'],
    "items": context.user_data['cart'],
    "delivery_time": context.user_data['delivery_time'],  # e.g., "20:15"
    "delivery_time_display": context.user_data['delivery_time_display'],  # e.g., "8:15 PM"
    "note": context.user_data.get('note', ""),
    "timestamp": firestore.SERVER_TIMESTAMP
    }

    try:
        # Add document to Firestore under "orders" collection
        db.collection("orders").add(order_data)

        await send_text(update, "✅ Order placed successfully! 🎉")

        # Prepare admin summary
        order_summary = "\n".join([
            f"{i['item_name']} x {i['quantity']} (₹{i['price']})"
            for i in context.user_data['cart']
        ])
        if context.user_data['delivery_charge'] > 0:
            order_summary += f"\n🚚 Delivery charge: ₹{context.user_data['delivery_charge']}"

        admin_msg = (
            f"🛎 New Order from @{update.effective_user.username}:\n"
            f"📱 {context.user_data['mobile']}\n"
            f"🏠 {context.user_data['address']}\n"
            f"🕒 Delivery Time: {context.user_data['delivery_time_display']}\n"
            f"📝 Note: {context.user_data.get('note', 'None')}\n\n"
            f"{order_summary}\n"
            f"💰 Total: ₹{context.user_data['total_price']}"
        )


        await context.bot.send_message(chat_id=ADMIN_ID, text=admin_msg)

    except Exception as e:
        await send_text(update, f"⚠️ Failed to save order: {e}")

    return ConversationHandler.END



async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_text(update, "❌ To cancel an order, please contact /support.")
    return ConversationHandler.END

async def support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    support_text = (
        f"📞 *Need Help?*\n\n"
        f"• Contact on Telegram: @{SUPPORT_ID}\n"
        f"• 📱 Call us: +91 9749001501\n\n"
        f"Use /start to place a new order anytime 🍽️"
    )
    await send_text(update, support_text, reply_markup=None)


async def auto_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()
    if text in ["ok", "thanks", "thank you", "hello", "hi"]:
        await send_text(update, "😊 You're welcome! Use /start to place a new order.")
    else:
        await send_text(update, "🤔 I didn't understand. Use /start to place an order or /support for help.")

async def manual_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ You are not authorized to use this command.")
        return

    try:
        args = context.args
        if len(args) < 2:
            await update.message.reply_text("⚠️ Usage: /reply <user_id|username> <message>")
            return
        
        target = args[0]
        reply_message = " ".join(args[1:])

        # Check if target is username
        if target.startswith("@"):
            target = target[1:]
        
        # Try numeric first
        try:
            target_user_id = int(target)
        except ValueError:
            # Lookup by username in user_sessions
            found = False
            target_user_id = None
            for uid, info in user_sessions.items():
                if info["username"] == target:
                    target_user_id = uid
                    found = True
                    break
            if not target_user_id:
                users = db.collection("users").where("username", "==", target).stream()
                for user_doc in users:
                    target_user_id = int(user_doc.id)
                    found = True
                    break
            if not found:
                await update.message.reply_text(f"❌ User @{target} not found in sessions.")
                return

        await context.bot.send_message(chat_id=target_user_id, text=f"💬 Support: {reply_message}")
        await update.message.reply_text("✅ Message sent successfully!")

    except Exception as e:
        await update.message.reply_text(f"⚠️ Error: {e}")


# ------------------------ Application Setup ------------------------

app = ApplicationBuilder().token("7557939515:AAE-ZoHEK1cQr6dvC2pRUYhaMQtIUkvEie4").build()

conv_handler = ConversationHandler(
    entry_points=[CommandHandler('start', start)],
    states={
        CHOOSING_ITEM: [CallbackQueryHandler(choose_item)],
        ENTER_QUANTITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_quantity)],
        ENTER_MOBILE: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_mobile)],
        ENTER_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_address)],
        ORDER_TYPE: [CallbackQueryHandler(order_type)],
        # ENTER_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_time)],
        ENTER_TIME: [CallbackQueryHandler(enter_time)],
        ENTER_NOTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_note)],
        CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm)],
    },
    fallbacks=[CommandHandler('cancel', cancel)]
)

app.add_handler(conv_handler)
app.add_handler(CommandHandler('support', support))
app.add_handler(CommandHandler('reply', manual_reply))
# app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, auto_reply))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, forward_all_messages))

app.run_polling()
