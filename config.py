# config.py
import os

BOT_TOKEN = "8586016384:AAFNSMHw-2TsJGZBcHKNOHrOzOa_HliZC9E"
ADMIN_IDS = [7351574618]

# تنظیمات سطوح کاربری
TIER_LIMITS = {
    'Free': 30,
    'VIP': 80,
    'Pro': 9999  # نامحدود
}

TIER_COOLDOWNS = {
    'Free': 300,   # 5 دقیقه
    'VIP': 180,    # 3 دقیقه
    'Pro': 60      # 1 دقیقه
}

# بسته‌های اعتبار
CREDIT_PACKAGES = {
    'small': {'amount': 50, 'price': 20000, 'label': '۵۰ بمب - ۲۰,۰۰۰ تومان'},
    'medium': {'amount': 150, 'price': 50000, 'label': '۱۵۰ بمب - ۵۰,۰۰۰ تومان'},
    'large': {'amount': 500, 'price': 150000, 'label': '۵۰۰ بمب - ۱۵۰,۰۰۰ تومان'}
}

# تنظیمات پایگاه داده
DB_PATH = "data/users.db"

# تنظیمات پوشه پرداخت
PAYMENT_FOLDER = "payments"