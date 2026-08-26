# utils.py - نسخه کامل
import re
import json
import random
import string
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any

# ============================================================
# توابع اعتبارسنجی
# ============================================================

def is_valid_phone(phone: str) -> bool:
    """
    اعتبارسنجی شماره موبایل ایران
    پشتیبانی از: 09123456789, 9123456789, +989123456789, 00989123456789
    """
    # حذف فاصله‌ها و خط تیره
    phone = phone.replace(" ", "").replace("-", "").replace("_", "")
    
    patterns = [
        r"^09[0-9]{9}$",           # 09123456789
        r"^9[0-9]{9}$",            # 9123456789
        r"^\+989[0-9]{9}$",        # +989123456789
        r"^00989[0-9]{9}$",        # 00989123456789
        r"^989[0-9]{9}$",          # 989123456789
    ]
    
    for pattern in patterns:
        if re.match(pattern, phone):
            return True
    return False

def format_phone(phone: str) -> str:
    """
    استانداردسازی شماره (حذف +98 و 0 اول)
    خروجی: 9123456789
    """
    phone = phone.replace(" ", "").replace("-", "").replace("_", "")
    
    if phone.startswith("+98"):
        phone = phone[3:]
    elif phone.startswith("0098"):
        phone = phone[4:]
    elif phone.startswith("98"):
        phone = phone[2:]
    if phone.startswith("0"):
        phone = phone[1:]
    
    # اعتبارسنجی نهایی
    if re.match(r"^9[0-9]{9}$", phone):
        return phone
    return ""

def is_valid_email(email: str) -> bool:
    """اعتبارسنجی ایمیل"""
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return re.match(pattern, email) is not None


# ============================================================
# توابع فرمت‌سازی
# ============================================================

def format_time(seconds: int) -> str:
    """
    تبدیل ثانیه به فرمت دقیقه:ثانیه
    مثال: 125 -> "02:05"
    """
    if seconds <= 0:
        return "۰۰:۰۰"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes:02d}:{secs:02d}"

def format_time_persian(seconds: int) -> str:
    """
    تبدیل ثانیه به فرمت فارسی دقیقه و ثانیه
    مثال: 125 -> "۲ دقیقه و ۵ ثانیه"
    """
    if seconds <= 0:
        return "همین الان"
    
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    
    parts = []
    if minutes > 0:
        parts.append(f"{minutes} دقیقه")
    if secs > 0:
        parts.append(f"{secs} ثانیه")
    
    return " و ".join(parts)

def get_tier_emoji(tier: str) -> str:
    """دریافت ایموجی سطح کاربری"""
    emojis = {
        'Free': '🆓',
        'VIP': '⭐',
        'Pro': '💎'
    }
    return emojis.get(tier, '🆓')

def get_tier_name(tier: str) -> str:
    """دریافت نام فارسی سطح کاربری"""
    names = {
        'Free': 'رایگان',
        'VIP': 'ویژه',
        'Pro': 'حرفه‌ای'
    }
    return names.get(tier, 'رایگان')

def get_status_emoji(status: str) -> str:
    """دریافت ایموجی وضعیت"""
    emojis = {
        'success': '✅',
        'failed': '❌',
        'pending': '⏳',
        'error': '⚠️',
        'approved': '✅',
        'rejected': '❌'
    }
    return emojis.get(status, '❓')


# ============================================================
# توابع مربوط به پرداخت
# ============================================================

def create_payment_message(package: Dict) -> str:
    """ساخت پیام پرداخت برای کاربر"""
    return f"""
💰 **بسته {package.get('label', '')}**

📱 اعتبار: {package.get('amount', 0)} بمب
💵 قیمت: {package.get('price', 0):,} تومان

📌 **مراحل پرداخت:**
۱. مبلغ را به شماره کارت زیر واریز کنید
۲. اسکرین‌شات را ارسال کنید
۳. منتظر تأیید ادمین باشید

💳 شماره کارت: `6037-9918-1234-5678`
👤 به نام: `حسین محمدی`

⚠️ توجه: پس از ارسال اسکرین‌شات، درخواست شما در صف تأیید قرار می‌گیرد.
    """

def create_payment_admin_message(payment: Dict, user: Dict) -> str:
    """ساخت پیام پرداخت برای ادمین"""
    return f"""
📋 **درخواست پرداخت جدید**

🆔 شماره: #{payment['id']}
👤 کاربر: {user.get('first_name', '')} (@{user.get('username', 'نامشخص')})
🆔 شناسه: {payment['user_id']}
📦 بسته: {payment['package']}
💰 مبلغ: {payment['amount']:,} تومان
📅 تاریخ: {payment['created_at']}
🖼️ اسکرین‌شات: {payment['screenshot_path']}

برای تأیید یا رد، از پنل مدیریت استفاده کنید.
    """


# ============================================================
# توابع مربوط به اندپوینت‌ها
# ============================================================

def validate_endpoint(endpoint: Dict) -> tuple:
    """
    اعتبارسنجی اندپوینت
    بازگشت: (is_valid, error_message)
    """
    required_fields = ['name', 'url', 'method', 'payload']
    
    for field in required_fields:
        if field not in endpoint:
            return False, f"فیلد '{field}' الزامی است"
    
    if not endpoint.get('name') or not isinstance(endpoint['name'], str):
        return False, "نام اندپوینت باید یک رشته غیرخالی باشد"
    
    if not endpoint.get('url') or not isinstance(endpoint['url'], str):
        return False, "URL باید یک رشته غیرخالی باشد"
    
    if endpoint.get('method') not in ['GET', 'POST', 'PUT', 'DELETE']:
        return False, "متد باید یکی از GET, POST, PUT, DELETE باشد"
    
    if endpoint.get('type') not in ['json', 'form', 'text']:
        return False, "نوع باید یکی از json, form, text باشد"
    
    return True, ""


# ============================================================
# توابع کمکی عمومی
# ============================================================

def generate_referral_code(length: int = 6) -> str:
    """تولید کد معرف تصادفی"""
    chars = string.ascii_uppercase + string.digits
    # حذف کاراکترهای مبهم
    chars = chars.replace('O', '').replace('0', '').replace('I', '').replace('1', '')
    return ''.join(random.choices(chars, k=length))

def generate_id() -> str:
    """تولید شناسه یکتا"""
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    random_part = ''.join(random.choices(string.digits, k=4))
    return f"{timestamp}{random_part}"

def truncate_text(text: str, max_length: int = 100) -> str:
    """کوتاه‌سازی متن"""
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."

def safe_json_loads(text: str) -> Optional[Dict]:
    """بارگذاری ایمن JSON"""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


# ============================================================
# توابع مربوط به تاریخ و زمان
# ============================================================

def get_persian_date(date_str: str) -> str:
    """تبدیل تاریخ به فرمت فارسی (ساده)"""
    try:
        dt = datetime.fromisoformat(date_str)
        months = ['فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور',
                  'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند']
        # این یک تبدیل ساده است. برای تبدیل دقیق نیاز به کتابخانه jalali
        return f"{dt.year}/{dt.month:02d}/{dt.day:02d} {dt.hour:02d}:{dt.minute:02d}"
    except:
        return date_str

def is_time_expired(timestamp: str, seconds: int) -> bool:
    """بررسی انقضای زمان"""
    try:
        dt = datetime.fromisoformat(timestamp)
        elapsed = (datetime.now() - dt).total_seconds()
        return elapsed > seconds
    except:
        return True

def get_time_remaining(timestamp: str, seconds: int) -> int:
    """دریافت زمان باقی‌مانده"""
    try:
        dt = datetime.fromisoformat(timestamp)
        elapsed = (datetime.now() - dt).total_seconds()
        remaining = seconds - elapsed
        return max(0, int(remaining))
    except:
        return 0


# ============================================================
# توابع مربوط به لاگ
# ============================================================

def format_log_entry(log: Dict) -> str:
    """فرمت‌سازی یک ورودی لاگ"""
    return f"""
📱 **{log.get('target_phone', '')}**
✅ موفق: {log.get('success_count', 0)}
❌ ناموفق: {log.get('failed_count', 0)}
📅 {log.get('created_at', '')}
    """

def format_stats_for_user(stats: Dict) -> str:
    """فرمت‌سازی آمار برای کاربر"""
    tier_emoji = get_tier_emoji(stats.get('tier', 'Free'))
    
    return f"""
📊 **آمار شما**

⭐ سطح: {tier_emoji} {stats.get('tier', 'Free')}
💰 اعتبار: {stats.get('credits', 0)}
📱 معرفی‌ها: {stats.get('referral_count', 0)}

📱 **بمب‌ها:**
• کل ارسال‌ها: {stats.get('total_bombs', 0)}
• ✅ موفق: {stats.get('total_success', 0)}
• ❌ ناموفق: {stats.get('total_failed', 0)}
    """


# ============================================================
# توابع مربوط به ارور هندلینگ
# ============================================================

def get_error_message(error_code: str) -> str:
    """دریافت پیام خطا بر اساس کد"""
    messages = {
        'no_credits': '❌ اعتبار شما کافی نیست!',
        'no_endpoints': '❌ هیچ اندپوینتی در دسترس نیست!',
        'cooldown': '⏳ لطفاً منتظر بمانید...',
        'invalid_phone': '❌ شماره نامعتبر!',
        'banned': '🚫 شما مسدود شده‌اید!',
        'not_admin': '❌ شما دسترسی ادمین ندارید!',
        'user_not_found': '❌ کاربر یافت نشد!',
        'payment_failed': '❌ پرداخت ناموفق!',
        'already_referred': '⚠️ این کاربر قبلاً معرفی شده است!',
    }
    return messages.get(error_code, '❌ خطای ناشناخته!')


# ============================================================
# توابع مربوط به validation
# ============================================================

def validate_credit_amount(amount: int) -> bool:
    """اعتبارسنجی مقدار اعتبار"""
    return amount > 0 and amount <= 10000

def validate_package_name(package_name: str) -> bool:
    """اعتبارسنجی نام بسته"""
    valid_packages = ['small', 'medium', 'large']
    return package_name in valid_packages

def validate_user_id(user_id: int) -> bool:
    """اعتبارسنجی شناسه کاربر"""
    return user_id > 0 and user_id < 9999999999


# ============================================================
# توابع مربوط به ساخت پیام‌های آماده
# ============================================================

def create_welcome_message(user: Dict) -> str:
    """ساخت پیام خوش‌آمدگویی"""
    return f"""
👋 **خوش آمدید {user.get('first_name', '')}!**

🎁 **۵ اعتبار** رایگان به حساب شما اضافه شد!

📊 **اطلاعات حساب شما:**
• سطح: 🆓 Free
• اعتبار: ۵
• کد معرف: `{user.get('referral_code', '')}`

از منوی زیر استفاده کنید:
    """

def create_profile_message(user: Dict, stats: Dict) -> str:
    """ساخت پیام پروفایل"""
    tier_emoji = get_tier_emoji(user.get('tier', 'Free'))
    
    return f"""
👤 **پروفایل شما**

🆔 شناسه: `{user.get('user_id')}`
👤 نام: {user.get('first_name', '')}
⭐ سطح: {tier_emoji} {user.get('tier', 'Free')}
💰 اعتبار: {user.get('credits', 0)}
📱 معرفی‌ها: {user.get('referral_count', 0)}
📊 کل بمب‌ها: {stats.get('total_bombs', 0)}
✅ موفق: {stats.get('total_success', 0)}
❌ ناموفق: {stats.get('total_failed', 0)}
📅 تاریخ ثبت‌نام: {user.get('registered_at', '')[:10]}
    """


# ============================================================
# کلاس‌های کمکی
# ============================================================

class Color:
    """کلاس رنگ‌ها برای ترمینال"""
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    PURPLE = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'

def print_colored(text: str, color: str = Color.WHITE):
    """چاپ متن رنگی در ترمینال"""
    print(f"{color}{text}{Color.RESET}")

def print_success(text: str):
    """چاپ پیام موفقیت"""
    print_colored(f"✅ {text}", Color.GREEN)

def print_error(text: str):
    """چاپ پیام خطا"""
    print_colored(f"❌ {text}", Color.RED)

def print_warning(text: str):
    """چاپ پیام هشدار"""
    print_colored(f"⚠️ {text}", Color.YELLOW)

def print_info(text: str):
    """چاپ پیام اطلاعات"""
    print_colored(f"ℹ️ {text}", Color.CYAN)


# ============================================================
# توابع مربوط به فایل
# ============================================================

def ensure_directory_exists(path: str):
    """اطمینان از وجود پوشه"""
    import os
    os.makedirs(path, exist_ok=True)

def read_json_file(filepath: str) -> Optional[Dict]:
    """خواندن فایل JSON"""
    import os
    if not os.path.exists(filepath):
        return None
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return None

def write_json_file(filepath: str, data: Any):
    """نوشتن فایل JSON"""
    import os
    ensure_directory_exists(os.path.dirname(filepath))
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_file_size(filepath: str) -> int:
    """دریافت حجم فایل"""
    import os
    try:
        return os.path.getsize(filepath)
    except:
        return 0