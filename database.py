# database.py - نسخه کامل
import aiosqlite
import sqlite3
from datetime import datetime
import random
import string
import os
from typing import Optional, Dict, List, Any
from config import DB_PATH, TIER_COOLDOWNS

class Database:
    def __init__(self):
        self._init_db()
    
    def _init_db(self):
        """ایجاد جداول در اولین اجرا"""
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # جدول کاربران
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                tier TEXT DEFAULT 'Free',
                credits INTEGER DEFAULT 0,
                referral_count INTEGER DEFAULT 0,
                referral_code TEXT UNIQUE,
                referred_by INTEGER,
                last_bomb_time TIMESTAMP,
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_admin INTEGER DEFAULT 0,
                is_banned INTEGER DEFAULT 0,
                total_bombs_sent INTEGER DEFAULT 0
            )
        """)
        
        # جدول تراکنش‌های اعتبار
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS credit_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount INTEGER,
                type TEXT,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # جدول درخواست‌های پرداخت
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS payment_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount INTEGER,
                package TEXT,
                screenshot_path TEXT,
                status TEXT DEFAULT 'pending',
                admin_note TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                processed_at TIMESTAMP
            )
        """)
        
        # جدول معرفی‌ها
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER,
                referred_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_successful INTEGER DEFAULT 1
            )
        """)
        
        # جدول لاگ ارسال
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bomb_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                target_phone TEXT,
                endpoints_used INTEGER,
                success_count INTEGER,
                failed_count INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # جدول اندپوینت‌های غیرفعال
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS disabled_endpoints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                endpoint_name TEXT,
                disabled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                reason TEXT
            )
        """)
        
        conn.commit()
        conn.close()
    
    # ============================================================
    # توابع مدیریت کاربر
    # ============================================================
    
    async def get_user(self, user_id: int) -> Optional[Dict]:
        """دریافت اطلاعات کاربر"""
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM users WHERE user_id = ?",
                (user_id,)
            )
            row = await cursor.fetchone()
            return dict(row) if row else None
    
    async def get_user_by_referral_code(self, referral_code: str) -> Optional[Dict]:
        """دریافت کاربر با کد معرف"""
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM users WHERE referral_code = ?",
                (referral_code,)
            )
            row = await cursor.fetchone()
            return dict(row) if row else None
    
    async def create_user(self, user_id: int, username: str = None,
                         first_name: str = None, last_name: str = None,
                         referred_by: int = None) -> Dict:
        """ثبت‌نام کاربر جدید"""
        referral_code = self._generate_referral_code()
        
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """INSERT INTO users 
                   (user_id, username, first_name, last_name, referral_code, referred_by)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (user_id, username, first_name, last_name, referral_code, referred_by)
            )
            await db.commit()
            
            if referred_by:
                await self._increment_referral_count(referred_by, user_id)
            
            # اضافه کردن ۵ اعتبار رایگان برای کاربر جدید
            await self.add_credits(user_id, 5, "اعتبار خوش‌آمدگویی")
            
            return await self.get_user(user_id)
    
    def _generate_referral_code(self) -> str:
        chars = string.ascii_uppercase + string.digits
        return ''.join(random.choices(chars, k=6))
    
    async def _increment_referral_count(self, referrer_id: int, referred_id: int):
        """افزایش تعداد معرف‌ها و بررسی ارتقا به VIP"""
        async with aiosqlite.connect(DB_PATH) as db:
            # ثبت معرفی
            await db.execute(
                "INSERT INTO referrals (referrer_id, referred_id) VALUES (?, ?)",
                (referrer_id, referred_id)
            )
            
            # افزایش شمارش
            await db.execute(
                "UPDATE users SET referral_count = referral_count + 1 WHERE user_id = ?",
                (referrer_id,)
            )
            await db.commit()
            
            # بررسی ارتقا به VIP
            cursor = await db.execute(
                "SELECT referral_count, tier FROM users WHERE user_id = ?",
                (referrer_id,)
            )
            row = await cursor.fetchone()
            
            if row and row[0] >= 3 and row[1] == 'Free':
                await db.execute(
                    "UPDATE users SET tier = 'VIP' WHERE user_id = ?",
                    (referrer_id,)
                )
                await db.commit()
                return True
        return False
    
    # ============================================================
    # توابع مربوط به سطح کاربری (Tier)
    # ============================================================
    
    async def get_user_tier(self, user_id: int) -> str:
        """دریافت سطح کاربری"""
        user = await self.get_user(user_id)
        return user.get('tier', 'Free') if user else 'Free'
    
    async def get_available_endpoints_count(self, user_id: int) -> int:
        """دریافت تعداد اندپوینت‌های قابل استفاده بر اساس سطح"""
        tier = await self.get_user_tier(user_id)
        limits = {
            'Free': 30,
            'VIP': 80,
            'Pro': 9999
        }
        return limits.get(tier, 30)
    
    async def upgrade_to_vip(self, user_id: int) -> bool:
        """ارتقا به VIP"""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE users SET tier = 'VIP' WHERE user_id = ?",
                (user_id,)
            )
            await db.commit()
            return True
    
    async def upgrade_to_pro(self, user_id: int) -> bool:
        """ارتقا به Pro"""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE users SET tier = 'Pro' WHERE user_id = ?",
                (user_id,)
            )
            await db.commit()
            return True
    
    # ============================================================
    # توابع مربوط به زمان‌بندی (Cooldown)
    # ============================================================
    
    async def get_cooldown(self, user_id: int) -> int:
        """دریافت زمان انتظار بر اساس سطح کاربری"""
        tier = await self.get_user_tier(user_id)
        return TIER_COOLDOWNS.get(tier, 300)
    
    async def check_cooldown(self, user_id: int) -> tuple:
        """
        بررسی وضعیت زمان‌بندی
        بازگشت: (can_bomb, remaining_seconds, message)
        """
        user = await self.get_user(user_id)
        if not user:
            return False, 0, "❌ کاربر یافت نشد!"
        
        if user.get('is_banned', 0) == 1:
            return False, 0, "🚫 شما مسدود شده‌اید!"
        
        last_time = user.get('last_bomb_time')
        if not last_time:
            return True, 0, "✅ آماده ارسال!"
        
        last_bomb = datetime.fromisoformat(last_time)
        cooldown = await self.get_cooldown(user_id)
        elapsed = (datetime.now() - last_bomb).total_seconds()
        remaining = cooldown - elapsed
        
        if remaining > 0:
            minutes = int(remaining // 60)
            seconds = int(remaining % 60)
            return False, remaining, f"⏳ باید {minutes:02d}:{seconds:02d} صبر کنید!"
        
        return True, 0, "✅ آماده ارسال!"
    
    async def update_last_bomb_time(self, user_id: int):
        """به‌روزرسانی زمان آخرین ارسال"""
        now = datetime.now().isoformat()
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE users SET last_bomb_time = ? WHERE user_id = ?",
                (now, user_id)
            )
            await db.commit()
    
    # ============================================================
    # توابع مربوط به اعتبار (Credits)
    # ============================================================
    
    async def get_credits(self, user_id: int) -> int:
        """دریافت اعتبار کاربر"""
        user = await self.get_user(user_id)
        return user.get('credits', 0) if user else 0
    
    async def add_credits(self, user_id: int, amount: int, description: str = ""):
        """افزایش اعتبار کاربر"""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE users SET credits = credits + ? WHERE user_id = ?",
                (amount, user_id)
            )
            await db.execute(
                """INSERT INTO credit_transactions 
                   (user_id, amount, type, description) 
                   VALUES (?, ?, 'add', ?)""",
                (user_id, amount, description)
            )
            await db.commit()
    
    async def spend_credit(self, user_id: int, amount: int = 1) -> bool:
        """کسر اعتبار کاربر"""
        credits = await self.get_credits(user_id)
        if credits < amount:
            return False
        
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE users SET credits = credits - ? WHERE user_id = ?",
                (amount, user_id)
            )
            await db.execute(
                """INSERT INTO credit_transactions 
                   (user_id, amount, type, description) 
                   VALUES (?, ?, 'spend', ?)""",
                (user_id, amount, f"استفاده از بمب (۱ اعتبار)")
            )
            
            await db.execute(
                "UPDATE users SET total_bombs_sent = total_bombs_sent + 1 WHERE user_id = ?",
                (user_id,)
            )
            await db.commit()
            return True
    
    async def get_credit_history(self, user_id: int, limit: int = 10) -> List[Dict]:
        """دریافت تاریخچه اعتبار"""
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT * FROM credit_transactions 
                   WHERE user_id = ? 
                   ORDER BY created_at DESC 
                   LIMIT ?""",
                (user_id, limit)
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
    
    # ============================================================
    # توابع مربوط به معرفی (Referral)
    # ============================================================
    
    async def get_referral_count(self, user_id: int) -> int:
        """دریافت تعداد معرفی‌های کاربر"""
        user = await self.get_user(user_id)
        return user.get('referral_count', 0) if user else 0
    
    async def get_referral_link(self, user_id: int) -> str:
        """دریافت لینک معرفی کاربر"""
        user = await self.get_user(user_id)
        if not user:
            return ""
        code = user.get('referral_code', '')
        return f"https://t.me/YourBotName?start=ref_{code}"
    
    async def get_referral_list(self, user_id: int) -> List[Dict]:
        """دریافت لیست کاربرانی که معرفی کرده"""
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT u.user_id, u.username, u.first_name, u.registered_at
                   FROM referrals r
                   JOIN users u ON r.referred_id = u.user_id
                   WHERE r.referrer_id = ?
                   ORDER BY r.created_at DESC""",
                (user_id,)
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
    
    # ============================================================
    # توابع مربوط به پرداخت (Payment)
    # ============================================================
    
    async def add_payment_request(self, user_id: int, package: str, amount: int, screenshot_path: str) -> int:
        """ثبت درخواست پرداخت جدید"""
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                """INSERT INTO payment_requests 
                   (user_id, package, amount, screenshot_path) 
                   VALUES (?, ?, ?, ?)""",
                (user_id, package, amount, screenshot_path)
            )
            await db.commit()
            return cursor.lastrowid
    
    async def get_pending_payments(self) -> List[Dict]:
        """دریافت تمام درخواست‌های پرداخت در انتظار تأیید"""
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT pr.*, u.username, u.first_name, u.last_name 
                   FROM payment_requests pr
                   JOIN users u ON pr.user_id = u.user_id
                   WHERE pr.status = 'pending'
                   ORDER BY pr.created_at DESC"""
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
    
    async def get_payment_request(self, request_id: int) -> Optional[Dict]:
        """دریافت اطلاعات یک درخواست پرداخت"""
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM payment_requests WHERE id = ?",
                (request_id,)
            )
            row = await cursor.fetchone()
            return dict(row) if row else None
    
    async def approve_payment(self, request_id: int, admin_note: str = "") -> bool:
        """تأیید درخواست پرداخت و اضافه کردن اعتبار"""
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT user_id, amount FROM payment_requests WHERE id = ?",
                (request_id,)
            )
            row = await cursor.fetchone()
            if not row:
                return False
            
            user_id, amount = row
            
            await db.execute(
                """UPDATE payment_requests 
                   SET status = 'approved', admin_note = ?, processed_at = CURRENT_TIMESTAMP 
                   WHERE id = ?""",
                (admin_note, request_id)
            )
            
            await db.execute(
                "UPDATE users SET credits = credits + ? WHERE user_id = ?",
                (amount, user_id)
            )
            
            await db.execute(
                """INSERT INTO credit_transactions 
                   (user_id, amount, type, description) 
                   VALUES (?, ?, 'add', ?)""",
                (user_id, amount, f"پرداخت تأیید شده - درخواست #{request_id}")
            )
            
            await db.commit()
            return True
    
    async def reject_payment(self, request_id: int, admin_note: str = "") -> bool:
        """رد درخواست پرداخت"""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """UPDATE payment_requests 
                   SET status = 'rejected', admin_note = ?, processed_at = CURRENT_TIMESTAMP 
                   WHERE id = ?""",
                (admin_note, request_id)
            )
            await db.commit()
            return True
    
    # ============================================================
    # توابع مربوط به لاگ و آمار
    # ============================================================
    
    async def log_bomb(self, user_id: int, target_phone: str, endpoints_used: int, 
                       success_count: int, failed_count: int):
        """ثبت لاگ ارسال"""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """INSERT INTO bomb_logs 
                   (user_id, target_phone, endpoints_used, success_count, failed_count) 
                   VALUES (?, ?, ?, ?, ?)""",
                (user_id, target_phone, endpoints_used, success_count, failed_count)
            )
            await db.commit()
    
    async def get_user_stats(self, user_id: int) -> Dict:
        """دریافت آمار کاربر"""
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            
            # اطلاعات کاربر
            cursor = await db.execute(
                "SELECT tier, credits, referral_count, total_bombs_sent FROM users WHERE user_id = ?",
                (user_id,)
            )
            user_row = await cursor.fetchone()
            
            # تعداد کل لاگ‌ها
            cursor = await db.execute(
                "SELECT COUNT(*) as total, SUM(success_count) as success, SUM(failed_count) as failed FROM bomb_logs WHERE user_id = ?",
                (user_id,)
            )
            log_row = await cursor.fetchone()
            
            return {
                'tier': user_row[0] if user_row else 'Free',
                'credits': user_row[1] if user_row else 0,
                'referral_count': user_row[2] if user_row else 0,
                'total_bombs': user_row[3] if user_row else 0,
                'total_logs': log_row[0] if log_row else 0,
                'total_success': log_row[1] if log_row else 0,
                'total_failed': log_row[2] if log_row else 0
            }
    
    async def get_admin_stats(self) -> Dict:
        """دریافت آمار کلی برای ادمین"""
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            
            cursor = await db.execute("SELECT COUNT(*) FROM users")
            total_users = (await cursor.fetchone())[0]
            
            cursor = await db.execute("SELECT COUNT(*) FROM users WHERE tier = 'Free'")
            free_users = (await cursor.fetchone())[0]
            
            cursor = await db.execute("SELECT COUNT(*) FROM users WHERE tier = 'VIP'")
            vip_users = (await cursor.fetchone())[0]
            
            cursor = await db.execute("SELECT COUNT(*) FROM users WHERE tier = 'Pro'")
            pro_users = (await cursor.fetchone())[0]
            
            cursor = await db.execute("SELECT COUNT(*) FROM users WHERE is_banned = 1")
            banned_users = (await cursor.fetchone())[0]
            
            cursor = await db.execute("SELECT COUNT(*) FROM payment_requests WHERE status = 'pending'")
            pending_payments = (await cursor.fetchone())[0]
            
            cursor = await db.execute("SELECT COUNT(*) FROM bomb_logs")
            total_bombs = (await cursor.fetchone())[0]
            
            cursor = await db.execute("SELECT SUM(credits) FROM users")
            total_credits = (await cursor.fetchone())[0] or 0
            
            return {
                'total_users': total_users,
                'free_users': free_users,
                'vip_users': vip_users,
                'pro_users': pro_users,
                'banned_users': banned_users,
                'pending_payments': pending_payments,
                'total_bombs': total_bombs,
                'total_credits': total_credits
            }
    
    async def get_bomb_history(self, user_id: int, limit: int = 10) -> List[Dict]:
        """دریافت تاریخچه بمب‌ها"""
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT * FROM bomb_logs 
                   WHERE user_id = ? 
                   ORDER BY created_at DESC 
                   LIMIT ?""",
                (user_id, limit)
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
    
    # ============================================================
    # توابع مدیریت اندپوینت‌های غیرفعال
    # ============================================================
    
    async def disable_endpoint(self, endpoint_name: str, reason: str = "خطا در ارسال"):
        """غیرفعال کردن یک اندپوینت"""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """INSERT INTO disabled_endpoints (endpoint_name, reason) 
                   VALUES (?, ?)""",
                (endpoint_name, reason)
            )
            await db.commit()
    
    async def get_disabled_endpoints(self) -> List[str]:
        """دریافت لیست اندپوینت‌های غیرفعال"""
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT endpoint_name FROM disabled_endpoints"
            )
            rows = await cursor.fetchall()
            return [row[0] for row in rows]
    
    async def enable_endpoint(self, endpoint_name: str):
        """فعال کردن مجدد یک اندپوینت"""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "DELETE FROM disabled_endpoints WHERE endpoint_name = ?",
                (endpoint_name,)
            )
            await db.commit()
    
    # ============================================================
    # توابع مدیریت کاربران (ادمین)
    # ============================================================
    
    async def get_all_users(self, offset: int = 0, limit: int = 50) -> List[Dict]:
        """دریافت لیست همه کاربران با صفحه‌بندی"""
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT user_id, username, first_name, last_name, tier, credits, 
                          referral_count, registered_at, is_banned 
                   FROM users 
                   ORDER BY registered_at DESC 
                   LIMIT ? OFFSET ?""",
                (limit, offset)
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
    
    async def ban_user(self, user_id: int) -> bool:
        """بن کردن کاربر"""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE users SET is_banned = 1 WHERE user_id = ?",
                (user_id,)
            )
            await db.commit()
            return True
    
    async def unban_user(self, user_id: int) -> bool:
        """رفع بن کاربر"""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE users SET is_banned = 0 WHERE user_id = ?",
                (user_id,)
            )
            await db.commit()
            return True
    
    async def set_admin(self, user_id: int) -> bool:
        """ادمین کردن کاربر"""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE users SET is_admin = 1 WHERE user_id = ?",
                (user_id,)
            )
            await db.commit()
            return True
    
    async def remove_admin(self, user_id: int) -> bool:
        """برداشتن ادمین از کاربر"""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE users SET is_admin = 0 WHERE user_id = ?",
                (user_id,)
            )
            await db.commit()
            return True
    
    # ============================================================
    # توابع کمکی
    # ============================================================
    
    async def is_admin(self, user_id: int) -> bool:
        """بررسی ادمین بودن کاربر"""
        user = await self.get_user(user_id)
        return user.get('is_admin', 0) == 1 if user else False
    
    async def is_banned(self, user_id: int) -> bool:
        """بررسی بن بودن کاربر"""
        user = await self.get_user(user_id)
        return user.get('is_banned', 0) == 1 if user else False