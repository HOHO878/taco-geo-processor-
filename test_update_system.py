#!/usr/bin/env python3
"""
Test script to verify that the update system works correctly.
"""

import sys
import os
import json
import subprocess

# Add the current directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_update_client_directly():
    """Test the update client directly."""
    print("=== Testing Update Client Directly ===")
    
    updater_path = os.path.join(os.path.dirname(__file__), 'updater', 'update_client_new.py')
    manifest_url = "https://drive.google.com/uc?export=download&id=16byll_MpyEbMZvlEqVeXfgFpUwCpWFvz"
    
    try:
        print(f"Running: python {updater_path} --check-online {manifest_url}")
        
        # Run the update client
        result = subprocess.run(
            [sys.executable, updater_path, '--check-online', manifest_url],
            capture_output=True,
            text=False,  # Don't decode to text automatically
            timeout=30
        )
        
        print(f"Return code: {result.returncode}")
        print(f"Stdout length: {len(result.stdout)} bytes")
        print(f"Stderr length: {len(result.stderr)} bytes")
        
        # Try to decode stdout
        stdout_text = None
        if isinstance(result.stdout, bytes):
            encodings_to_try = ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252', 'iso-8859-1']
            for encoding in encodings_to_try:
                try:
                    stdout_text = result.stdout.decode(encoding)
                    print(f"✅ Successfully decoded stdout with {encoding}")
                    break
                except UnicodeDecodeError as e:
                    print(f"❌ Failed to decode with {encoding}: {e}")
                    continue
            else:
                stdout_text = result.stdout.decode('utf-8', errors='replace')
                print("⚠️ Used UTF-8 with error replacement for stdout")
        
        # Try to decode stderr
        stderr_text = None
        if isinstance(result.stderr, bytes):
            encodings_to_try = ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252', 'iso-8859-1']
            for encoding in encodings_to_try:
                try:
                    stderr_text = result.stderr.decode(encoding)
                    print(f"✅ Successfully decoded stderr with {encoding}")
                    break
                except UnicodeDecodeError as e:
                    print(f"❌ Failed to decode with {encoding}: {e}")
                    continue
            else:
                stderr_text = result.stderr.decode('utf-8', errors='replace')
                print("⚠️ Used UTF-8 with error replacement for stderr")
        
        print(f"\nStdout content: {stdout_text}")
        print(f"\nStderr content: {stderr_text}")
        
        # Try to parse JSON
        if stdout_text and stdout_text.strip():
            try:
                update_info = json.loads(stdout_text)
                print(f"✅ Successfully parsed JSON: {update_info}")
                return True
            except json.JSONDecodeError as e:
                print(f"❌ Failed to parse JSON: {e}")
                return False
        else:
            print("❌ No stdout content to parse")
            return False
            
    except subprocess.TimeoutExpired:
        print("❌ Update client timed out")
        return False
    except Exception as e:
        print(f"❌ Error running update client: {e}")
        return False

def test_local_manifest():
    """Test with local manifest file."""
    print("\n=== Testing with Local Manifest ===")
    
    local_manifest_path = os.path.join(os.path.dirname(__file__), 'updater', 'update_manifest.json')
    
    if not os.path.exists(local_manifest_path):
        print("❌ Local manifest file not found")
        return False
    
    try:
        with open(local_manifest_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)
        print(f"✅ Local manifest loaded: {manifest}")
        return True
    except Exception as e:
        print(f"❌ Failed to load local manifest: {e}")
        return False

def main():
    """Main test function."""
    print("Testing Update System Fixes")
    print("=" * 50)
    
    # Test local manifest
    local_success = test_local_manifest()
    
    # Test update client directly
    client_success = test_update_client_directly()
    
    print("\n" + "=" * 50)
    print("Test Results:")
    print(f"Local manifest test: {'✅ PASSED' if local_success else '❌ FAILED'}")
    print(f"Update client test: {'✅ PASSED' if client_success else '❌ FAILED'}")
    
    if local_success and client_success:
        print("\n🎉 All tests passed! The update system should work correctly.")
        return 0
    else:
        print("\n⚠️ Some tests failed. Check the output above for details.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
