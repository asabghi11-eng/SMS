# bot_render.py - نسخه کامل اصلاح شده نهایی
import os
import asyncio
import logging
import sys
from flask import Flask, request, jsonify
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, CommandStart
from aiogram.types import Update, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN, ADMIN_IDS
from database import Database
from endpoint_manager import EndpointManager
from bomber_engine import BomberEngine
from admin_panel import AdminPanel
from utils import is_valid_phone, format_time

# تنظیمات لاگ
logging.basicConfig(level=logging.INFO)

# مقداردهی اولیه
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
app = Flask(__name__)

# دیتابیس و ...
db = Database()
endpoint_manager = EndpointManager()
bomber_engine = BomberEngine()

# ============================================================
# Flask Routes
# ============================================================

@app.route('/')
def home():
    return "✅ SMS Bomber Bot is running!"

@app.route('/health')
def health():
    return "OK", 200

@app.route('/webhook', methods=['POST'])
async def webhook():
    """دریافت درخواست‌های تلگرام"""
    try:
        update = Update(**request.json)
        await dp.feed_update(bot, update)
        return jsonify({"ok": True})
    except Exception as e:
        print(f"❌ خطا در Webhook: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500

# ============================================================
# کلاس‌های State (برای FSM)
# ============================================================

class BombState(StatesGroup):
    waiting_for_phone = State()

class PaymentState(StatesGroup):
    waiting_for_screenshot = State()

# ============================================================
# توابع کمکی
# ============================================================

async def get_main_keyboard(user_id: int):
    """کیبورد اصلی"""
    keyboard = [
        [InlineKeyboardButton(text="📱 SMS Bomber", callback_data="sms_bomb")],
        [InlineKeyboardButton(text="👤 پروفایل", callback_data="profile")],
        [InlineKeyboardButton(text="🔗 سیستم معرفی", callback_data="referral")],
        [InlineKeyboardButton(text="💰 خرید اعتبار", callback_data="buy_credits")],
        [InlineKeyboardButton(text="📊 آمار", callback_data="stats")]
    ]
    
    if await AdminPanel.is_admin(user_id):
        keyboard.append([InlineKeyboardButton(text="⚙️ پنل مدیریت", callback_data="admin_panel")])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# ============================================================
# Handler های ربات
# ============================================================

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    """دستور /start"""
    user_id = message.from_user.id
    first_name = message.from_user.first_name
    username = message.from_user.username
    last_name = message.from_user.last_name
    
    # بررسی کد معرف
    args = message.text.split()
    referred_by = None
    if len(args) > 1 and args[1].startswith('ref_'):
        referral_code = args[1][4:]
        referrer = await db.get_user_by_referral_code(referral_code)
        if referrer and referrer['user_id'] != user_id:
            referred_by = referrer['user_id']
    
    user = await db.get_user(user_id)
    if not user:
        user = await db.create_user(user_id, username, first_name, last_name, referred_by)
        await message.answer(
            f"👋 **خوش آمدید {first_name}!**\n\n"
            f"🎁 ۵ اعتبار رایگان به حساب شما اضافه شد!\n\n"
            f"📊 سطح: {user['tier']}\n"
            f"💰 اعتبار: {user['credits']}",
            reply_markup=await get_main_keyboard(user_id)
        )
    else:
        if user.get('is_banned', 0) == 1:
            await message.answer("🚫 شما مسدود شده‌اید!")
            return
        
        await message.answer(
            f"👋 **خوش برگشتی {first_name}!**\n\n"
            f"📊 سطح: {user['tier']}\n"
            f"💰 اعتبار: {user['credits']}\n"
            f"📱 معرفی‌ها: {user['referral_count']}",
            reply_markup=await get_main_keyboard(user_id)
        )

@dp.message(Command("ping"))
async def cmd_ping(message: types.Message):
    """بررسی وضعیت ربات"""
    await message.answer("🏓 Pong! ربات فعال است!")

@dp.message(Command("cancel"))
async def cmd_cancel(message: types.Message, state: FSMContext):
    """لغو عملیات"""
    await state.clear()
    await message.answer("❌ لغو شد!", reply_markup=await get_main_keyboard(message.from_user.id))

# ============================================================
# SMS Bomber
# ============================================================

@dp.callback_query(lambda c: c.data == "sms_bomb")
async def sms_bomb_menu(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    credits = await db.get_credits(user_id)
    
    if credits <= 0:
        await callback.message.edit_text(
            "❌ اعتبار شما کافی نیست!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💰 خرید اعتبار", callback_data="buy_credits")],
                [InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_to_menu")]
            ])
        )
        await callback.answer()
        return
    
    can_bomb, remaining, msg = await db.check_cooldown(user_id)
    if not can_bomb:
        await callback.message.edit_text(
            f"⏳ {msg}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_to_menu")]
            ])
        )
        await callback.answer()
        return
    
    await callback.message.edit_text(
        f"📱 شماره هدف را وارد کنید:\nمثال: 09123456789\n\n"
        f"💰 اعتبار شما: {credits}\n"
        f"برای لغو /cancel",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_to_menu")]
        ])
    )
    await state.set_state(BombState.waiting_for_phone)
    await callback.answer()

@dp.message(BombState.waiting_for_phone)
async def handle_phone(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    phone = message.text.strip()
    
    if not is_valid_phone(phone):
        await message.reply_text("❌ شماره نامعتبر!")
        return
    
    if phone.startswith('0'):
        phone = phone[1:]
    
    credits = await db.get_credits(user_id)
    if credits <= 0:
        await message.reply_text("❌ اعتبار کافی نیست!")
        await state.clear()
        return
    
    tier = await db.get_user_tier(user_id)
    endpoints = endpoint_manager.get_endpoints_for_tier(tier)
    
    if not endpoints:
        await message.reply_text("❌ هیچ اندپوینتی در دسترس نیست!")
        await state.clear()
        return
    
    if not await db.spend_credit(user_id, 1):
        await message.reply_text("❌ خطا در کسر اعتبار!")
        await state.clear()
        return
    
    await db.update_last_bomb_time(user_id)
    await message.reply_text(f"🚀 شروع حمله به {phone}...\n⏳ لطفاً صبر کنید...")
    
    def on_complete(result):
        asyncio.create_task(send_result(message, result, phone))
    
    bomber_engine.run_bomb(endpoints, phone, mode="storm", on_complete=on_complete)
    await state.clear()

async def send_result(message: types.Message, result: dict, phone: str):
    msg = f"""
✅ **حمله به {phone} کامل شد!**

📊 نتایج:
• مجموع: {result['total']}
• ✅ موفق: {result['success']}
• ❌ ناموفق: {result['failed']}
• ⚠️ خطا: {result['errors']}
    """
    await message.reply_text(msg, reply_markup=await get_main_keyboard(message.from_user.id))

# ============================================================
# دکمه بازگشت
# ============================================================

@dp.callback_query(lambda c: c.data == "back_to_menu")
async def back_to_menu(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "🏠 منوی اصلی",
        reply_markup=await get_main_keyboard(callback.from_user.id)
    )
    await callback.answer()

# ============================================================
# پروفایل
# ============================================================

@dp.callback_query(lambda c: c.data == "profile")
async def show_profile(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user = await db.get_user(user_id)
    stats = await db.get_user_stats(user_id)
    
    msg = f"""
👤 **پروفایل شما**

🆔 شناسه: {user_id}
⭐ سطح: {user['tier']}
💰 اعتبار: {user['credits']}
📱 معرفی‌ها: {user['referral_count']}
📊 کل بمب‌ها: {stats['total_bombs']}
    """
    
    await callback.message.edit_text(msg, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_to_menu")]
    ]))
    await callback.answer()

# ============================================================
# خرید اعتبار (ساده)
# ============================================================

@dp.callback_query(lambda c: c.data == "buy_credits")
async def buy_credits(callback: types.CallbackQuery):
    keyboard = [
        [InlineKeyboardButton(text="📦 ۵۰ بمب - ۲۰,۰۰۰ تومان", callback_data="buy_50")],
        [InlineKeyboardButton(text="📦 ۱۵۰ بمب - ۵۰,۰۰۰ تومان", callback_data="buy_150")],
        [InlineKeyboardButton(text="📦 ۵۰۰ بمب - ۱۵۰,۰۰۰ تومان", callback_data="buy_500")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_to_menu")]
    ]
    
    await callback.message.edit_text(
        "💰 **خرید اعتبار**\n\n"
        "بسته مورد نظر را انتخاب کنید:\n\n"
        "💳 شماره کارت: `6037-9918-1234-5678`\n"
        "👤 به نام: `حسین محمدی`\n\n"
        "پس از واریز، اسکرین‌شات را ارسال کنید.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )
    await callback.answer()

# ============================================================
# آمار
# ============================================================

@dp.callback_query(lambda c: c.data == "stats")
async def user_stats(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    stats = await db.get_user_stats(user_id)
    
    await callback.message.edit_text(
        f"📊 **آمار شما**\n\n"
        f"⭐ سطح: {stats['tier']}\n"
        f"💰 اعتبار: {stats['credits']}\n"
        f"📱 کل بمب‌ها: {stats['total_bombs']}\n"
        f"✅ موفق: {stats['total_success']}\n"
        f"❌ ناموفق: {stats['total_failed']}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_to_menu")]
        ])
    )
    await callback.answer()

# ============================================================
# پنل مدیریت (ساده)
# ============================================================

@dp.callback_query(lambda c: c.data == "admin_panel")
async def admin_panel(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if not await AdminPanel.is_admin(user_id):
        await callback.answer("❌ شما دسترسی ادمین ندارید!")
        return
    
    stats = await db.get_admin_stats()
    keyboard = [
        [InlineKeyboardButton(text="👥 لیست کاربران", callback_data="admin_users")],
        [InlineKeyboardButton(text="📊 آمار کلی", callback_data="admin_stats2")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_to_menu")]
    ]
    
    await callback.message.edit_text(
        f"⚙️ **پنل مدیریت**\n\n"
        f"👥 کل کاربران: {stats['total_users']}\n"
        f"💰 درخواست‌های پرداخت: {stats['pending_payments']}\n"
        f"📱 کل بمب‌ها: {stats['total_bombs']}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "admin_stats2")
async def admin_stats2(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if not await AdminPanel.is_admin(user_id):
        await callback.answer("❌ شما دسترسی ادمین ندارید!")
        return
    
    stats = await db.get_admin_stats()
    await callback.message.edit_text(
        f"📊 **آمار کلی**\n\n"
        f"👥 کل کاربران: {stats['total_users']}\n"
        f"🆓 رایگان: {stats['free_users']}\n"
        f"⭐ VIP: {stats['vip_users']}\n"
        f"💎 Pro: {stats['pro_users']}\n"
        f"💰 اعتبار کل: {stats['total_credits']:,}\n"
        f"📱 کل بمب‌ها: {stats['total_bombs']}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="admin_panel")]
        ])
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "admin_users")
async def admin_users(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if not await AdminPanel.is_admin(user_id):
        await callback.answer("❌ شما دسترسی ادمین ندارید!")
        return
    
    users = await db.get_all_users(offset=0, limit=10)
    msg = "👥 **لیست کاربران:**\n\n"
    
    for u in users:
        status = "🚫" if u.get('is_banned', 0) == 1 else "✅"
        msg += f"{status} {u['user_id']} | {u['tier']} | {u['credits']}\n"
    
    await callback.message.edit_text(msg, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="admin_panel")]
    ]))
    await callback.answer()

# ============================================================
# تنظیم Webhook
# ============================================================

async def set_webhook():
    """تنظیم Webhook برای Render"""
    webhook_url = os.environ.get("WEBHOOK_URL")
    if not webhook_url:
        app_name = os.environ.get("RENDER_SERVICE_NAME", "sms-bomber-bot")
        webhook_url = f"https://{app_name}.onrender.com/webhook"
    
    try:
        await bot.set_webhook(
            url=webhook_url,
            allowed_updates=types.AllowedUpdates.ALL
        )
        print(f"✅ Webhook تنظیم شد: {webhook_url}")
    except Exception as e:
        print(f"❌ خطا در تنظیم Webhook: {e}")

# ============================================================
# اجرا
# ============================================================

async def main():
    """اجرای اصلی ربات - حالت محلی با Polling"""
    print("🚀 ربات در حال راه‌اندازی...")
    print(f"📊 تعداد اندپوینت‌ها: {endpoint_manager.get_endpoints_count()}")
    print("✅ ربات آماده اجرا است!")
    await dp.start_polling(bot)

async def on_startup():
    """کارهای اولیه در شروع (برای Render)"""
    print("🚀 ربات در حال راه‌اندازی روی Render...")
    print(f"📊 تعداد اندپوینت‌ها: {endpoint_manager.get_endpoints_count()}")
    
    if os.environ.get("RENDER"):
        await set_webhook()
        print("✅ ربات با Webhook اجرا شد!")

def run_flask():
    """اجرای Flask (برای Render)"""
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

if __name__ == "__main__":
    if os.environ.get("RENDER"):
        # روی Render: Webhook و Flask
        asyncio.run(on_startup())
        run_flask()
    else:
        # محلی: Polling
        asyncio.run(main())