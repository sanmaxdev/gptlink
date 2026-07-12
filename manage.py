from __future__ import annotations

import argparse

from gptlink.config import settings
from gptlink.database import Database


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage GPTLink API keys")
    subcommands = parser.add_subparsers(dest="command", required=True)
    create = subcommands.add_parser("create-key", help="Create an API key")
    create.add_argument("name", nargs="?", default="Hermes")
    subcommands.add_parser("list-keys", help="List API keys without secrets")
    revoke = subcommands.add_parser("revoke-key", help="Revoke an API key")
    revoke.add_argument("id", type=int)
    args = parser.parse_args()

    settings.ensure_directories()
    database = Database(settings.database_path)
    database.initialize()

    if args.command == "create-key":
        print(database.create_api_key(args.name).secret)
    elif args.command == "list-keys":
        for key in database.list_api_keys():
            state = "revoked" if key["revoked_at"] else "active"
            print(f'{key["id"]}\t{key["prefix"]}\t{key["name"]}\t{state}')
    elif not database.revoke_api_key(args.id):
        raise SystemExit("Active key not found")


if __name__ == "__main__":
    main()

