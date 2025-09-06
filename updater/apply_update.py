# -*- coding: utf-8 -*-

"""
سكربت تطبيق التحديث (يعمل كعملية مستقلة).

هذا السكربت مصمم ليتم تشغيله من `update_client.py` وهو مسؤول عن
الخطوات الفعلية لاستبدال الملفات. تشغيله كعملية منفصلة يساعد في
تجاوز مشكلة قفل الملفات (File Locking) على أنظمة ويندوز، حيث لا يمكن
للتطبيق أن يستبدل ملفاته الخاصة أثناء تشغيله.

المهام:
1.  يستقبل مسار حزمة التحديث ومسار مجلد التطبيق الرئيسي كوسيطات.
2.  ينشئ نسخة احتياطية من مجلد `taco_geo_processor` الحالي.
3.  يستخرج الملفات الجديدة من حزمة التحديث.
4.  يستبدل المجلد القديم بالجديد.
5.  في حال حدوث أي خطأ، يقوم بإرجاع النسخة الاحتياطية (Rollback).
6.  بعد النجاح، يقوم بحذف النسخة الاحتياطية.
7.  يحدّث ملف `VERSION` برقم الإصدار الجديد من الـ manifest.
8.  ينشئ ملف `_update_success.flag` كعلامة للعملية الأم بنجاح التحديث.
"""

import os
import sys
import shutil
import zipfile
import json
import time

def log(message):
    """دالة بسيطة لطباعة الرسائل مع الوقت."""
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}")

def main():
    log("بدء عملية تطبيق التحديث...")

    # 1. قراءة الوسيطات من سطر الأوامر
    if len(sys.argv) != 3:
        log("خطأ: الوسيطات غير كافية.")
        log("الاستخدام: python apply_update.py <مسار_حزمة_التحديث> <مسار_التطبيق_الرئيسي>")
        sys.exit(1)

    zip_path = sys.argv[1]
    app_dir = sys.argv[2]

    # تحديد المسارات الهامة
    target_dir = os.path.join(app_dir, 'taco_geo_processor')
    backup_dir = os.path.join(app_dir, 'taco_geo_processor_backup')
    version_file = os.path.join(app_dir, 'VERSION')
    success_flag = os.path.join(app_dir, '_update_success.flag')

    # التأكد من أن المسارات موجودة
    if not os.path.exists(zip_path):
        log(f"خطأ: حزمة التحديث غير موجودة في {zip_path}")
        sys.exit(1)
    if not os.path.exists(target_dir):
        log(f"خطأ: المجلد الهدف للتحديث غير موجود في {target_dir}")
        sys.exit(1)

    # --- بدء عملية التحديث ---
    try:
        # 2. إنشاء نسخة احتياطية
        log(f"إنشاء نسخة احتياطية من '{os.path.basename(target_dir)}' إلى '{os.path.basename(backup_dir)}'...")
        if os.path.exists(backup_dir):
            shutil.rmtree(backup_dir) # حذف أي نسخة احتياطية قديمة
        shutil.move(target_dir, backup_dir)
        log("تم إنشاء النسخة الاحتياطية بنجاح.")

        # 3. استخراج حزمة التحديث
        log(f"استخراج الملفات من {os.path.basename(zip_path)}...")
        with zipfile.ZipFile(zip_path, 'r') as zipf:
            # استخراج مجلد taco_geo_processor فقط
            members = [m for m in zipf.namelist() if m.startswith('taco_geo_processor/')]
            zipf.extractall(app_dir, members=members)
        log("تم استخراج الملفات الجديدة بنجاح.")

        # 4. Read the new version from the manifest inside the zip
        log("Reading new version number...")
        new_version = "0.0.0"
        with zipfile.ZipFile(zip_path, 'r') as zipf:
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

            if manifest_name:
                with zipf.open(manifest_name) as manifest_file:
                    manifest_data = json.load(manifest_file)
                    new_version = manifest_data.get('version', '0.0.0')
            else:
                log("Warning: No manifest file found inside the update package.")

        # 5. Update the VERSION file
        if new_version != "0.0.0":
            log(f"Updating VERSION file to {new_version}...")
            with open(version_file, 'w') as f:
                f.write(new_version)
            log("Version file updated.")
        else:
            log("Warning: Could not determine new version from manifest.")

        # 6. حذف النسخة الاحتياطية بعد نجاح كل شيء
        log("التحديث ناجح. يتم الآن حذف النسخة الاحتياطية...")
        shutil.rmtree(backup_dir)
        log("تم حذف النسخة الاحتياطية.")

        # 7. إنشاء علامة النجاح
        with open(success_flag, 'w') as f:
            f.write('success')

        log("اكتملت عملية تطبيق التحديث بنجاح!")

    except Exception as e:
        log(f"حدث خطأ فادح أثناء التحديث: {e}")
        log("!!! بدء عملية الإرجاع (Rollback) !!!")
        
        # Rollback: استرجاع النسخة الاحتياطية
        if os.path.exists(backup_dir):
            if os.path.exists(target_dir):
                shutil.rmtree(target_dir) # حذف الملفات الجديدة غير المكتملة
            shutil.move(backup_dir, target_dir)
            log("تم استرجاع النسخة الاحتياطية بنجاح.")
        else:
            log("خطأ في الإرجاع: النسخة الاحتياطية غير موجودة!")
        
        sys.exit(1) # الخروج برمز خطأ

if __name__ == "__main__":
    main()
