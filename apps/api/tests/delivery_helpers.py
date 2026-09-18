import io

from PIL import Image


def image_bytes(format="PNG", color="green"):
    buffer = io.BytesIO()
    Image.new("RGB", (64, 48), color).save(buffer, format=format)
    return buffer.getvalue()


async def upload(client, attempt, version, kind="DELIVERY_PHOTO", **extra):
    response = await client.post(
        f"/api/v1/delivery-attempts/{attempt}/evidence",
        params={
            "expected_version": version,
            "evidence_type": kind,
            "filename": "evidence.png",
            **extra,
        },
        content=image_bytes(),
        headers={"Content-Type": "image/png"},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def submit_delivery(client, trip, review=False):
    result = await client.post(
        f"/api/v1/trips/{trip['id']}/delivery-attempts", json={"expected_version": trip["version"]}
    )
    assert result.status_code == 201, result.text
    attempt = result.json()
    evidence = await upload(client, attempt["attempt"]["id"], attempt["trip_version"])
    result = await client.post(
        f"/api/v1/delivery-attempts/{attempt['attempt']['id']}/pod",
        json={
            "expected_version": evidence["trip_version"],
            "recipient_name": "Maria Santos",
            "recipient_role": "Receiving Staff",
            "driver_confirmed": True,
            "notes": "Cargo received in good condition.",
        },
    )
    assert result.status_code == 201, result.text
    data = result.json()
    if review:
        return await review_delivery(client, data["trip"])
    return data["trip"]


async def review_delivery(client, trip):
    history = (await client.get(f"/api/v1/trips/{trip['id']}/delivery-attempts")).json()
    pod = history["items"][0]["pod"]
    result = await client.post(
        f"/api/v1/pod/{pod['id']}/review", json={"expected_version": trip["version"]}
    )
    assert result.status_code == 200, result.text
    return (await client.get(f"/api/v1/trips/{trip['id']}")).json()
