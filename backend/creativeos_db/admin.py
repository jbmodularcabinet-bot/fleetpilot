"""Trusted local administration. Never exposed as an HTTP endpoint."""
import argparse
import getpass
import json

from .auth import AuthService
from .multibrand import MultiBrandService
from .store import CreativeOSStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("migrate")
    user = commands.add_parser("user")
    user.add_argument("username")
    user.add_argument("--platform-admin", action="store_true")
    membership = commands.add_parser("membership")
    membership.add_argument("user_id")
    membership.add_argument("organization_id")
    membership.add_argument("role", choices=["OWNER", "EDITOR", "VIEWER"])
    revoke = commands.add_parser("revoke")
    revoke.add_argument("user_id")
    revoke.add_argument("organization_id")
    org = commands.add_parser("organization")
    org.add_argument("name")
    org.add_argument("slug")
    org.add_argument("--classification", choices=["NATIVE", "EXTERNAL"], default="EXTERNAL")
    org.add_argument("--ecosystem-key", default="")
    brand = commands.add_parser("brand")
    brand.add_argument("organization_id")
    brand.add_argument("name")
    brand.add_argument("--entity-type", choices=["BRAND", "PRODUCT"], default="BRAND")
    args = parser.parse_args()
    auth = AuthService(args.db)
    if args.command == "user":
        password = getpass.getpass("Password (12+ characters): ")
        if password != getpass.getpass("Confirm password: "):
            parser.error("Passwords did not match")
        result = auth.provision_user(args.username, password, is_platform_admin=args.platform_admin)
    elif args.command == "membership":
        auth.grant_membership(args.user_id, args.organization_id, args.role)
        result = {"membership": "updated"}
    elif args.command == "revoke":
        auth.revoke_membership(args.user_id, args.organization_id)
        result = {"membership": "revoked"}
    else:
        with CreativeOSStore(args.db) as store:
            multi = MultiBrandService(store)
            if args.command == "migrate":
                result = {"schema_version": store.migrate_to_latest()}
            elif args.command == "organization":
                result = multi.create_organization(args.name, args.slug, classification=args.classification, ecosystem_key=args.ecosystem_key)
            else:
                result = multi.create_brand(args.organization_id, {"name": args.name}, entity_type=args.entity_type)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
