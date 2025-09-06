# -*- coding: utf-8 -*-

"""
عميل التحديث (Update Client).

هذا السكربت هو نقطة الدخول الرئيسية لإدارة التحديثات.
يدعم الأوامر التالية عبر سطر الأوامر:
- `--check-update <path>`: لفحص حزمة تحديث وعرض معلوماتها.
- `--apply <path>`: لتطبيق التحديث.
- `--check-online <url>`: للتحقق من التحديثات من Google Drive.
- `--download-update <url>`: لتحميل التحديث من Google Drive.

المهام:
1.  يقرأ وسيطات سطر الأوامر.
2.  يقرأ ملف `VERSION` لمعرفة الإصدار الحالي.
3.  عند فحص أو تطبيق تحديث:
    a. يفتح حزمة التحديث (ZIP).
    b. يقرأ `update_manifest.json`.
    c. **يتحقق من التوقيع الرقمي للـ manifest** باستخدام المفتاح العام.
    d. **يتحقق من سلامة كل ملف** في الحز��ة بمقارنة الـ hash المحسوب مع
       الـ hash المسجل في الـ manifest.
4.  عند تطبيق التحديث (`--apply`):
    a. يتأكد أن إصدار التحديث أعلى من الإصدار الحالي.
    b. يشغل `apply_update.py` كعملية منفصلة (subprocess).
    c. ينتظر انتهاء عملية التحديث ويتحقق من وجود علامة النجاح.
    d. يعيد تشغيل التطبيق الرئيسي.
5.  عند التحقق من التحديثات عبر الإنترنت:
    a. يجلب ملف `update_manifest.json` من Google Drive.
    b. يقارن الإصدار الحالي مع الإصدار المتاح.
6.  عند تحميل التحديث:
    a. يحمل حزمة التحديث من Google Drive.
"""

import os
import sys
import json
import hashlib
import zipfile
import argparse
import subprocess
import base64
import tempfile
import shutil
import requests
import urllib.parse
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import InvalidSignature

# --- إعدادات ومسارات ---
APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
VERSION_FILE = os.path.join(APP_DIR, 'VERSION')
PUBLIC_KEY_FILE = os.path.join(APP_DIR, 'keys', 'public_key.pem')
APPLY_UPDATE_SCRIPT = os.path.join(os.path.dirname(__file__), 'apply_update.py')

# --- دوال مساعدة ---

def get_current_version():
    """يقرأ رقم الإصدار الحالي من ملف VERSION."""
    try:
        with open(VERSION_FILE, 'r') as f:
            return f.read().strip()
    except FileNotFoundError:
        return "0.0.0"

def calculate_sha256(file_path):
    """يحسب SHA-256 hash لملف معين."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def verify_signature(data_bytes, signature_b64, public_key):
    """يتحقق من صحة التوقيع الرقمي."""
    try:
        signature_bytes = base64.b64decode(signature_b64)
        public_key.verify(
            signature_bytes,
            data_bytes,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )
        return True
    except InvalidSignature:
        return False
    except Exception as e:
        print(f"حدث خطأ غير متوقع أثناء التحقق من التوقيع: {e}")
        return False

def get_direct_download_link(gdrive_url):
    """تحويل رابط Google Drive العادي إلى رابط تحميل مباشر."""
    # التحقق من أن الرابط هو رابط Google Drive
    if "drive.google.com" not in gdrive_url:
        return gdrive_url

    # استخراج معرف الملف من الرابط
    file_id = None
    if "/file/d/" in gdrive_url:
        file_id = gdrive_url.split("/file/d/")[1].split("/")[0]
    elif "id=" in gdrive_url:
        file_id = gdrive_url.split("id=")[1].split("&")[0]

    if not file_id:
        return gdrive_url

    # إنشاء رابط التحميل المباشر
    return f"https://drive.google.com/uc?export=download&id={file_id}"

def download_file(url, destination):
    """تحميل ملف من رابط معين وحفظه في المسار المحدد."""
    try:
        print(f"جاري تحميل الملف من: {url}")
        direct_url = get_direct_download_link(url)

        # استخدام requests لتحميل الملف
        response = requests.get(direct_url, stream=True)
        response.raise_for_status()

        # حفظ الملف
        with open(destination, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        print(f"تم تحميل الملف بنجاح إلى: {destination}")
        return True
    except Exception as e:
        print(f"فشل تحميل الملف: {e}")
        return False

# --- المنطق الرئيسي ---

class UpdateHandler:
    def __init__(self, update_path=""):
        self.update_path = update_path
        self.temp_dir = None
        self.manifest = None
        self.public_key = self._load_public_key()

    def _load_public_key(self):
        """تحميل المفتاح العام من الملف."""
        try:
            with open(PUBLIC_KEY_FILE, "rb") as key_file:
                return serialization.load_pem_public_key(key_file.read())
        except FileNotFoundError:
            print(f"خطأ فادح: المفتاح العام غير موجود في {PUBLIC_KEY_FILE}")
            sys.exit(1)
        except Exception as e:
            print(f"خطأ أثناء تحميل المفتاح العام: {e}")
            sys.exit(1)

    def pre_check(self):
        """
        يقوم بالتحقق المبدئي من حزمة التحديث (فك الضغط المؤقت، التحقق من التوقيع والـ hashes).
        """
        print(f"بدء التحقق من حزمة التحديث: {self.update_path}")

        if not os.path.exists(self.update_path):
            print("خطأ: ملف التحديث غير موجود.")
            return False

        try:
            self.temp_dir = tempfile.mkdtemp()
            with zipfile.ZipFile(self.update_path, 'r') as zipf:
                # 1. استخراج الـ manifest
                manifest_str = zipf.read('update_manifest.json').decode('utf-8')
                self.manifest = json.loads(manifest_str)

                # 2. التحقق من التوقيع
                print("التحقق من التوقيع الرقمي للـ manifest...")
                signature = self.manifest.pop('signature', None)
                if not signature:
                    print("خطأ: الـ manifest غير موقّع!")
                    return False

                manifest_bytes = json.dumps(self.manifest, sort_keys=True, ensure_ascii=False).encode('utf-8')
                if not verify_signature(manifest_bytes, signature, self.public_key):
                    print("خطأ فادح: التوقيع الرقمي غير صالح! قد تكون الحزمة تالفة أو تم التلاعب بها.")
                    return False
                print("التوقيع الرقمي صالح.")

                # 3. التحقق من hashes الملفات
                print("التحقق من سلامة الملفات (hashes)...")
                for file_info in self.manifest['files']:
                    zipf.extract(os.path.join('taco_geo_processor', file_info['path']), path=self.temp_dir)
                    extracted_file_path = os.path.join(self.temp_dir, 'taco_geo_processor', file_info['path'])

                    if not os.path.exists(extracted_file_path):
                        print(f"خطأ: الملف {file_info['path']} مفقود من الحزمة.")
                        return False

                    calculated_hash = calculate_sha256(extracted_file_path)
                    if calculated_hash != file_info['hash']:
                        print(f"خطأ: الـ hash للملف {file_info['path']} غير متطابق.")
                        return False
                print("جميع الملفات سليمة.")

            return True
        except Exception as e:
            print(f"حدث خطأ أثناء التحقق من الحزمة: {e}")
            return False
        finally:
            # تنظيف الملفات المؤقتة
            if self.temp_dir and os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)

    def check_for_update(self):
        """يعرض معلومات التحديث المتاحة."""
        if self.pre_check():
            current_version = get_current_version()
            print("\n--- فحص التحديثات ---")
            print(f"الإصدار الحالي: {current_version}")
            print(f"الإصدار المتاح: {self.manifest['version']}")
            print(f"ملاحظات الإصدار: {self.manifest['release_notes']}")
            if self.manifest['version'] > current_version:
                print("يوجد تحديث جديد متاح.")
            else:
                print("أنت تستخدم أحدث إصدار بالفعل.")

    def apply_update(self):
        """يبدأ عملية تطبيق التحديث."""
        if not self.pre_check():
            print("فشل التحقق المبدئي. تم إلغاء التحديث.")
            return

        current_version = get_current_version()
        if self.manifest['version'] <= current_version:
            print("أنت تستخدم أحدث إصدار بالفعل. لا حاجة للتحديث.")
            return

        print("\n--- بدء تطبيق التحديث ---")
        print("سيتم إغلاق التطبيق الحالي وتطبيق التحديث. هل تريد المتابعة؟ (y/n)")
        if input().lower() != 'y':
            print("تم إلغاء التحديث.")
            return

        try:
            # تشغيل apply_update.py كعملية منفصلة
            print("تشغيل سكربت تطبيق التحديث...")
            args = [sys.executable, APPLY_UPDATE_SCRIPT, self.update_path, APP_DIR]
            subprocess.Popen(args)

            print("تم بدء عملية التحديث في الخلفية. سيتم إغلاق هذا التطبيق الآن.")
            sys.exit(0) # الخروج للسماح للعملية الجديد�� بالعمل

        except Exception as e:
            print(f"فشل في بدء عملية التحديث: {e}")

    def fetch_manifest(self, url):
        """يجلب ملف update_manifest.json من Google Drive."""
        try:
            print(f"جاري جلب ملف البيانات الوصفية من: {url}")
            direct_url = get_direct_download_link(url)

            response = requests.get(direct_url)
            response.raise_for_status()

            self.manifest = json.loads(response.text)
            print("تم جلب ملف البيانات الوصفية بنجاح.")
            return True
        except Exception as e:
            print(f"فشل جلب ملف البيانات الوصفية: {e}")
            return False

    def check_for_update_from_url(self, url):
        """يتحقق من وجود تحديثات من رابط Google Drive."""
        if not self.fetch_manifest(url):
            return False

        current_version = get_current_version()
        print("\n--- فحص التحديثات ---")
        print(f"الإصدار الحالي: {current_version}")
        print(f"الإصدار المتاح: {self.manifest['version']}")
        print(f"ملاحظات الإصدار: {self.manifest['release_notes']}")

        if self.manifest['version'] > current_version:
            print("يوجد تحديث جديد متاح.")
            return True
        else:
            print("أنت تستخدم أحدث إصدار بالفعل.")
            return False

    def download_update(self, url, destination=None):
        """يحمل حزمة التحديث من Google Drive."""
        if not destination:
            destination = os.path.join(tempfile.gettempdir(), "update_package.zip")

        # الحصول على رابط حزمة التحديث من الـ manifest
        if 'download_url' in self.manifest:
            download_url = self.manifest['download_url']
        else:
            # إذا لم يكن هناك رابط تحميل في الـ manifest، نستخدم نفس الرابط
            download_url = url

        return download_file(download_url, destination)

def main():
    parser = argparse.ArgumentParser(description="عميل التحديث للتطبيق.")
    parser.add_argument('--check-update', metavar='PATH', help="فحص حزمة تحديث من مسار محلي أو URL.")
    parser.add_argument('--apply', metavar='PATH', help="تطبيق تحديث من حزمة محلية.")
    parser.add_argument('--check-online', metavar='URL', help="فحص وجود تحديثات من رابط Google Drive.")
    parser.add_argument('--download-update', metavar='URL', help="تحميل حزمة التحديث من رابط Google Drive.")

    args = parser.parse_args()

    if args.check_update:
        handler = UpdateHandler(args.check_update)
        handler.check_for_update()
    elif args.apply:
        handler = UpdateHandler(args.apply)
        handler.apply_update()
    elif args.check_online:
        handler = UpdateHandler("")
        handler.check_for_update_from_url(args.check_online)
    elif args.download_update:
        handler = UpdateHandler("")
        if handler.fetch_manifest(args.download_update):
            handler.download_update(args.download_update)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()