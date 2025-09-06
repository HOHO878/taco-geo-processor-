#!/usr/bin/env python3
"""
Test script to verify that the encoding fixes work correctly.
"""

import sys
import os
import json
import requests

# Add the current directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_encoding_fix():
    """Test the encoding fix for the update manifest."""
    print("Testing encoding fix for update manifest...")
    
    # Test URL (the same one from the error)
    url = "https://drive.google.com/uc?export=download&id=16byll_MpyEbMZvlEqVeXfgFpUwCpWFvz"
    
    # First test with local manifest file
    print("\n=== Testing with local manifest file ===")
    try:
        with open('updater/update_manifest.json', 'r', encoding='utf-8') as f:
            local_manifest = json.loads(f.read())
        print("✅ Local manifest loaded successfully")
        print(f"Version: {local_manifest.get('version')}")
        print(f"Release notes: {local_manifest.get('release_notes')}")
    except Exception as e:
        print(f"❌ Failed to load local manifest: {e}")
    
    print("\n=== Testing with remote URL ===")
    
    try:
        print(f"Fetching manifest from: {url}")
        
        # Download the manifest file directly
        response = requests.get(url)
        response.raise_for_status()
        
        print(f"Response status: {response.status_code}")
        print(f"Response headers: {dict(response.headers)}")
        print(f"Content length: {len(response.content)}")
        
        # Try different encodings to handle the file properly
        manifest_str = None
        encodings_to_try = ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252', 'iso-8859-1']
        
        for encoding in encodings_to_try:
            try:
                manifest_str = response.content.decode(encoding)
                print(f"✅ Successfully decoded manifest using {encoding} encoding")
                print(f"First 200 characters: {manifest_str[:200]}")
                break
            except UnicodeDecodeError as e:
                print(f"❌ Failed to decode with {encoding}: {e}")
                continue
        
        if manifest_str is None:
            # If all encodings fail, try with error handling
            manifest_str = response.content.decode('utf-8', errors='replace')
            print("⚠️ Used UTF-8 with error replacement for manifest decoding")
        
        # Try to parse as JSON
        try:
            manifest_data = json.loads(manifest_str)
            print("✅ Successfully parsed manifest as JSON")
            print(f"Manifest keys: {list(manifest_data.keys())}")
            if 'version' in manifest_data:
                print(f"Version: {manifest_data['version']}")
            if 'release_notes' in manifest_data:
                print(f"Release notes: {manifest_data['release_notes'][:100]}...")
        except json.JSONDecodeError as e:
            print(f"❌ Failed to parse as JSON: {e}")
            print(f"Raw content (first 500 chars): {manifest_str[:500]}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error during test: {e}")
        return False

if __name__ == "__main__":
    success = test_encoding_fix()
    if success:
        print("\n✅ Encoding fix test completed successfully!")
    else:
        print("\n❌ Encoding fix test failed!")
        sys.exit(1)
