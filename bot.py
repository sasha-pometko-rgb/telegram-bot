import logging
import asyncio
from datetime import datetime, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ================= НАСТРОЙКИ =================
BOT_TOKEN = "8045149791:AAFExSDQAxWDb4vJ9Hdf4sEU2GW__uSMZSU"
ADMIN_CHAT_ID = 469270967
SPREADSHEET_NAME = "NailSibovatTable"
CHECK_INTERVAL = 60  # для теста 1 мин, потом 3600 (час)
JSON_FILE = r"D:\Telegram bot\telegram-bot-nail-1dcc785cc0df.json"
# =============================================

logging.basicConfig(level=logging.INFO)

# Google Sheets
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name(JSON_FILE, scope)
client = gspread.authorize(creds)
sheet = client.open(SPREADSHEET_NAME).sheet1

# ================= ФУНКЦИИ ==================

def find_user_row(telegram_id):
    records = sheet.get_all_records()
    for i, row in enumerate(records, start=2):
        try:
            if int(float(row["telegram_id"])) == telegram_id:
                return i
        except:
            continue
    return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    row = find_user_row(user.id)

    if not row:
        print(f"Добавляем пользователя: {user.id}, {user.username}")
        sheet.append_row([
            user.id,
            user.first_name,
            f"@{user.username}" if user.username else "",
            "",
            "ожидание",
            "no"
        ])

    await update.message.reply_text(
        "Вы зарегистрированы ✅\n"
        "Мы пришлём напоминание о записи за день до визита."
    )

def build_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Подтвердить", callback_data="confirm")],
        [InlineKeyboardButton("❌ Отменить", callback_data="cancel")],
        [InlineKeyboardButton("🔁 Перенести", callback_data="reschedule")],
    ])

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    telegram_id = query.from_user.id
    row = find_user_row(telegram_id)
    if not row:
        return

    action = query.data
    if action == "confirm":
        sheet.update_cell(row, 5, "подтверждено")
        await query.edit_message_text("Спасибо! Запись подтверждена ✅")
        await context.bot.send_message(
            ADMIN_CHAT_ID,
            f"✅ Клиент {query.from_user.first_name} подтвердил запись"
        )
    elif action in ("cancel", "reschedule"):
        status = "отмена" if action == "cancel" else "перенос"
        sheet.update_cell(row, 5, status)
        await query.edit_message_text(
            "Мы передали информацию администратору.\n"
            "Он свяжется с вами 💬"
        )
        await context.bot.send_message(
            ADMIN_CHAT_ID,
            f"⚠️ Клиент {query.from_user.first_name}: {status}"
        )

async def reminder_job(app):
    while True:
        records = sheet.get_all_records()
        now = datetime.now()
        tomorrow = (now + timedelta(days=1)).date()

        for i, row in enumerate(records, start=2):
            if not row["appointment_datetime"]:
                continue
            if row["reminder_sent"] == "yes":
                continue
            try:
                appt = datetime.strptime(row["appointment_datetime"], "%Y-%m-%d %H:%M")
            except ValueError:
                continue
            if appt.date() == tomorrow and row["status"] == "ожидание":
                try:
                    await app.bot.send_message(
                        chat_id=row["telegram_id"],
                        text=(
                            f"Напоминание о записи 📅\n"
                            f"{appt.strftime('%d.%m.%Y в %H:%M')}\n\n"
                            "Пожалуйста, выберите вариант:"
                        ),
                        reply_markup=build_keyboard()
                    )
                    sheet.update_cell(i, 6, "yes")
                    print(f"Отправлено напоминание: {row['telegram_id']}")
                except Exception as e:
                    print(f"Ошибка при отправке напоминания: {e}")

        await asyncio.sleep(CHECK_INTERVAL)

# ================== ЗАПУСК БОТА ==================
async def on_startup(app):
    asyncio.create_task(reminder_job(app))

if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(on_startup).build()

    # добавляем хэндлеры
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))

    # старт бота (Windows-friendly)
    app.run_polling()
