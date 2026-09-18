"""Private immutable object interface. Local implementation is development-only."""

import hashlib
import io
import re
import warnings
from collections.abc import Iterator
from pathlib import Path
from typing import Protocol

from fastapi import HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError

from .config import get_settings
from .delivery_policy import MAX_FILE_BYTES, MAX_IMAGE_PIXELS


class EvidenceStorage(Protocol):
    def put(self, key: str, data: bytes) -> None: ...
    def read(self, key: str) -> bytes: ...
    def discard_uncommitted(self, key: str) -> None: ...
    def head(self, key: str) -> int: ...
    def keys(self) -> Iterator[str]: ...
    def health_check(self) -> None: ...


class LocalEvidenceStorage:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def path(self, key: str) -> Path:
        if not re.fullmatch(r"[a-f0-9]{32}/[a-f0-9]{32}\.png", key):
            raise ValueError("Invalid private object key")
        result = (self.root / key).resolve()
        if not result.is_relative_to(self.root):
            raise ValueError("Invalid private object location")
        return result

    def put(self, key: str, data: bytes) -> None:
        target = self.path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:  # Never overwrite a submitted object.
            stream.write(data)

    def read(self, key: str) -> bytes:
        with self.path(key).open("rb") as stream:
            data = stream.read(MAX_FILE_BYTES + 1)
        if len(data) > MAX_FILE_BYTES:
            raise ValueError("Stored evidence exceeds size limit")
        return data

    def discard_uncommitted(self, key: str) -> None:
        self.path(key).unlink(missing_ok=True)

    def head(self, key: str) -> int:
        return self.path(key).stat().st_size

    def keys(self) -> Iterator[str]:
        for path in self.root.glob("*/*.png"):
            key = path.relative_to(self.root).as_posix()
            self.path(key)
            yield key

    def health_check(self) -> None:
        import uuid

        key = f"{'0' * 32}/{uuid.uuid4().hex}.png"
        try:
            self.put(key, b"fleetpilot-storage-probe")
            if self.read(key) != b"fleetpilot-storage-probe":
                raise OSError("Storage probe mismatch")
        finally:
            self.discard_uncommitted(key)


def storage() -> EvidenceStorage:
    settings = get_settings()
    if settings.storage_backend == "s3":
        from .s3_storage import S3EvidenceStorage

        return S3EvidenceStorage(settings)
    if settings.environment == "production":
        raise HTTPException(503, "Production evidence storage is not configured.")
    root = (
        Path(settings.evidence_storage_root)
        if settings.evidence_storage_root
        else (Path(__file__).resolve().parents[3] / ".runtime" / f"evidence-{settings.environment}")
    )
    return LocalEvidenceStorage(root)


def validate_image(data: bytes, filename: str, content_type: str) -> tuple[bytes, str]:
    allowed = {
        "image/jpeg": ("JPEG", {".jpg", ".jpeg"}),
        "image/png": ("PNG", {".png"}),
        "image/webp": ("WEBP", {".webp"}),
    }
    if not data or len(data) > MAX_FILE_BYTES:
        raise HTTPException(413 if data else 422, "Provide a nonempty image no larger than 5 MiB.")
    if (
        not filename
        or len(filename) > 160
        or any(c in filename for c in "/\\:\x00\r\n")
        or content_type not in allowed
        or Path(filename).suffix.lower() not in allowed[content_type][1]
    ):
        raise HTTPException(
            422, "Use a JPEG, PNG or WebP image with a matching filename and content type."
        )
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data), formats=["JPEG", "PNG", "WEBP"]) as candidate:
                if (
                    candidate.format != allowed[content_type][0]
                    or candidate.width * candidate.height > MAX_IMAGE_PIXELS
                    or getattr(candidate, "n_frames", 1) != 1
                ):
                    raise ValueError("Unsupported image dimensions or animation")
                candidate.verify()
            with Image.open(io.BytesIO(data), formats=["JPEG", "PNG", "WEBP"]) as candidate:
                candidate.load()
                oriented = ImageOps.exif_transpose(candidate).convert("RGBA")
                # Reconstruct pixels into a clean image: no EXIF/GPS, comments or appended payloads.
                clean = Image.frombytes("RGBA", oriented.size, oriented.tobytes())
                output = io.BytesIO()
                clean.save(output, format="PNG")
                normalized = output.getvalue()
                if len(normalized) > MAX_FILE_BYTES:
                    raise ValueError("Decoded image exceeds storage limit")
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        SyntaxError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise HTTPException(
            422, "Invalid image. Use a single-frame image up to 16 megapixels and 5 MiB."
        ) from exc
    return normalized, hashlib.sha256(normalized).hexdigest()
