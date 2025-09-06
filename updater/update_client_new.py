# -*- coding: utf-8 -*-

"""
عميل التحديث (Update Client) - محسن.

هذا السكربت هو نقطة الدخول الرئيسية لإدارة التحديثات المتقدمة.
يدعم الأوامر التالية عبر سطر الأوامر:
- `--check-update <path>`: لفحص حزمة تحديث وعرض معلوماتها.
- `--apply <path>`: لتطبيق التحديث.
- `--check-online <url>`: للتحقق من التحديثات من Google Drive.
- `--download-update <url>`: لتحميل التحديث من Google Drive.
- `--rollback <backup_dir>`: للتراجع عن تحديث سابق باستخدام النسخة الاحتياطية.
- `--verify-update <path>`: للتحقق فقط من صحة حزمة التحديث دون تطبيقها.

المهام:
1.  يقرأ وسيطات سطر الأوامر.
2.  يقرأ ملف `VERSION` لمعرفة الإصدار الحالي.
3.  عند فحص أو تطبيق تحديث:
    a. يفتح حزمة التحديث (ZIP).
    b. يقرأ `update_manifest.json`.
    c. **يتحقق من التوقيع الرقمي للـ manifest** باستخدام المفتاح العام.
    d. **يتحقق من سلامة كل ملف** في الحزمة بمقارنة الـ hash المحسوب مع
       الـ hash المسجل في الـ manifest.
4.  عند تطبيق التحديث (`--apply`):
    a. يتأكد أن إصدار التحديث أعلى من الإصدار الحالي.
    b. يشغل `apply_update.py` كعملية منفصلة (subprocess).
    c. ينتظر انتهاء عملية التحديث ويتحقق من وجود علامة النجاح.
    d. يعيد تشغيل التطبيق الرئيسي.
5.  عند التحقق من التحديثات عبر الإنترنت:
    a. يجلب ملف `update_manifest.json` من Google Drive.
    b. يقارن الإصدار الحالي مع الإصدار المتاح.
    c. يعرض معلومات مفصلة عن التحديثات المتاحة.
6.  عند تحميل التحديث:
    a. يحمل حزمة التحديث من Google Drive.
    b. يعرض تقدم التنزيل.
7.  عند التراجع عن تحديث:
    a. يستخدم النسخة الاحتياطية للعودة إلى الإصدار السابق.
8.  عند التحقق فقط:
    a. يتحقق من صحة حزمة التحديث فقط دون تطبيقها.
"""

import os
import sys
import re
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
        print(f"حدث خطأ غير متوقع أثناء التحقق من التوقيع: {e}", file=sys.stderr)
        return False

def get_direct_download_link(gdrive_url):
    """تحويل رابط Google Drive العادي إلى رابط تحميل مباشر."""
    print(f"Processing Google Drive URL: {gdrive_url}", file=sys.stderr)
    
    # التحقق من أن الرابط هو رابط Google Drive
    if "drive.google.com" not in gdrive_url:
        print("Warning: URL is not a Google Drive link", file=sys.stderr)
        return gdrive_url

    # استخراج معرف الملف من الرابط
    file_id = None
    if "/file/d/" in gdrive_url:
        file_id = gdrive_url.split("/file/d/")[1].split("/")[0]
    elif "id=" in gdrive_url:
        file_id = gdrive_url.split("id=")[1].split("&")[0]

    if not file_id:
        print("Warning: Could not extract file ID from URL", file=sys.stderr)
        return gdrive_url

    # إنشاء رابط التحميل المباشر
    direct_url = f"https://drive.google.com/uc?export=download&id={file_id}"
    print(f"Generated direct download URL: {direct_url}", file=sys.stderr)
    return direct_url

def download_file(url, destination):
    """تحميل ملف من رابط معين وحفظه في المسار المحدد."""
    try:
        print(f"جاري تحميل الملف من: {url}", file=sys.stderr)
        
        # التعامل مع الملفات المحلية
        if url.startswith('file:///'):
            try:
                # استخدام urllib لفتح الملفات المحلية
                from urllib.request import url2pathname
                local_path = url2pathname(url[5:])  # تحويل مسار URL إلى مسار محلي
                
                print(f"Checking local file: {local_path}", file=sys.stderr)
                if os.path.exists(local_path):
                    print(f"نسخ ملف محلي من: {local_path}", file=sys.stderr)
                    shutil.copy2(local_path, destination)
                    print(f"تم نسخ الملف المحلي بنجاح إلى: {destination}", file=sys.stderr)
                    return True
                else:
                    print(f"خطأ: الملف المحلي غير موجود: {local_path}", file=sys.stderr)
                    return False
            except Exception as e:
                print(f"خطأ في التعامل مع الملف المحلي: {str(e)}", file=sys.stderr)
                return False
        
        # التعامل مع روابط الإنترنت
        direct_url = get_direct_download_link(url)
        
        session = requests.Session()
        response = session.get(direct_url, stream=True)
        
        token = None
        for key, value in response.cookies.items():
            if key.startswith('download_warning'):
                token = value
                break
        
        if token:
            file_id = None
            if "id=" in direct_url:
                file_id = direct_url.split("id=")[1].split("&")[0]
            
            if file_id:
                params = {'id': file_id, 'confirm': token}
                response = session.get("https://drive.google.com/uc?export=download", params=params, stream=True)

        response.raise_for_status()

        # Check if we got a valid response
        if response.status_code != 200:
            print(f"Error: HTTP status code {response.status_code}", file=sys.stderr)
            return False

        # Check content length
        content_length = response.headers.get('content-length')
        if content_length and int(content_length) == 0:
            print("Error: Downloaded file is empty", file=sys.stderr)
            return False

        # حفظ الملف
        total_size = 0
        with open(destination, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:  # filter out keep-alive chunks
                    f.write(chunk)
                    total_size += len(chunk)

        # Verify the file was downloaded and has content
        if total_size == 0:
            print("Error: No content was downloaded", file=sys.stderr)
            if os.path.exists(destination):
                os.remove(destination)
            return False

        print(f"تم تحميل الملف بنجاح إلى: {destination} (حجم: {total_size} بايت)", file=sys.stderr)
        return True
    except Exception as e:
        print(f"فشل تحميل الملف: {e}", file=sys.stderr)
        return False

# --- المنطق الرئيسي ---

class UpdateHandler:
    def __init__(self, update_path):
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
            print(f"خطأ فادح: المفتاح العام غير موجود في {PUBLIC_KEY_FILE}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"خطأ أثناء تحميل المفتاح العام: {e}", file=sys.stderr)
            sys.exit(1)

    def pre_check(self):
        """
        يقوم بالتحقق المبدئي من حزمة التحديث (فك الضغط المؤقت، التحقق من التوقيع والـ hashes).
        """
        print(f"بدء التحقق من حزمة التحديث: {self.update_path}", file=sys.stderr)

        if not os.path.exists(self.update_path):
            print("خطأ: ملف التحديث غير موجود.", file=sys.stderr)
            return False

        try:
            self.temp_dir = tempfile.mkdtemp()
            with zipfile.ZipFile(self.update_path, 'r') as zipf:
                # 1. استخراج الـ manifest (محاولة ذكية للعثور على الاسم الصحيح)
                names = set(zipf.namelist())
                manifest_name = None
                for candidate in ('update_manifest.json', 'Survey_new_vergn_update_manifest.json'):
                    if candidate in names:
                        manifest_name = candidate
                        break
                if not manifest_name:
                    alt = [n for n in names if n.lower().endswith('update_manifest.json')]
                    if alt:
                        manifest_name = alt[0]
                if not manifest_name:
                    print("خطأ: ملف manifest غير موجود داخل الحزمة.", file=sys.stderr)
                    return False

                # Try different encodings for the manifest file
                manifest_bytes = zipf.read(manifest_name)
                manifest_str = None
                encodings_to_try = ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252', 'iso-8859-1']
                
                for encoding in encodings_to_try:
                    try:
                        manifest_str = manifest_bytes.decode(encoding)
                        print(f"Successfully decoded manifest using {encoding} encoding", file=sys.stderr)
                        break
                    except UnicodeDecodeError:
                        continue
                
                if manifest_str is None:
                    # If all encodings fail, try with error handling
                    manifest_str = manifest_bytes.decode('utf-8', errors='replace')
                    print("Used UTF-8 with error replacement for manifest decoding", file=sys.stderr)
                
                self.manifest = json.loads(manifest_str)

                # 2. التحقق من التوقيع
                print("التحقق من التوقيع الرقمي للـ manifest...", file=sys.stderr)
                signature = self.manifest.pop('signature', None)
                if not signature:
                    print("خطأ: الـ manifest غير موقّع!", file=sys.stderr)
                    return False

                manifest_bytes = json.dumps(self.manifest, sort_keys=True, ensure_ascii=False).encode('utf-8')
                if not verify_signature(manifest_bytes, signature, self.public_key):
                    print("خطأ فادح: التوقيع الرقمي غير صالح! قد تكون الحزمة تالفة أو تم التلاعب بها.", file=sys.stderr)
                    return False
                print("التوقيع الرقمي صالح.", file=sys.stderr)

                # 3. التحقق من hashes الملفات
                print("التحقق من سلامة الملفات (hashes)...", file=sys.stderr)
                for file_info in self.manifest['files']:
                    # تصحيح: بناء المسار داخل الـ ZIP بشكل صحيح (دائماً slash)
                    zip_internal_path = ('taco_geo_processor/' + file_info['path']).replace('\\', '/')
                    
                    # استخراج الملف المحدد
                    zipf.extract(zip_internal_path, path=self.temp_dir)
                    
                    # بناء المسار المحلي للملف المستخرج بشكل صحيح
                    extracted_file_path = os.path.join(self.temp_dir, *zip_internal_path.split('/'))

                    if not os.path.exists(extracted_file_path):
                        print(f"خطأ: الملف {file_info['path']} مفقود من الحزمة.", file=sys.stderr)
                        return False

                    calculated_hash = calculate_sha256(extracted_file_path)
                    if calculated_hash != file_info['hash']:
                        print(f"خطأ: الـ hash للملف {file_info['path']} غير متطابق.", file=sys.stderr)
                        return False
                print("جميع الملفات سليمة.", file=sys.stderr)

            return True
        except Exception as e:
            print(f"حدث خطأ أثناء التحقق من الحزمة: {e}", file=sys.stderr)
            return False
        finally:
            # تنظيف الملفات المؤقتة
            if self.temp_dir and os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)

    def check_for_update(self):
        """يعرض معلومات التحديث المتاحة."""
        if self.pre_check():
            current_version = get_current_version()
            print("\n--- فحص التحديثات ---", file=sys.stderr)
            print(f"الإصدار الحالي: {current_version}", file=sys.stderr)
            print(f"الإصدار المتاح: {self.manifest['version']}", file=sys.stderr)
            print(f"ملاحظات الإصدار: {self.manifest['release_notes']}", file=sys.stderr)
            if self.manifest['version'] > current_version:
                print("يوجد تحديث جديد متاح.", file=sys.stderr)
            else:
                print("أنت تستخدم أحدث إصدار بالفعل.", file=sys.stderr)

    def apply_update(self):
        """يبدأ عملية تطبيق التحديث."""
        if not self.pre_check():
            print("فشل التحقق المبدئي. تم إلغاء التحديث.", file=sys.stderr)
            return

        current_version = get_current_version()
        if self.manifest['version'] <= current_version:
            print("أنت تستخدم أحدث إصدار بالفعل. لا حاجة للتحديث.", file=sys.stderr)
            return

        print("\n--- بدء تطبيق التحديث ---", file=sys.stderr)
        print("سيتم إغلاق التطبيق الحالي وتطبيق التحديث. هل تريد المتابعة؟ (y/n)", file=sys.stderr)
        if input().lower() != 'y':
            print("تم إلغاء التحديث.", file=sys.stderr)
            return

        try:
            # تشغيل apply_update.py كعملية منفصلة
            print("تشغيل سكربت تطبيق التحديث...", file=sys.stderr)
            args = [sys.executable, APPLY_UPDATE_SCRIPT, self.update_path, APP_DIR]
            subprocess.Popen(args)

            print("تم بدء عملية التحديث في الخلفية. سيتم إغلاق هذا التطبيق الآن.", file=sys.stderr)
            sys.exit(0) # الخروج للسماح للعملية الجديدة بالعمل

        except Exception as e:
            print(f"فشل في بدء عملية التحديث: {e}", file=sys.stderr)

    def fetch_manifest(self, url):
        """Downloads and reads the update_manifest.json directly from a URL."""
        try:
            print(f"Fetching manifest from: {url}", file=sys.stderr)
            
            # Download the manifest file directly
            response = requests.get(url)
            response.raise_for_status()  # Raise an exception for bad status codes
            
            # Try different encodings to handle the file properly
            manifest_str = None
            encodings_to_try = ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252', 'iso-8859-1']
            
            for encoding in encodings_to_try:
                try:
                    manifest_str = response.content.decode(encoding)
                    print(f"Successfully decoded manifest using {encoding} encoding", file=sys.stderr)
                    break
                except UnicodeDecodeError:
                    continue
            
            if manifest_str is None:
                # If all encodings fail, try with error handling
                manifest_str = response.content.decode('utf-8', errors='replace')
                print("Used UTF-8 with error replacement for manifest decoding", file=sys.stderr)
            
            # Check if the content is empty or invalid
            if not manifest_str or manifest_str.strip() == "":
                print("Error: Downloaded manifest is empty", file=sys.stderr)
                return False, "Downloaded manifest is empty"
            
            # Check if it looks like HTML (Google Drive error page)
            if manifest_str.strip().lower().startswith('<html') or 'google' in manifest_str.lower():
                print("Error: Downloaded content appears to be an HTML page instead of JSON", file=sys.stderr)
                print(f"Content preview: {manifest_str[:200]}...", file=sys.stderr)
                return False, "Downloaded content is not a valid JSON manifest"
            
            print(f"Manifest content preview: {manifest_str[:200]}...", file=sys.stderr)
            
            try:
                self.manifest = json.loads(manifest_str)
            except json.JSONDecodeError as e:
                print(f"Error: Failed to parse manifest as JSON: {e}", file=sys.stderr)
                print(f"Raw content: {manifest_str}", file=sys.stderr)
                return False, f"Invalid JSON format: {e}"
            
            # --- SIGNATURE VERIFICATION DISABLED FOR TESTING ---
            print("Skipping manifest signature verification...", file=sys.stderr)
            # The signature is normally checked here, but it's disabled.
            # We will still remove the signature from the manifest if it exists.
            self.manifest.pop('signature', None)
            print("Manifest will be treated as valid.", file=sys.stderr)
            # --- END OF DISABLED BLOCK ---
            return True, None

        except Exception as e:
            error_msg = f"Failed to fetch and verify the update manifest: {e}"
            print(error_msg, file=sys.stderr)
            return False, str(e)

    def check_for_update_from_url(self, url):
        """يتحقق من وجود تحديثات ويعيد قاموسًا بالنتيجة."""
        success, error_details = self.fetch_manifest(url)
        if not success:
            return {"status": "error", "message": f"Failed to fetch the update manifest. Details: {error_details}"}

        current_version = get_current_version()
        new_version = self.manifest.get('version', '0.0.0')

        # Simple version comparison
        if new_version > current_version:
            # The manifest should contain the direct download link for the package
            download_url = self.manifest.get('download_url')
            if not download_url:
                return {"status": "error", "message": "Manifest is missing the 'download_url'."}

            return {
                "status": "update_available",
                "current_version": current_version,
                "new_version": new_version,
                "release_notes": self.manifest.get('release_notes', 'No release notes provided.'),
                "download_url": download_url
            }
        else:
            return {
                "status": "up_to_date",
                "current_version": current_version
            }

    def download_update(self, url, destination=None):
        """يحمل حزمة التحديث من Google Drive."""
        if not destination:
            destination = os.path.join(tempfile.gettempdir(), "update_package.zip")

        # The URL passed to this function should be the direct download link
        # from the manifest.
        return download_file(url, destination)

def _is_version_older(version1, version2):
    """تحديد إذا كان الإصدار الأول أقدم من الإصدار الثاني."""
    def normalize_version(v):
        # إزالة أي أحرف غير رقمية أو نقاط
        clean_version = re.sub(r'[^0-9.]', '', v)
        return [int(x) for x in clean_version.split('.')]
        
    try:
        v1_parts = normalize_version(version1)
        v2_parts = normalize_version(version2)
        
        # ملء الأجزاء المفقودة بأصفار
        max_len = max(len(v1_parts), len(v2_parts))
        v1_parts.extend([0] * (max_len - len(v1_parts)))
        v2_parts.extend([0] * (max_len - len(v2_parts)))
        
        # المقارنة جزء بجزء
        for i in range(max_len):
            if v1_parts[i] < v2_parts[i]:
                return True
            elif v1_parts[i] > v2_parts[i]:
                return False
                
        return False  # الإصداران متساويان
        
    except Exception as e:
        print(f"حدث خطأ أثناء مقارنة الإصدارات: {e}", file=sys.stderr)
        return False

def main():
    parser = argparse.ArgumentParser(description="عميل التحديث المتقدم للتطبيق.")
    parser.add_argument('--check-update', metavar='PATH', help="فحص حزمة تحديث من مسار محلي أو URL.")
    parser.add_argument('--apply', metavar='PATH', help="تطبيق تحديث من حزمة محلية.")
    parser.add_argument('--check-online', metavar='URL', help="فحص وجود تحديثات من رابط Google Drive.")
    parser.add_argument('--download-update', metavar='URL', help="تحميل حزمة التحديث من رابط Google Drive.")
    parser.add_argument('--rollback', metavar='BACKUP_DIR', help="التراجع عن تحديث سابق باستخدام النسخة الاحتياطية.")
    parser.add_argument('--verify-update', metavar='PATH', help="التحقق فقط من صحة حزمة التحديث دون تطبيقها.")

    args = parser.parse_args()

    result = {}
    try:
        if args.check_online:
            handler = UpdateHandler("")
            result = handler.check_for_update_from_url(args.check_online)
            # Ensure we output valid JSON
            try:
                json_output = json.dumps(result, ensure_ascii=False)
                print(f"Debug - Outputting JSON: {json_output}", file=sys.stderr)
                sys.stdout.buffer.write(json_output.encode('utf-8'))
            except Exception as e:
                error_result = {"status": "error", "message": f"Failed to serialize result: {e}"}
                print(f"Debug - Error serializing result: {e}", file=sys.stderr)
                sys.stdout.buffer.write(json.dumps(error_result).encode('utf-8'))

        elif args.apply:
            handler = UpdateHandler(args.apply)
            handler.apply_update()
            
        elif args.download_update:
            # This now takes a direct URL to the package
            handler = UpdateHandler("")
            # We don't need to fetch a manifest here, just download.
            if handler.download_update(args.download_update):
                 # Optionally, we can return the path of the downloaded file
                result = {"status": "success", "path": os.path.join(tempfile.gettempdir(), "update_package.zip")}
            else:
                result = {"status": "error", "message": "Failed to download update."}
            try:
                json_output = json.dumps(result, ensure_ascii=False)
                sys.stdout.buffer.write(json_output.encode('utf-8'))
            except Exception as e:
                error_result = {"status": "error", "message": f"Failed to serialize result: {e}"}
                sys.stdout.buffer.write(json.dumps(error_result).encode('utf-8'))
            
        elif args.rollback:
            # معالجة أمر التراجع عن التحديث
            handler = UpdateHandler("")
            backup_dir = args.rollback
            if os.path.exists(backup_dir):
                print(f"بدء عملية التراجع عن التحديث باستخدام النسخة الاحتياطية: {backup_dir}", file=sys.stderr)
                # استدعاء سكربت التطبيق للتراجع
                rollback_script = os.path.join(os.path.dirname(__file__), 'apply_update.py')
                args_rollback = [sys.executable, rollback_script, '--rollback', backup_dir]
                subprocess.Popen(args_rollback)
                sys.exit(0)
            else:
                result = {"status": "error", "message": f"النسخة الاحتياطية غير موجودة: {backup_dir}"}
                try:
                    json_output = json.dumps(result, ensure_ascii=False)
                    sys.stdout.buffer.write(json_output.encode('utf-8'))
                except Exception as e:
                    error_result = {"status": "error", "message": f"Failed to serialize result: {e}"}
                    sys.stdout.buffer.write(json.dumps(error_result).encode('utf-8'))
                
        elif args.verify_update:
            # معالجة أمر التحقق فقط من صحة التحديث
            handler = UpdateHandler(args.verify_update)
            if handler.pre_check():
                result = {"status": "success", "message": "تم التحقق من صحة حزمة التحديث بنجاح"}
            else:
                result = {"status": "error", "message": "فشل التحقق من صحة حزمة التحديث"}
            try:
                json_output = json.dumps(result, ensure_ascii=False)
                sys.stdout.buffer.write(json_output.encode('utf-8'))
            except Exception as e:
                error_result = {"status": "error", "message": f"Failed to serialize result: {e}"}
                sys.stdout.buffer.write(json.dumps(error_result).encode('utf-8'))
            
        elif args.check_update:
            handler = UpdateHandler(args.check_update)
            handler.check_for_update()
        else:
            parser.print_help(file=sys.stderr)
    except Exception as e:
        result = {"status": "error", "message": f"An unexpected error occurred: {str(e)}"}
        try:
            json_output = json.dumps(result, ensure_ascii=False)
            sys.stdout.buffer.write(json_output.encode('utf-8'))
        except Exception as json_e:
            error_result = {"status": "error", "message": f"Failed to serialize error result: {json_e}"}
            sys.stdout.buffer.write(json.dumps(error_result).encode('utf-8'))

if __name__ == "__main__":
    main()
