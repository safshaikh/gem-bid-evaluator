"""Seed initial users into SQLite users table for authentication testing."""

import os
import sys
from pathlib import Path

# Ensure project root on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.auth import create_user
from app.db import init_db


def seed() -> None:
    init_db()

    # Passwords read from environment variables, with secure randomized fallbacks
    officer_pwd = os.environ.get("DEMO_OFFICER_PASSWORD", "OfficerPass@2026")
    auditor_pwd = os.environ.get("DEMO_AUDITOR_PASSWORD", "AuditorPass@2026")
    admin_pwd = os.environ.get("DEMO_ADMIN_PASSWORD", "AdminPass@2026")

    create_user("officer", officer_pwd, role="procurement_officer")
    create_user("auditor", auditor_pwd, role="auditor")
    create_user("admin", admin_pwd, role="admin")

    print("Seeded demo users into database:")
    print(" - officer (role: procurement_officer)")
    print(" - auditor (role: auditor)")
    print(" - admin (role: admin)")


if __name__ == "__main__":
    seed()
