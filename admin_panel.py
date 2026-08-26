# admin_panel.py
from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import Database
from config import ADMIN_IDS
import os

db = Database()

class AdminPanel:
    @staticmethod
    async def is_admin(user_id: int) -> bool:
        """بررسی ادمین بودن کاربر"""
        return user_id in ADMIN_IDS or await db.is_admin(user_id)
    
    @staticmethod
    async def show_admin_menu(user_id: int) -> InlineKeyboardMarkup:
        """نمایش منوی مدیریت"""
        keyboard = [
            [InlineKeyboardButton("📋 درخواست‌های پرداخت", callback_data="admin_payments")],
            [InlineKeyboardButton("👥 مدیریت کاربران", callback_data="admin_users")],
            [InlineKeyboardButton("📊 آمار کلی", callback_data="admin_stats")],
            [InlineKeyboardButton("📢 ارسال پیام همگانی", callback_data="admin_broadcast")],
            [InlineKeyboardButton("📁 مدیریت اندپوینت‌ها", callback_data="admin_endpoints")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_menu")]
        ]
        return InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    @staticmethod
    async def get_payments_message() -> str:
        """گرفتن پیام درخواست‌های پرداخت"""
        payments = await db.get_pending_payments()
        if not payments:
            return "📋 هیچ درخواست پرداخت جدیدی وجود ندارد."
        
        message = "📋 **درخواست‌های پرداخت در انتظار تأیید:**\n\n"
        for p in payments[:10]:  # حداکثر ۱۰ تا
            message += f"🆔 #{p['id']}\n"
            message += f"👤 کاربر: {p.get('first_name', '')} (@{p.get('username', 'نامشخص')})\n"
            message += f"💰 مبلغ: {p['amount']:,} تومان\n"
            message += f"📦 بسته: {p['package']}\n"
            message += f"📅 تاریخ: {p['created_at']}\n"
            message += f"🖼️ اسکرین‌شات: {p['screenshot_path']}\n"
            message += "─────────────\n"
        
        if len(payments) > 10:
            message += f"\nو {len(payments) - 10} درخواست دیگر..."
        
        return message
    
    @staticmethod
    async def get_users_message(page: int = 0) -> str:
        """گرفتن پیام لیست کاربران"""
        users = await db.get_all_users(offset=page * 10, limit=10)
        if not users:
            return "📋 هیچ کاربری یافت نشد."
        
        message = f"📋 **لیست کاربران (صفحه {page + 1}):**\n\n"
        for u in users:
            status = "🚫" if u.get('is_banned', 0) == 1 else "✅"
            message += f"{status} 🆔 {u['user_id']}\n"
            message += f"👤 {u.get('first_name', '')} (@{u.get('username', 'نامشخص')})\n"
            message += f"📊 سطح: {u['tier']} | اعتبار: {u['credits']}\n"
            message += f"📅 ثبت‌نام: {u['registered_at']}\n"
            message += "─────────────\n"
        
        return message
    
    @staticmethod
    async def get_stats_message() -> str:
        """گرفتن پیام آمار"""
        stats = await db.get_admin_stats()
        
        message = f"""
📊 **آمار کلی ربات**

👥 **کاربران:**
• کل کاربران: {stats['total_users']}
• رایگان (Free): {stats['free_users']}
• ویژه (VIP): {stats['vip_users']}
• حرفه‌ای (Pro): {stats['pro_users']}
• مسدود شده: {stats['banned_users']}

💰 **مالی:**
• کل اعتبار موجود: {stats['total_credits']:,}
• درخواست‌های پرداخت: {stats['pending_payments']}

📱 **بمب‌ها:**
• کل ارسال‌ها: {stats['total_bombs']}
        """
        return message
    
    @staticmethod
    async def build_payment_keyboard(payment_id: int) -> InlineKeyboardMarkup:
        """ساخت کیبورد برای تأیید/رد پرداخت"""
        keyboard = [
            [
                InlineKeyboardButton("✅ تأیید", callback_data=f"approve_payment_{payment_id}"),
                InlineKeyboardButton("❌ رد", callback_data=f"reject_payment_{payment_id}")
            ],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_payments")]
        ]
        return InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    @staticmethod
    async def build_user_keyboard(user_id: int) -> InlineKeyboardMarkup:
        """ساخت کیبورد برای مدیریت کاربر"""
        user = await db.get_user(user_id)
        if not user:
            return InlineKeyboardMarkup(inline_keyboard=[])
        
        is_banned = user.get('is_banned', 0) == 1
        ban_text = "🚫 بن کردن" if not is_banned else "✅ رفع بن"
        ban_callback = f"ban_user_{user_id}" if not is_banned else f"unban_user_{user_id}"
        
        keyboard = [
            [InlineKeyboardButton("💰 تنظیم اعتبار", callback_data=f"set_credits_{user_id}")],
            [InlineKeyboardButton(ban_text, callback_data=ban_callback)],
            [InlineKeyboardButton("📊 مشاهده آمار", callback_data=f"user_stats_{user_id}")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_users")]
        ]
        return InlineKeyboardMarkup(inline_keyboard=keyboard)