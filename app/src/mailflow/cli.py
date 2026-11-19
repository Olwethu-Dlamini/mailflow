"""Account commands for the server, e.g. the first admin:

    docker compose exec mailflow mailflow user add --email you@example.com --name You --admin

Passwords are typed at a prompt (twice), never given as an argument, so they stay out of the shell history.
"""

import argparse
import getpass
import os
import sys

from . import auth
from .store import Store


def _ask_password() -> str:
    while True:
        first = getpass.getpass("New password: ")
        try:
            auth.check_password_rule(first)
        except ValueError as error:
            print(error)
            continue
        if getpass.getpass("Again: ") == first:
            return first
        print("The two passwords differ, try again.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mailflow")
    groups = parser.add_subparsers(dest="group", required=True)
    user = groups.add_parser("user", help="manage accounts").add_subparsers(dest="action", required=True)
    add = user.add_parser("add", help="create an account")
    add.add_argument("--email", required=True)
    add.add_argument("--name", required=True)
    add.add_argument("--admin", action="store_true", help="may manage accounts")
    for action in ("reset", "disable", "enable"):
        user.add_parser(action, help=f"{action} an account").add_argument("--email", required=True)
    user.add_parser("list", help="list accounts")
    args = parser.parse_args(argv)

    store = Store(os.environ.get("DB_PATH", "/data/mailflow.db"))
    if args.action == "list":
        for u in store.list_users():
            flags = ", ".join(f for f, on in (("admin", u.is_admin), ("disabled", not u.active)) if on)
            print(f"{u.email}\t{u.name}\t{flags}")
        return 0
    if args.action == "add":
        if store.user_by_email(args.email):
            print(f"{args.email.strip().lower()} already has an account", file=sys.stderr)
            return 1
        store.add_user(args.email, args.name, auth.hash_password(_ask_password()), args.admin)
        print(f"Added {args.email.strip().lower()}")
        return 0

    found = store.user_by_email(args.email)
    if found is None:
        print(f"No account for {args.email}", file=sys.stderr)
        return 1
    if args.action == "reset":
        store.set_password(found.id, auth.hash_password(_ask_password()))
    else:
        store.set_active(found.id, args.action == "enable")
    print(f"{args.action.capitalize()}: {found.email}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
