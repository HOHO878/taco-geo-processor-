# إصلاح مشكلة ترميز النصوص في نظام التحديثات

## المشاكل الأصلية
كان يظهر أحد الأخطاء التالية عند محاولة فحص التحديثات:

### الخطأ الأول - مشكلة الترميز:
```
Failed to fetch the update manifest. Details: 'utf-8' codec can't decode byte 0xd3 in position 10: invalid continuation byte
```

### الخطأ الثاني - ملف فارغ:
```
Failed to fetch the update manifest. Details: Expecting value: line 1 column 1 (char 0)
```

## أسباب المشاكل
1. **مشكلة الترميز**: ملف `update_manifest.json` على جوجل درايف محفوظ بترميز مختلف عن UTF-8
2. **ملف فارغ**: الملف المحمل فارغ أو لا يحتوي على JSON صالح
3. **صفحة HTML**: جوجل درايف يعيد صفحة HTML بدلاً من الملف المطلوب

## الحل المطبق

### 1. إصلاح ملف `update_client_new.py`
تم إضافة معالجة متعددة الترميزات والتحقق من صحة الملفات في الدوال التالية:

#### دالة `fetch_manifest()`
- معالجة متعددة الترميزات
- فحص الملف الفارغ
- فحص صفحات HTML
- رسائل تشخيص مفصلة

#### دالة `download_file()`
- فحص حجم الملف المحمل
- التحقق من حالة HTTP
- حذف الملفات الفارغة

#### دالة `get_direct_download_link()`
- رسائل تشخيص للروابط
- معالجة أفضل للأخطاء

#### دالة `fetch_manifest()`
```python
# Try different encodings to handle the file properly
manifest_str = None
encodings_to_try = ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252', 'iso-8859-1']

for encoding in encodings_to_try:
    try:
        manifest_str = response.content.decode(encoding)
        print(f"Successfully decoded manifest using {encoding} encoding")
        break
    except UnicodeDecodeError:
        continue

if manifest_str is None:
    # If all encodings fail, try with error handling
    manifest_str = response.content.decode('utf-8', errors='replace')
```

#### دالة `pre_check()`
تم تطبيق نفس المعالجة على ملفات ZIP المحلية.

### 2. إصلاح ملف `taco.py`
تم إضافة معالجة متعددة الترميزات في دالة `check_for_updates()`:

```python
# Try to decode with different encodings
stdout_text = result.stdout
if isinstance(stdout_text, bytes):
    encodings_to_try = ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252', 'iso-8859-1']
    for encoding in encodings_to_try:
        try:
            stdout_text = result.stdout.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        # If all encodings fail, use error replacement
        stdout_text = result.stdout.decode('utf-8', errors='replace')
```

## الترميزات المدعومة
1. **UTF-8** - الترميز الافتراضي
2. **UTF-8-sig** - UTF-8 مع BOM
3. **Latin-1** - ISO-8859-1
4. **CP1252** - Windows-1252
5. **ISO-8859-1** - Western European

## اختبار الإصلاح
يمكنك اختبار الإصلاح باستخدام:
```bash
python test_encoding_fix.py
```

## النتيجة المتوقعة
بعد تطبيق هذه الإصلاحات، يجب أن يعمل نظام التحديثات بشكل صحيح دون ظهور أخطاء الترميز.

## ملاحظات إضافية
- تم إضافة معالجة للأخطاء في جميع مراحل قراءة الملفات
- تم تحسين رسائل التشخيص لتسهيل اكتشاف المشاكل
- النظام الآن أكثر مرونة في التعامل مع ملفات بترميزات مختلفة
