"""Private S3 adapter. Clients never receive object keys or provider URLs."""

import hashlib
import json
import re
import uuid
from collections.abc import Iterator

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from .delivery_policy import MAX_FILE_BYTES


class StorageUnavailable(OSError):
    pass


class S3EvidenceStorage:
    def __init__(self, settings):
        self.bucket = settings.s3_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint,
            region_name=settings.s3_region,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            config=Config(
                signature_version="s3v4",
                connect_timeout=3,
                read_timeout=5,
                retries={"total_max_attempts": 2, "mode": "standard"},
                s3={"addressing_style": "path"},
            ),
        )

    @staticmethod
    def validate_key(key):
        if not re.fullmatch(r"[a-f0-9]{32}/[a-f0-9]{32}\.png", key):
            raise ValueError("Invalid private object key")

    def call(self, operation, key=None, **kwargs):
        if key is not None:
            self.validate_key(key)
            kwargs["Key"] = key
        try:
            return getattr(self.client, operation)(Bucket=self.bucket, **kwargs)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code in {"NoSuchKey", "NotFound", "404"}:
                raise FileNotFoundError("Evidence object missing") from None
            if code in {"PreconditionFailed", "412", "ConditionalRequestConflict"}:
                raise FileExistsError("Evidence object already exists") from None
            raise StorageUnavailable("Private storage unavailable") from None
        except BotoCoreError:
            raise StorageUnavailable("Private storage unavailable") from None

    def put(self, key: str, data: bytes) -> None:
        if len(data) > MAX_FILE_BYTES:
            raise ValueError("Object exceeds evidence size limit")
        self.call(
            "put_object",
            key,
            Body=data,
            ContentType="image/png",
            IfNoneMatch="*",
            Metadata={"sha256": hashlib.sha256(data).hexdigest()},
        )

    def read(self, key: str) -> bytes:
        result = self.call("get_object", key)
        stream = result["Body"]
        try:
            if result["ContentLength"] > MAX_FILE_BYTES:
                raise StorageUnavailable("Evidence object exceeds size limit")
            data = stream.read(MAX_FILE_BYTES + 1)
            if len(data) > MAX_FILE_BYTES or len(data) != result["ContentLength"]:
                raise StorageUnavailable("Incomplete evidence object")
            return data
        except BotoCoreError:
            raise StorageUnavailable("Private storage unavailable") from None
        finally:
            stream.close()

    def head(self, key: str) -> int:
        return self.call("head_object", key)["ContentLength"]

    def discard_uncommitted(self, key: str) -> None:
        self.call("delete_object", key)

    def keys(self) -> Iterator[str]:
        token = None
        while True:
            result = self.call("list_objects_v2", **({"ContinuationToken": token} if token else {}))
            for item in result.get("Contents", []):
                self.validate_key(item["Key"])
                yield item["Key"]
            if not result.get("IsTruncated"):
                return
            token = result["NextContinuationToken"]

    def health_check(self) -> None:
        self.call("head_bucket")
        acl = self.call("get_bucket_acl")
        if any(
            grant.get("Grantee", {}).get("URI", "").endswith(("/AllUsers", "/AuthenticatedUsers"))
            for grant in acl.get("Grants", [])
        ):
            raise StorageUnavailable("Bucket must be private")
        try:
            policy = self.client.get_bucket_policy(Bucket=self.bucket)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") != "NoSuchBucketPolicy":
                raise StorageUnavailable("Unable to verify bucket privacy") from None
        except BotoCoreError:
            raise StorageUnavailable("Unable to verify bucket privacy") from None
        else:
            for statement in json.loads(policy["Policy"]).get("Statement", []):
                principal = statement.get("Principal")
                if statement.get("Effect") == "Allow" and (
                    principal == "*"
                    or (isinstance(principal, dict) and "*" in str(principal.get("AWS", "")))
                ):
                    raise StorageUnavailable("Public bucket policies are prohibited")
        key = f"{'0' * 32}/{uuid.uuid4().hex}.png"
        try:
            self.put(key, b"fleetpilot-storage-probe")
            if self.read(key) != b"fleetpilot-storage-probe":
                raise StorageUnavailable("Storage probe mismatch")
        finally:
            self.discard_uncommitted(key)
