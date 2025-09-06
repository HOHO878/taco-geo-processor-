#!/usr/bin/env python3
"""
GitHub-based update system for TACO Geo Processor.
This provides a reliable alternative to Google Drive-based updates.
"""

import json
import requests
import webbrowser
from pathlib import Path
import os

class GitHubUpdater:
    def __init__(self, repo_owner, repo_name):
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/releases/latest"
        self.releases_url = f"https://github.com/{repo_owner}/{repo_name}/releases"
        
    def get_current_version(self):
        """Get current version from VERSION file."""
        try:
            version_file = Path(__file__).parent / 'VERSION'
            with open(version_file, 'r') as f:
                return f.read().strip()
        except:
            return "1.0.0"
    
    def get_latest_version(self):
        """Get latest version from GitHub API."""
        try:
            response = requests.get(self.api_url, timeout=10)
            response.raise_for_status()
            
            release_data = response.json()
            return {
                'version': release_data['tag_name'].lstrip('v'),
                'name': release_data['name'],
                'body': release_data['body'],
                'html_url': release_data['html_url'],
                'published_at': release_data['published_at'],
                'assets': release_data.get('assets', [])
            }
        except Exception as e:
            print(f"Error fetching latest version: {e}")
            return None
    
    def compare_versions(self, current, latest):
        """Compare version strings."""
        def version_tuple(version):
            return tuple(map(int, version.split('.')))
        
        try:
            current_tuple = version_tuple(current)
            latest_tuple = version_tuple(latest)
            return latest_tuple > current_tuple
        except:
            return False
    
    def check_for_updates(self):
        """Check if updates are available."""
        current_version = self.get_current_version()
        latest_info = self.get_latest_version()
        
        if not latest_info:
            return {
                'status': 'error',
                'message': 'فشل في جلب معلومات التحديثات من GitHub'
            }
        
        latest_version = latest_info['version']
        
        if self.compare_versions(current_version, latest_version):
            return {
                'status': 'update_available',
                'current_version': current_version,
                'latest_version': latest_version,
                'release_name': latest_info['name'],
                'release_notes': latest_info['body'],
                'download_url': latest_info['html_url'],
                'published_at': latest_info['published_at']
            }
        else:
            return {
                'status': 'up_to_date',
                'current_version': current_version,
                'latest_version': latest_version
            }
    
    def open_download_page(self):
        """Open the releases page in browser."""
        webbrowser.open(self.releases_url)

# Example usage
if __name__ == "__main__":
    updater = GitHubUpdater("your-username", "your-repo-name")
    result = updater.check_for_updates()
    print(json.dumps(result, indent=2, ensure_ascii=False))