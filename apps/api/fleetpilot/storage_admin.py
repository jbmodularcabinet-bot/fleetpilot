"""Explicit privileged, report-only reconciliation and portable evidence snapshots.

Run with the migration/backup account, never expose this as an HTTP endpoint.
Quiesce writers for coherent DB/object backups. Superseded bytes remain retained.
"""

import argparse
import asyncio
import hashlib
import json
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from .config import get_settings
from .evidence_storage import storage


def reconcile(rows, store):
    expected = {row["storage_key"]: row for row in rows}
    actual = set(store.keys())
    result = {"missing": [], "orphan": [], "checksum_mismatch": [], "superseded_retained": []}
    for key, row in expected.items():
        if key not in actual:
            result["missing"].append(str(row["id"]))
        elif hashlib.sha256(store.read(key)).hexdigest() != row["checksum"]:
            result["checksum_mismatch"].append(str(row["id"]))
        if row["status"] == "SUPERSEDED":
            result["superseded_retained"].append(str(row["id"]))
    # Key hashes identify orphan reports without disclosing internal locations.
    result["orphan"] = [
        hashlib.sha256(key.encode()).hexdigest() for key in sorted(actual - expected.keys())
    ]
    return result


def snapshot(rows, store, target):
    target = Path(target).resolve()
    target.mkdir(parents=True, exist_ok=False)
    manifest = []
    for row in rows:
        data = store.read(row["storage_key"])
        if hashlib.sha256(data).hexdigest() != row["checksum"]:
            raise RuntimeError("Snapshot aborted: object integrity failure")
        name = f"{row['id']}.png"
        (target / name).write_bytes(data)
        manifest.append({"file": name, "key": row["storage_key"], "checksum": row["checksum"]})
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2))


def restore_objects(source, store):
    source = Path(source).resolve()
    for item in json.loads((source / "manifest.json").read_text()):
        path = (source / item["file"]).resolve()
        if not path.is_relative_to(source) or path.suffix != ".png":
            raise ValueError("Unsafe snapshot path")
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != item["checksum"]:
            raise RuntimeError("Snapshot checksum mismatch")
        try:
            existing = store.read(item["key"])
        except FileNotFoundError:
            store.put(item["key"], data)
        else:
            if existing != data:
                raise RuntimeError("Restore refuses to overwrite different evidence")


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["reconcile", "snapshot", "restore-objects"])
    parser.add_argument("--directory")
    parser.add_argument("--confirm-restore", action="store_true")
    args = parser.parse_args()
    store = storage()
    if args.action == "restore-objects":
        if not args.confirm_restore or not args.directory:
            parser.error("Restoring requires --directory and --confirm-restore")
        restore_objects(args.directory, store)
        print("Evidence restore completed and checksums verified")
        return
    settings = get_settings()
    if not settings.migration_database_url:
        raise RuntimeError("Explicit privileged backup connection required")
    engine = create_async_engine(settings.migration_database_url)
    try:
        async with engine.connect() as db:
            # RLS must error rather than silently back up a partial tenant view.
            await db.execute(text("SET row_security = off"))
            rows = (
                (
                    await db.execute(
                        text(
                            "SELECT id, storage_key, checksum, status FROM delivery_evidence UNION ALL SELECT id, storage_key, checksum, status FROM expense_evidence UNION ALL SELECT id, storage_key, checksum, status FROM maintenance_evidence"
                        )
                    )
                )
                .mappings()
                .all()
            )
        if args.action == "reconcile":
            print(json.dumps(reconcile(rows, store), indent=2))
        else:
            if not args.directory:
                parser.error("Snapshot requires --directory")
            snapshot(rows, store, args.directory)
            print("Evidence snapshot complete; pair with quiesced PostgreSQL dump")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
