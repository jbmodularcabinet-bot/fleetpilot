import asyncio
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from fleetpilot.db import Session, set_context

from .conftest import login

pytestmark = pytest.mark.asyncio

DATA = {
    "customers": {
        "customer_code": "ACME-001",
        "company_name": "ACME Logistics Client",
        "contact_person": "Ana Reyes",
    },
    "vehicles": {"unit_number": "TRK-001", "plate_number": "ABC-1234", "vehicle_type": "Wing van"},
    "drivers": {
        "employee_number": "DRV-001",
        "first_name": "Juan",
        "last_name": "Dela Cruz",
        "license_number": "N01-123",
        "license_expiry": "2028-01-31",
    },
}


async def create(client, domain, data=None):
    response = await client.post(f"/api/v1/{domain}", json=data or DATA[domain])
    assert response.status_code == 201, response.text
    return response.json()


async def fleet(client):
    return {domain: await create(client, domain) for domain in DATA}


async def assign(client, rows):
    return await client.post(
        "/api/v1/vehicle-driver-assignments",
        json={"vehicle_id": rows["vehicles"]["id"], "driver_id": rows["drivers"]["id"]},
    )


@pytest.mark.parametrize("domain", DATA)
async def test_crud_search_sort_pagination_validation_audit(client, domain):
    await login(client)
    row = await create(client, domain)
    path = f"/api/v1/{domain}/{row['id']}"
    assert (await client.get(path)).json()["id"] == row["id"]
    changed = {**DATA[domain], "notes": "Updated safely"}
    assert (await client.patch(path, json=changed)).json()["notes"] == "Updated safely"
    listing = (
        await client.get(
            f"/api/v1/{domain}?search={list(DATA[domain].values())[0]}&limit=1&sort=created_at&direction=asc"
        )
    ).json()
    assert listing["total"] == 1 and len(listing["items"]) == 1
    assert (await client.get(f"/api/v1/{domain}?offset=1&limit=1")).json()["items"] == []
    assert (await client.get(f"/api/v1/{domain}?search=NO-MATCH")).json()["total"] == 0
    assert (await client.post(f"/api/v1/{domain}", json=DATA[domain])).status_code == 409
    assert (await client.post(f"/api/v1/{domain}", json={})).status_code == 422
    for extra in (
        {"organization_id": str(uuid.uuid4())},
        {"created_by": str(uuid.uuid4())},
        {"id": str(uuid.uuid4())},
        {"status": "IN_TRANSIT"},
    ):
        assert (await client.patch(path, json={**DATA[domain], **extra})).status_code == 422
    assert (await client.get(f"/api/v1/{domain}?sort=id;DROP%20TABLE%20users")).status_code == 422
    assert (await client.get(f"/api/v1/{domain}?limit=0")).status_code == 422
    assert (await client.get(f"/api/v1/{domain}?status=BOGUS")).status_code == 422
    assert (await client.post(path + "/deactivate")).status_code == 200
    assert (await client.get(f"/api/v1/{domain}?status=INACTIVE")).json()["total"] == 1
    assert (await client.post(path + "/reactivate")).status_code == 200
    assert (await client.delete(path)).status_code == 405
    events = (await client.get("/api/v1/audit-logs")).json()
    singular = {"customers": "customer", "vehicles": "vehicle", "drivers": "driver"}[domain]
    assert {
        f"{singular}.{event}" for event in ("created", "updated", "deactivated", "reactivated")
    } <= {e["action"] for e in events}


async def test_golden_workflow_and_assignment_history(client):
    # Fixture provisions both organizations and their owners; all domain work goes through authenticated API.
    await login(client)
    rows = await fleet(client)
    assert rows["drivers"]["user_id"] is None
    assert rows["drivers"]["license_expiry"] == "2028-01-31"
    response = await assign(client, rows)
    assert response.status_code == 201, response.text
    assignment = response.json()
    assert assignment["driver_name"] == "Juan Dela Cruz"
    assert (await assign(client, rows)).status_code == 409
    for domain in ("vehicles", "drivers"):
        assert (
            await client.post(f"/api/v1/{domain}/{rows[domain]['id']}/deactivate")
        ).status_code == 409
    leave = {**DATA["drivers"], "employment_status": "ON_LEAVE"}
    assert (
        await client.patch(f"/api/v1/drivers/{rows['drivers']['id']}", json=leave)
    ).status_code == 409
    await client.post("/api/v1/auth/logout")
    await login(client)  # New session/transaction confirms persistence.
    assert (await client.get("/api/v1/vehicles?search=TRK-001")).json()["total"] == 1
    for domain, key in (("vehicles", "vehicle_id"), ("drivers", "driver_id")):
        found = (
            await client.get(
                f"/api/v1/vehicle-driver-assignments?{key}={rows[domain]['id']}&is_current=true"
            )
        ).json()
        assert found["items"][0]["id"] == assignment["id"]
    path = f"/api/v1/vehicle-driver-assignments/{assignment['id']}"
    ended = await client.post(path + "/unassign")
    assert ended.status_code == 200, ended.text
    assert ended.json()["unassigned_at"] and not ended.json()["is_current"]
    assert (await client.post(path + "/unassign")).status_code == 409
    assert (await client.get(path)).json()["id"] == assignment["id"]
    assert (await client.get("/api/v1/vehicle-driver-assignments?is_current=false")).json()[
        "total"
    ] == 1
    assert (await client.get(f"/api/v1/vehicles/{rows['vehicles']['id']}")).json()[
        "status"
    ] == "AVAILABLE"
    assert (await client.get(f"/api/v1/drivers/{rows['drivers']['id']}")).json()[
        "operational_status"
    ] == "UNASSIGNED"
    events = (await client.get("/api/v1/audit-logs")).json()
    assert {"driver.assigned_to_vehicle", "driver.unassigned_from_vehicle"} <= {
        e["action"] for e in events
    }
    await client.post("/api/v1/auth/logout")
    await login(client, "other-owner@example.com")
    for domain, row in rows.items():
        assert (await client.get(f"/api/v1/{domain}/{row['id']}")).status_code == 404
        assert (await client.get(f"/api/v1/{domain}")).json()["total"] == 0
        assert (
            await client.get(f"/api/v1/{domain}?search={list(DATA[domain].values())[0]}")
        ).json()["total"] == 0
        assert (
            await client.patch(f"/api/v1/{domain}/{row['id']}", json=DATA[domain])
        ).status_code == 404
        assert (await client.post(f"/api/v1/{domain}/{row['id']}/deactivate")).status_code == 404
        assert (await client.post(f"/api/v1/{domain}/{row['id']}/reactivate")).status_code == 404
    assert (await client.get(path)).status_code == 404
    assert (await client.get("/api/v1/vehicle-driver-assignments?search=TRK-001")).json()[
        "total"
    ] == 0
    assert (await client.post(path + "/unassign")).status_code == 404
    assert (await assign(client, rows)).status_code == 404
    # Same codes may exist independently in tenant B.
    other = await fleet(client)
    assert (await assign(client, other)).status_code == 201
    mixed = {**other, "drivers": rows["drivers"]}
    assert (await assign(client, mixed)).status_code == 404


@pytest.mark.parametrize(
    "domain,change",
    [
        ("vehicles", {"plate_number": "OTHER"}),
        ("vehicles", {"unit_number": "OTHER"}),
        ("drivers", {"employee_number": "OTHER"}),
        ("drivers", {"license_number": "OTHER"}),
    ],
)
async def test_each_unique_constraint(client, domain, change):
    await login(client)
    await create(client, domain)
    assert (
        await client.post(f"/api/v1/{domain}", json={**DATA[domain], **change})
    ).status_code == 409


async def test_driver_boundary_linkage_and_self_projection(client):
    await login(client, "juan@example.com")
    user_id = (await client.get("/api/v1/me")).json()["user"]["id"]
    assert (await client.get("/api/v1/driver-profile")).json()["profile"] is None
    for domain in (*DATA, "vehicle-driver-assignments"):
        assert (await client.get(f"/api/v1/{domain}")).status_code == 403
        assert (await client.get(f"/api/v1/{domain}/{uuid.uuid4()}")).status_code == 403
    for domain in DATA:
        assert (await client.post(f"/api/v1/{domain}", json=DATA[domain])).status_code == 403
        assert (
            await client.patch(f"/api/v1/{domain}/{uuid.uuid4()}", json=DATA[domain])
        ).status_code == 403
        assert (await client.post(f"/api/v1/{domain}/{uuid.uuid4()}/deactivate")).status_code == 403
    assert (
        await client.post(
            "/api/v1/vehicle-driver-assignments",
            json={"vehicle_id": str(uuid.uuid4()), "driver_id": str(uuid.uuid4())},
        )
    ).status_code == 403
    await client.post("/api/v1/auth/logout")
    await login(client)
    rows = await fleet(client)
    linked = await client.patch(
        f"/api/v1/drivers/{rows['drivers']['id']}", json={**DATA["drivers"], "user_id": user_id}
    )
    assert linked.status_code == 200, linked.text
    assert (await assign(client, rows)).status_code == 201
    assert (await client.get("/api/v1/driver-profile")).status_code == 403
    assert (
        await client.post(
            "/api/v1/drivers",
            json={
                **DATA["drivers"],
                "employee_number": "DRV-002",
                "license_number": None,
                "user_id": user_id,
            },
        )
    ).status_code == 409
    assert (
        await client.post(
            "/api/v1/drivers",
            json={**DATA["drivers"], "employee_number": "DRV-003", "user_id": str(uuid.uuid4())},
        )
    ).status_code == 422
    await client.post("/api/v1/auth/logout")
    await login(client, "juan@example.com")
    own = (await client.get("/api/v1/driver-profile")).json()
    assert own["profile"]["employee_number"] == "DRV-001"
    assert own["assignment"]["unit_number"] == "TRK-001"
    assert "notes" not in own["profile"] and "driver_id" not in own["assignment"]


async def test_forced_rls_direct_sql_and_history_guard(client, admin_db):
    await login(client)
    identity_a = (await client.get("/api/v1/me")).json()
    rows_a = await fleet(client)
    assignment_a = (await assign(client, rows_a)).json()
    await client.post("/api/v1/auth/logout")
    await login(client, "other-owner@example.com")
    identity_b = (await client.get("/api/v1/me")).json()
    rows_b = await fleet(client)
    assignment_b = (await assign(client, rows_b)).json()
    tables = ("customers", "vehicles", "drivers", "vehicle_driver_assignments")
    async with Session() as db:
        for table in tables:
            assert await db.scalar(text(f"SELECT count(*) FROM {table}")) == 0
        await set_context(db, identity_b["user"]["id"], identity_b["organization"]["id"])
        for table in tables:
            assert await db.scalar(text(f"SELECT count(*) FROM {table}")) == 1
            foreign_id = (
                assignment_a["id"] if table == "vehicle_driver_assignments" else rows_a[table]["id"]
            )
            assert (
                await db.scalar(
                    text(f"SELECT count(*) FROM {table} WHERE id=:id"), {"id": foreign_id}
                )
                == 0
            )
            result = await db.execute(
                text(f"UPDATE {table} SET organization_id=organization_id WHERE id=:id"),
                {"id": foreign_id},
            )
            assert result.rowcount == 0
            assert (
                await db.execute(text(f"DELETE FROM {table} WHERE id=:id"), {"id": foreign_id})
            ).rowcount == 0
        await db.rollback()
    for statement, params in [
        (
            "UPDATE customers SET organization_id=:foreign WHERE id=:id",
            {"id": rows_b["customers"]["id"], "foreign": identity_a["organization"]["id"]},
        ),
        (
            "UPDATE vehicle_driver_assignments SET notes='tampered' WHERE id=:id",
            {"id": assignment_b["id"]},
        ),
        (
            "INSERT INTO vehicle_driver_assignments(id,organization_id,vehicle_id,driver_id,created_by,is_current,unassigned_at) VALUES(:id,:org,:vehicle,:driver,:actor,false,now())",
            {
                "id": str(uuid.uuid4()),
                "org": identity_b["organization"]["id"],
                "vehicle": rows_a["vehicles"]["id"],
                "driver": rows_b["drivers"]["id"],
                "actor": identity_b["user"]["id"],
            },
        ),
    ]:
        async with Session() as db:
            await set_context(db, identity_b["user"]["id"], identity_b["organization"]["id"])
            with pytest.raises(DBAPIError):
                await db.execute(text(statement), params)
            await db.rollback()
    policy_rows = (
        await admin_db.execute(
            text(
                "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = ANY(:tables)"
            ),
            {"tables": list(tables)},
        )
    ).all()
    assert len(policy_rows) == 4 and all(row[1] and row[2] for row in policy_rows)


@pytest.mark.parametrize(
    "role,allowed",
    [
        ("OWNER", True),
        ("ADMIN", True),
        ("MANAGER", True),
        ("DISPATCHER", False),
        ("ACCOUNTING", False),
        ("MAINTENANCE", False),
        ("DRIVER", False),
    ],
)
async def test_role_matrix_all_master_mutations(client, admin_db, role, allowed):
    await login(client)
    rows = await fleet(client)
    identity = (await client.get("/api/v1/me")).json()
    await admin_db.execute(
        text("UPDATE organization_memberships SET role=:role WHERE id=:id"),
        {"role": role, "id": identity["membership"]["id"]},
    )
    await admin_db.commit()
    for domain in DATA:
        path = f"/api/v1/{domain}/{rows[domain]['id']}"
        response = await client.patch(path, json={**DATA[domain], "notes": "role test"})
        assert response.status_code == (200 if allowed else 403)
        response = await client.post(path + "/deactivate")
        assert response.status_code == (200 if allowed else 403)
        response = await client.post(path + "/reactivate")
        assert response.status_code == (200 if allowed else 403)
    response = await assign(client, rows)
    assert response.status_code == (201 if allowed else 403)
    identifier = response.json()["id"] if allowed else str(uuid.uuid4())
    assert (
        await client.post(f"/api/v1/vehicle-driver-assignments/{identifier}/unassign")
    ).status_code == (200 if allowed else 403)


async def test_concurrent_assignment_and_distinct_current_constraints(client):
    await login(client)
    rows = await fleet(client)
    responses = await asyncio.gather(assign(client, rows), assign(client, rows))
    assert sorted(response.status_code for response in responses) == [201, 409]
    other_vehicle = await create(
        client,
        "vehicles",
        {**DATA["vehicles"], "unit_number": "TRK-002", "plate_number": "ABC-9999"},
    )
    other_driver = await create(
        client,
        "drivers",
        {**DATA["drivers"], "employee_number": "DRV-002", "license_number": "N02-234"},
    )
    assert (await assign(client, {**rows, "vehicles": other_vehicle})).status_code == 409
    assert (await assign(client, {**rows, "drivers": other_driver})).status_code == 409
    assignment = next(response.json() for response in responses if response.status_code == 201)
    assert (
        await client.post(f"/api/v1/vehicle-driver-assignments/{assignment['id']}/unassign")
    ).status_code == 200
    assert (await assign(client, rows)).status_code == 201
    assert (await client.get("/api/v1/vehicle-driver-assignments")).json()["total"] == 2


@pytest.mark.parametrize(
    "domain,extra",
    [
        ("vehicles", {"year": 1800}),
        ("vehicles", {"capacity": -1, "capacity_unit": "kg"}),
        ("vehicles", {"capacity": 10}),
        ("vehicles", {"odometer": -1}),
        ("vehicles", {"registration_expiry": "not-a-date"}),
        ("vehicles", {"status": "IN_TRANSIT"}),
        ("drivers", {"operational_status": "ASSIGNED"}),
        ("drivers", {"employment_status": "INACTIVE"}),
        ("drivers", {"license_expiry": "2027-02-30"}),
        ("customers", {"email": "invalid"}),
        ("customers", {"company_name": " "}),
        ("customers", {"phone": "not-a-phone"}),
    ],
)
async def test_server_validation(client, domain, extra):
    await login(client)
    assert (
        await client.post(f"/api/v1/{domain}", json={**DATA[domain], **extra})
    ).status_code == 422


async def test_restrictive_overrides_and_account_link_protection(client, admin_db):
    await login(client, "juan@example.com")
    driver_id = (await client.get("/api/v1/me")).json()["user"]["id"]
    await client.post("/api/v1/auth/logout")
    await login(client)
    identity = (await client.get("/api/v1/me")).json()
    await admin_db.execute(
        text(
            "UPDATE organization_memberships SET permissions_json='{"
            + '"deny":["vehicles.assign_driver","users.manage"]'
            + "}'::jsonb WHERE id=:id"
        ),
        {"id": identity["membership"]["id"]},
    )
    await admin_db.commit()
    rows = await fleet(client)
    assert (await assign(client, rows)).status_code == 403
    assert (
        await client.patch(
            f"/api/v1/drivers/{rows['drivers']['id']}",
            json={**DATA["drivers"], "user_id": driver_id},
        )
    ).status_code == 403


async def test_literal_search_and_cross_tenant_link(client):
    await login(client, "other-owner@example.com")
    foreign_user = (await client.get("/api/v1/me")).json()["user"]["id"]
    await client.post("/api/v1/auth/logout")
    await login(client)
    await fleet(client)
    for domain in DATA:
        for search in ("%", "_", "' OR 1=1 --"):
            assert (await client.get(f"/api/v1/{domain}", params={"search": search})).json()[
                "total"
            ] == 0
    assert (
        await client.post(
            "/api/v1/drivers",
            json={**DATA["drivers"], "employee_number": "OTHER", "user_id": foreign_user},
        )
    ).status_code == 422


async def test_database_active_cardinality_and_closed_history(client):
    await login(client)
    identity = (await client.get("/api/v1/me")).json()
    rows = await fleet(client)
    current = (await assign(client, rows)).json()
    vehicle = await create(
        client,
        "vehicles",
        {**DATA["vehicles"], "unit_number": "TRK-002", "plate_number": "XYZ-100"},
    )
    driver = await create(
        client, "drivers", {**DATA["drivers"], "employee_number": "DRV-002", "license_number": None}
    )
    for vehicle_id, driver_id in [
        (rows["vehicles"]["id"], driver["id"]),
        (vehicle["id"], rows["drivers"]["id"]),
    ]:
        async with Session() as db:
            await set_context(db, identity["user"]["id"], identity["organization"]["id"])
            with pytest.raises(DBAPIError, match="uq_current_"):
                await db.execute(
                    text(
                        "INSERT INTO vehicle_driver_assignments (id,organization_id,vehicle_id,driver_id,created_by,is_current) VALUES (:id,:org,:vehicle,:driver,:actor,true)"
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "org": identity["organization"]["id"],
                        "vehicle": vehicle_id,
                        "driver": driver_id,
                        "actor": identity["user"]["id"],
                    },
                )
            await db.rollback()
    await client.post(f"/api/v1/vehicle-driver-assignments/{current['id']}/unassign")
    async with Session() as db:
        await set_context(db, identity["user"]["id"], identity["organization"]["id"])
        with pytest.raises(DBAPIError, match="Only explicit unassignment"):
            await db.execute(
                text(
                    "UPDATE vehicle_driver_assignments SET is_current=true,unassigned_at=NULL WHERE id=:id"
                ),
                {"id": current["id"]},
            )
        await db.rollback()
    async with Session() as db:
        await set_context(db, identity["user"]["id"], identity["organization"]["id"])
        assert (
            await db.execute(
                text("DELETE FROM vehicle_driver_assignments WHERE id=:id"), {"id": current["id"]}
            )
        ).rowcount == 0
        await db.rollback()
