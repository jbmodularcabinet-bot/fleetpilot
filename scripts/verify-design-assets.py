"""Verify the locked FleetPilot reference originals without modifying them."""

import hashlib
import json
import stat
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1] / "assets/design-references/v1"
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "LOCKED_REFERENCE_BASELINE"
    assert len(manifest["assets"]) == 6
    seen = set()
    for asset in manifest["assets"]:
        path = (root / asset["file"]).resolve()
        assert path.parent == root.resolve(), "Asset must remain inside the version directory"
        assert path.name not in seen, "Duplicate asset entry"
        seen.add(path.name)
        data = path.read_bytes()
        assert len(data) == asset["bytes"], f"Size changed: {path.name}"
        assert hashlib.sha256(data).hexdigest() == asset["sha256"], f"Hash changed: {path.name}"
        attributes = getattr(path.stat(), "st_file_attributes", None)
        if attributes is not None:
            assert attributes & stat.FILE_ATTRIBUTE_READONLY, f"Read-only flag missing: {path.name}"
        print(f"PASS {asset['id']} {path.name}")
    print("6/6 locked originals verified; manifest hashes and sizes match.")


if __name__ == "__main__":
    main()
