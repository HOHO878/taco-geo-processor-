#!/usr/bin/env python3
"""
Script to clean up unused update-related files since we simplified the update system.
"""

import os
import shutil

def cleanup_unused_files():
    """Remove unused update-related files."""
    files_to_remove = [
        'updater/update_client_new.py',
        'updater/update_client.py', 
        'updater/apply_update.py',
        'updater/Survey_new_vergn_update_manifest.json',
        'updater/update_manifest.json',
        'updater/test_manifest.json',
        'test_encoding_fix.py',
        'test_update_system.py',
        'ENCODING_FIX_README.md',
        'SIMPLE_UPDATE_SOLUTION.md'
    ]
    
    print("Cleaning up unused update-related files...")
    
    for file_path in files_to_remove:
        if os.path.exists(file_path):
            try:
                if os.path.isfile(file_path):
                    os.remove(file_path)
                    print(f"✅ Removed file: {file_path}")
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
                    print(f"✅ Removed directory: {file_path}")
            except Exception as e:
                print(f"❌ Failed to remove {file_path}: {e}")
        else:
            print(f"⚠️ File not found: {file_path}")
    
    print("\nCleanup completed!")

if __name__ == "__main__":
    cleanup_unused_files()
