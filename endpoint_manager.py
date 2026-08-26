# endpoint_manager.py - نسخه اصلاح شده
import json
import random
import os
from datetime import datetime
from typing import List, Dict, Optional

ENDPOINTS_FILE = "endpoints.json"

class EndpointManager:
    def __init__(self):
        self.endpoints = []
        self.disabled_endpoints = []
        self.load_endpoints()
    
    def load_endpoints(self):
        """بارگذاری اندپوینت‌ها از فایل JSON"""
        try:
            with open(ENDPOINTS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # بررسی اینکه داده یک لیست باشد
            if isinstance(data, list):
                self.endpoints = data
                # فیلتر کردن اندپوینت‌های غیرفعال
                self.endpoints = [e for e in self.endpoints if isinstance(e, dict) and e.get('active', True)]
            else:
                print("⚠️ فایل endpoints.json معتبر نیست! (لیست نیست)")
                self.endpoints = []
                
        except FileNotFoundError:
            print("⚠️ فایل endpoints.json پیدا نشد! ایجاد فایل جدید...")
            self.create_default_endpoints()
        except json.JSONDecodeError:
            print("⚠️ فایل endpoints.json خراب است! ایجاد فایل جدید...")
            self.create_default_endpoints()
    
    def create_default_endpoints(self):
        """ایجاد اندپوینت‌های پیش‌فرض"""
        self.endpoints = [
            {
                "name": "Snapp Drivers",
                "url": "https://digitalsignup.snapp.ir/oauth/drivers/api/v1/otp",
                "method": "POST",
                "headers": {"Content-Type": "application/json"},
                "payload": {"cellphone": "{phone}"},
                "type": "json",
                "active": True
            },
            {
                "name": "Tapsi",
                "url": "https://tap33.me/api/v2/user",
                "method": "POST",
                "headers": {"Content-Type": "application/json"},
                "payload": {"credential": {"phoneNumber": "0{phone}", "role": "PASSENGER"}},
                "type": "json",
                "active": True
            },
            {
                "name": "Divar",
                "url": "https://api.divar.ir/v5/auth/authenticate",
                "method": "POST",
                "headers": {"Content-Type": "application/json"},
                "payload": {"phone": "0{phone}"},
                "type": "json",
                "active": True
            },
            {
                "name": "Alibaba",
                "url": "https://ws.alibaba.ir/api/v3/account/mobile/otp",
                "method": "POST",
                "headers": {"Content-Type": "application/json"},
                "payload": {"phoneNumber": "0{phone}"},
                "type": "json",
                "active": True
            },
            {
                "name": "Sheypoor",
                "url": "https://www.sheypoor.com/api/v10.0.0/auth/send",
                "method": "POST",
                "headers": {"Content-Type": "application/json"},
                "payload": {"username": "0{phone}"},
                "type": "json",
                "active": True
            }
        ]
        self.save_endpoints()
        print("✅ فایل endpoints.json با اندپوینت‌های پیش‌فرض ایجاد شد!")
    
    def get_endpoints_for_tier(self, tier: str) -> List[Dict]:
        """دریافت اندپوینت‌ها بر اساس سطح کاربری"""
        limits = {
            'Free': 30,
            'VIP': 80,
            'Pro': 9999
        }
        limit = limits.get(tier, 30)
        
        # فیلتر کردن اندپوینت‌های فعال
        active_endpoints = [e for e in self.endpoints if e.get('active', True)]
        
        # اگر تعداد اندپوینت‌ها کمتر از حد مجاز باشد، همه را برمی‌گرداند
        if len(active_endpoints) <= limit:
            return active_endpoints.copy()
        
        # انتخاب تصادفی از اندپوینت‌ها
        return random.sample(active_endpoints, limit)
    
    def get_endpoints_count(self) -> int:
        """دریافت تعداد کل اندپوینت‌ها"""
        return len(self.endpoints)
    
    def get_active_count(self) -> int:
        """دریافت تعداد اندپوینت‌های فعال"""
        return len([e for e in self.endpoints if e.get('active', True)])
    
    def get_endpoint_by_name(self, name: str) -> Optional[Dict]:
        """دریافت اندپوینت با نام"""
        for endpoint in self.endpoints:
            if endpoint.get('name') == name:
                return endpoint
        return None
    
    def mark_inactive(self, endpoint_name: str, reason: str = "خطا در ارسال"):
        """غیرفعال کردن یک اندپوینت (در صورت خرابی)"""
        for endpoint in self.endpoints:
            if endpoint.get('name') == endpoint_name:
                endpoint['active'] = False
                endpoint['disabled_reason'] = reason
                endpoint['disabled_at'] = str(datetime.now())
                self.save_endpoints()
                return True
        return False
    
    def save_endpoints(self):
        """ذخیره تغییرات در فایل"""
        with open(ENDPOINTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.endpoints, f, ensure_ascii=False, indent=2)
    
    def get_all_endpoints(self) -> List[Dict]:
        """دریافت لیست تمام اندپوینت‌ها"""
        return self.endpoints.copy()
    
    def add_endpoint(self, endpoint: Dict) -> bool:
        """اضافه کردن اندپوینت جدید"""
        # بررسی تکراری نبودن
        for e in self.endpoints:
            if e.get('name') == endpoint.get('name'):
                return False
        
        self.endpoints.append(endpoint)
        self.save_endpoints()
        return True
    
    def remove_endpoint(self, endpoint_name: str) -> bool:
        """حذف اندپوینت"""
        for i, e in enumerate(self.endpoints):
            if e.get('name') == endpoint_name:
                del self.endpoints[i]
                self.save_endpoints()
                return True
        return False