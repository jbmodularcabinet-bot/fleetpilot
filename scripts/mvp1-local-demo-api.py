"""Run the WSL source against the preserved Windows development database; no seeding."""

import argparse
import asyncio
import ipaddress
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID

import asyncpg
import uvicorn
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
WINDOWS = Path(r"C:\Users\User\Documents\ChatGPT\FleetPilot")


async def validate_manifest(values):
    manifest = json.loads(
        (WINDOWS / ".runtime" / "mvp1_validation_results.json").read_text()
    )
    ids = [UUID(row["trip_id"]) for row in manifest]
    if len(ids) != 4 or len(set(ids)) != 4:
        raise RuntimeError(
            "Expected four retained validation trip identifiers; no records will be recreated"
        )
    connection = await asyncpg.connect(
        values["MIGRATION_DATABASE_URL"].replace(
            "postgresql+asyncpg://", "postgresql://"
        )
    )
    try:
        async with connection.transaction(readonly=True):
            if await connection.fetchval("SELECT current_database()") != "fleetpilot":
                raise RuntimeError("Unexpected development database")
            records = await connection.fetch(
                "SELECT id,organization_id,trip_number,reference_number,special_instructions,scheduled_pickup_at FROM trips WHERE id=ANY($1::uuid[]) ORDER BY scheduled_pickup_at,id",
                ids,
            )
            if len(records) != 4:
                raise RuntimeError(
                    "Retained validation trips are missing; refusing to reseed"
                )
            grouped = {}
            for row in records:
                if not (row["reference_number"] or "").startswith("MVP1-VAL-") or not (
                    row["special_instructions"] or ""
                ).startswith("TEST / MVP1 VALIDATION DATA"):
                    raise RuntimeError(
                        "A retained record is not explicitly labelled synthetic; review it manually"
                    )
                grouped.setdefault(str(row["organization_id"]), []).append(
                    str(row["id"])
                )
            print(
                json.dumps(
                    {
                        "retained_synthetic_trip_count": len(records),
                        "trips": [
                            {
                                "id": str(x["id"]),
                                "trip_number": x["trip_number"],
                                "scheduled_pickup_at": x[
                                    "scheduled_pickup_at"
                                ].isoformat(),
                            }
                            for x in records
                        ],
                        "source_records_changed": False,
                    }
                ),
                flush=True,
            )
            return grouped
    finally:
        await connection.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--origin", required=True)
    args = parser.parse_args()
    address = ipaddress.ip_address(args.host)
    if not address.is_private or args.host == "0.0.0.0":
        raise SystemExit("Bind only a specified private local interface")
    if os.name != "nt" or "wsl.localhost" not in str(ROOT).lower():
        raise SystemExit("Explicit Windows runtime / WSL source continuation required")
    values = {k: v for k, v in dotenv_values(WINDOWS / ".env").items() if v is not None}
    u = urlparse(values["DATABASE_URL"])
    if (
        u.hostname != "127.0.0.1"
        or u.port != 54329
        or u.path != "/fleetpilot"
        or values.get("ENVIRONMENT", "development") != "development"
    ):
        raise SystemExit(
            "Refusing an unexpected source database or production environment"
        )
    synthetic = asyncio.run(validate_manifest(values))
    os.environ.update(values)
    os.environ.pop("MIGRATION_DATABASE_URL", None)
    os.environ.update(
        {
            "ENVIRONMENT": "development",
            "WEB_ORIGIN": args.origin,
            "REPORTING_SYNTHETIC_TRIPS_JSON": json.dumps(synthetic),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    os.chdir(ROOT / "apps" / "api")
    sys.path.insert(0, str(ROOT / "apps" / "api"))
    print(
        json.dumps(
            {
                "source": str(ROOT),
                "bind": args.host,
                "port": 8016,
                "allowed_origin": args.origin,
                "production": False,
            }
        ),
        flush=True,
    )
    uvicorn.run(
        "fleetpilot.main:app",
        host=args.host,
        port=8016,
        access_log=False,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
