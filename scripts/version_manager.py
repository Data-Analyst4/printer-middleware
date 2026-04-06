#!/usr/bin/env python3
"""
Version management script for Printer Middleware
"""

import argparse
import json
import re
from datetime import datetime
from pathlib import Path

def get_current_version():
    """Get current version from app/version.py"""
    version_file = Path("app/version.py")
    with open(version_file, 'r') as f:
        content = f.read()

    match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
    return match.group(1) if match else None

def update_version(new_version, changes=None):
    """Update version in relevant files"""
    today = datetime.now().strftime("%Y-%m-%d")

    # Update app/version.py
    version_file = Path("app/version.py")
    with open(version_file, 'r') as f:
        content = f.read()

    # Update version
    content = re.sub(
        r'__version__\s*=\s*["\']([^"\']+)["\']',
        f'__version__ = "{new_version}"',
        content
    )

    # Update version info tuple
    content = re.sub(
        r'__version_info__\s*=\s*tuple\(map\(int,\s*__version__\.split\(\'.\'\)\)\)',
        f'__version_info__ = tuple(map(int, __version__.split(\'.\')))',
        content
    )

    # Add to version history if changes provided
    if changes:
        history_entry = f'    "{new_version}": {{"date": "{today}", "changes": {json.dumps(changes, indent=8)}}}'
        # Insert before the closing brace
        content = re.sub(
            r'(VERSION_HISTORY\s*=\s*\{[^}]*)\n\}',
            rf'\1,\n{history_entry}\n}}',
            content
        )

    with open(version_file, 'w') as f:
        f.write(content)

    # Update pyproject.toml
    pyproject_file = Path("pyproject.toml")
    with open(pyproject_file, 'r') as f:
        content = f.read()

    content = re.sub(
        r'version\s*=\s*["\']([^"\']+)["\']',
        f'version = "{new_version}"',
        content
    )

    with open(pyproject_file, 'w') as f:
        f.write(content)

    print(f"Updated version to {new_version}")

def create_git_tag(version, message):
    """Create git tag for the version"""
    import subprocess

    try:
        # Create annotated tag
        subprocess.run(["git", "tag", "-a", f"v{version}", "-m", message], check=True)
        print(f"Created git tag v{version}")
    except subprocess.CalledProcessError as e:
        print(f"Failed to create git tag: {e}")

def main():
    parser = argparse.ArgumentParser(description="Version management for Printer Middleware")
    parser.add_argument("action", choices=["get", "set", "tag"], help="Action to perform")
    parser.add_argument("--version", help="New version number (for set action)")
    parser.add_argument("--changes", nargs="+", help="List of changes (for set action)")
    parser.add_argument("--message", help="Tag message (for tag action)")

    args = parser.parse_args()

    if args.action == "get":
        version = get_current_version()
        print(f"Current version: {version}")

    elif args.action == "set":
        if not args.version:
            print("Error: --version required for set action")
            return

        update_version(args.version, args.changes)

        # Auto-create git commit
        import subprocess
        try:
            subprocess.run(["git", "add", "app/version.py", "pyproject.toml"], check=True)
            subprocess.run(["git", "commit", "-m", f"Bump version to {args.version}"], check=True)
            print(f"Committed version bump to {args.version}")
        except subprocess.CalledProcessError as e:
            print(f"Failed to commit version changes: {e}")

    elif args.action == "tag":
        version = get_current_version()
        if not version:
            print("Error: Could not determine current version")
            return

        message = args.message or f"Version {version}"
        create_git_tag(version, message)

if __name__ == "__main__":
    main()