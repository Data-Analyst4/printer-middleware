#!/usr/bin/env python3
"""
GitHub repository setup script for Printer Middleware
"""

import subprocess
import sys
import os
from pathlib import Path

def run_command(cmd, description):
    """Run a command and handle errors"""
    print(f"🔄 {description}...")
    try:
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        print(f"✅ {description} completed")
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} failed: {e}")
        print(f"Error output: {e.stderr}")
        return None

def main():
    print("🚀 Setting up Printer Middleware GitHub Repository")
    print("=" * 50)

    # Check if git is initialized
    if not Path(".git").exists():
        print("❌ Not a git repository. Please run 'git init' first.")
        return

    # Get repository URL from user
    repo_url = input("Enter your GitHub repository URL (e.g., https://github.com/username/printer-middleware.git): ").strip()

    if not repo_url:
        print("❌ Repository URL is required")
        return

    # Add remote origin
    if run_command(f'git remote add origin "{repo_url}"', "Adding remote origin") is None:
        # If remote already exists, update it
        run_command(f'git remote set-url origin "{repo_url}"', "Updating remote origin")

    # Push main branch
    if run_command("git push -u origin master", "Pushing master branch") is None:
        print("❌ Failed to push master branch")
        return

    # Push tags
    if run_command("git push origin --tags", "Pushing version tags") is None:
        print("⚠️  Failed to push tags (they may already exist on remote)")

    print("\n🎉 GitHub repository setup complete!")
    print("\nNext steps:")
    print("1. Go to your GitHub repository: " + repo_url.replace('.git', ''))
    print("2. Create a release for v1.0.0:")
    print("   - Go to Releases → Create a new release")
    print("   - Tag: v1.0.0")
    print("   - Title: Version 1.0.0 - Enterprise-grade release")
    print("   - Copy description from CHANGELOG.md")
    print("3. Users can now download specific versions using:")
    print("   git clone --branch v1.0.0 " + repo_url)
    print("   # or download ZIP from releases")

if __name__ == "__main__":
    main()