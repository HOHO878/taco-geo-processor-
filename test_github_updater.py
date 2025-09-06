#!/usr/bin/env python3
"""
Test script for GitHub updater system.
"""

import sys
import os

# Add the current directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_github_updater():
    """Test the GitHub updater system."""
    print("=== اختبار نظام التحديثات ===")
    
    try:
        # Import the GitHub updater
        from github_updater import GitHubUpdater
        
        print("✅ تم تحميل GitHubUpdater بنجاح")
        
        # Initialize updater with your repository
        updater = GitHubUpdater("HOHO878", "taco-geo-processor")
        print("✅ تم تهيئة النظام بنجاح")
        
        # Test getting current version
        current_version = updater.get_current_version()
        print(f"✅ الإصدار الحالي: {current_version}")
        
        # Test checking for updates
        print("جاري فحص التحديثات...")
        result = updater.check_for_updates()
        
        print("\n=== نتيجة فحص التحديثات ===")
        print(f"الحالة: {result['status']}")
        
        if result['status'] == 'update_available':
            print(f"إصدار جديد متاح!")
            print(f"الإصدار الحالي: {result['current_version']}")
            print(f"الإصدار الجديد: {result['latest_version']}")
        elif result['status'] == 'up_to_date':
            print("أنت تستخدم أحدث إصدار")
            print(f"الإصدار الحالي: {result['current_version']}")
        else:
            print(f"خطأ: {result.get('message', 'خطأ غير معروف')}")
        
        return True
        
    except ImportError as e:
        print(f"❌ خطأ في تحميل الملف: {e}")
        return False
    except Exception as e:
        print(f"❌ خطأ في الاختبار: {e}")
        return False

if __name__ == "__main__":
    success = test_github_updater()
    if success:
        print("\n🎉 الاختبار نجح! النظام يعمل بشكل صحيح.")
    else:
        print("\n⚠️ الاختبار فشل. تحقق من الأخطاء أعلاه.")
