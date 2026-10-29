
import os
import sqlite3
import logging
import html

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, ReplyKeyboardRemove
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ConversationHandler,
    ContextTypes, filters
)

TOKEN = os.environ["BOT_TOKEN"]
GROUP_ID = int(os.environ["GROUP_ID"])
DB_PATH = os.environ.get("DB_PATH", "submissions.db")

DEPARTMENT, NAME, DEDICATION, CONFIRM = range(4)

DEPARTMENTS = [
    "هندسة معمارية 24 🏛️",
    "هندسة مدنية 🏗️",
    "هندسة معمارية 25 🏠"
]

logging.basicConfig(level=logging.INFO)


# إنشاء قاعدة بيانات لحفظ تسجيلات الطلاب
def init_db():
    with sqlite3.connect(DB_PATH) as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS submissions (
                user_id INTEGER PRIMARY KEY,
                department TEXT NOT NULL,
                name TEXT NOT NULL,
                dedication TEXT NOT NULL,
                status TEXT NOT NULL
            )
        """)


def has_submitted(user_id):
    with sqlite3.connect(DB_PATH) as db:
        row = db.execute(
            "SELECT status FROM submissions WHERE user_id = ?",
            (user_id,)
        ).fetchone()
    return row is not None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if has_submitted(user_id):
        await update.message.reply_text(
            "عذراً، لقد سبق لك إرسال إهدائك.\n"
            "يسمح لكل طالب بإرسال إهداء واحد فقط. 🌷"
        )
        return ConversationHandler.END

    context.user_data.clear()

    keyboard = [[d] for d in DEPARTMENTS]

    await update.message.reply_text(
        "أهلاً وسهلاً بك في بوت كلمات الطلاب 🎓\n\n"
        "يرجى اختيار القسم:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard, resize_keyboard=True
        )
    )
    return DEPARTMENT


async def get_department(update: Update, context: ContextTypes.DEFAULT_TYPE):
    department = update.message.text.strip()

    if department not in DEPARTMENTS:
        await update.message.reply_text("يرجى اختيار قسم من الأزرار.")
        return DEPARTMENT

    context.user_data["department"] = department

    await update.message.reply_text(
        "تم اختيار القسم بنجاح.\n\n"
        "اكتب اسمك الكامل:",
        reply_markup=ReplyKeyboardRemove()
    )
    return NAME


async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()

    if not name or len(name) > 100:
        await update.message.reply_text(
            "يرجى إدخال اسم صحيح لا يتجاوز 100 حرف."
        )
        return NAME

    context.user_data["name"] = name

    await update.message.reply_text(
        "الآن اكتب كلمة الإهداء.\n"
        "يجب أن تكون أقل من 120 حرفاً."
    )
    return DEDICATION


async def get_dedication(update: Update, context: ContextTypes.DEFAULT_TYPE):
    dedication = update.message.text.strip()

    if not dedication:
        await update.message.reply_text("يرجى كتابة الإهداء.")
        return DEDICATION

    # الحد الأقصى 119 حرفاً
    if len(dedication) >= 120:
        await update.message.reply_text(
            f"إهداؤك يحتوي على {len(dedication)} حرفاً.\n\n"
            "⚠️ يجب أن تكون كلمات الإهداء أقل من 120 حرفاً.\n"
            "يرجى اختصار الإهداء وإرساله من جديد."
        )
        return DEDICATION

    context.user_data["dedication"] = dedication

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "تأكيد الإرسال ✅", callback_data="confirm"
            ),
            InlineKeyboardButton(
                "تعديل الإهداء ✏️", callback_data="edit"
            )
        ]
    ])

    await update.message.reply_text(
        "راجع بياناتك قبل الإرسال:\n\n"
        f"القسم: {context.user_data['department']}\n"
        f"الاسم: {context.user_data['name']}\n"
        f"الإهداء: {dedication}\n"
        f"عدد الحروف: {len(dedication)}/119",
        reply_markup=keyboard
    )

    return CONFIRM


async def confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "edit":
        await query.edit_message_text(
            "اكتب الإهداء الجديد.\n"
            "يجب أن يكون أقل من 120 حرفاً."
        )
        return DEDICATION

    user_id = query.from_user.id

    department = context.user_data["department"]
    name = context.user_data["name"]
    dedication = context.user_data["dedication"]

    # إعادة التحقق قبل الإرسال
    if len(dedication) >= 120:
        await query.edit_message_text(
            "الإهداء يجب أن يكون أقل من 120 حرفاً."
        )
        return DEDICATION

    # حجز التسجيل لمنع تكرار الإرسال
    with sqlite3.connect(DB_PATH) as db:
        result = db.execute(
            """
            INSERT OR IGNORE INTO submissions
            (user_id, department, name, dedication, status)
            VALUES (?, ?, ?, ?, 'pending')
            """,
            (user_id, department, name, dedication)
        )

    if result.rowcount == 0:
        await query.edit_message_text(
            "عذراً، لقد سبق لك إرسال إهدائك.\n"
            "يسمح لكل طالب بإرسال إهداء واحد فقط."
        )
        context.user_data.clear()
        return ConversationHandler.END

    message = (
        "🎓 <b>إهداء جديد من أحد الطلاب</b>\n\n"
        f"📚 <b>القسم:</b> {html.escape(department)}\n"
        f"👤 <b>الاسم:</b> {html.escape(name)}\n\n"
        f"💌 <b>كلمة الإهداء:</b>\n"
        f"{html.escape(dedication)}"
    )

    try:
        await context.bot.send_message(
            chat_id=GROUP_ID,
            text=message,
            parse_mode="HTML"
        )

        with sqlite3.connect(DB_PATH) as db:
            db.execute(
                "UPDATE submissions SET status = 'sent' WHERE user_id = ?",
                (user_id,)
            )

    except Exception:
        logging.exception("Group message failed")

        with sqlite3.connect(DB_PATH) as db:
            db.execute(
                "DELETE FROM submissions WHERE user_id = ? AND status = 'pending'",
                (user_id,)
            )

        await query.edit_message_text(
            "تعذر إرسال الإهداء إلى المجموعة.\n"
            "لم يتم اعتماد تسجيلك، يرجى المحاولة لاحقاً."
        )
        return ConversationHandler.END

    await query.edit_message_text(
        "تم إرسال اسمك وإهداؤك بنجاح إلى مجموعة الطلاب 🌷\n\n"
        "لا يمكن إرسال إهداء آخر من حسابك."
    )

    context.user_data.clear()
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()

    await update.message.reply_text(
        "تم إلغاء التسجيل.\n"
        "أرسل /start للبدء من جديد."
    )

    return ConversationHandler.END


def main():
    init_db()

    app = Application.builder().token(TOKEN).build()

    conversation = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            DEPARTMENT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_department)
            ],
            NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)
            ],
            DEDICATION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_dedication)
            ],
            CONFIRM: [
                CallbackQueryHandler(
                    confirm, pattern="^(confirm|edit)$"
                )
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True
    )

    app.add_handler(conversation)
    app.add_handler(CommandHandler("cancel", cancel))

    app.run_polling()


if __name__ == "__main__":
    main()
