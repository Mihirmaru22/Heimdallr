"""Command-line helpers: `python -m app.cli create-admin EMAIL` (prompts for a password)."""

from __future__ import annotations

import argparse
import getpass
import sys

from sqlalchemy import select

from app.db import session_scope
from app.models import Membership, Organization, Role, User
from app.security import hash_password


def create_admin(email: str, password: str | None) -> None:
    password = password or getpass.getpass("Password (10+ characters): ")
    if len(password) < 10:
        sys.exit("Password must be at least 10 characters")
    with session_scope(bypass=True) as db:
        user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if user is None:
            user = User(email=email, password_hash=hash_password(password), display_name=email.split("@")[0])
            db.add(user)
            db.flush()
            org = Organization(name="Admin workspace", slug=f"admin-{str(user.id)[:8]}")
            db.add(org)
            db.flush()
            db.add(Membership(org_id=org.id, user_id=user.id, role=Role.owner))
        user.is_platform_admin = True
    print(f"{email} is now a platform admin")


def main() -> None:
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("create-admin", help="create or promote a platform admin")
    p.add_argument("email")
    p.add_argument("--password-stdin", action="store_true", help="read the password from stdin")
    args = parser.parse_args()
    if args.cmd == "create-admin":
        create_admin(args.email.lower(), sys.stdin.readline().strip() if args.password_stdin else None)


if __name__ == "__main__":
    main()
