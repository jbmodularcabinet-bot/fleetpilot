# FleetPilot locked visual references

Status: **LOCKED v1**, at the user's request. Six supplied JPEG originals are saved without cropping, recompression, redrawing or alteration. They are repository source references, outside the public web directory.

| ID | Original | Saved reference | Role |
| --- | --- | --- | --- |
| FP-REF-01 | Photo 1.jpg | [Brand identity](v1/01-brand-identity.jpg) | Primary brand system |
| FP-REF-02 | Photo 2.jpg | [Owner dashboard](v1/02-owner-dashboard.jpg) | Owner composition and responsive direction |
| FP-REF-03 | Photo 3.jpg | [Product board A](v1/03-product-design-board-a.jpg) | UI rules and product screen references |
| FP-REF-04 | Photo 4.jpg | [Driver app](v1/04-driver-app.jpg) | Primary driver visual reference |
| FP-REF-05 | Photo 5.jpg | [Product board B](v1/05-product-design-board-b.jpg) | Companion to Photo 3, separately retained |
| FP-REF-06 | Photo 6.jpg | [Dark profitability concept](v1/06-dark-profitability-concept.jpg) | Alternate concept, not a replacement brand |

[manifest.json](v1/manifest.json) records original names, dimensions, byte sizes, roles and SHA-256 checksums. Photos 3 and 5 have the same visible composition but different bytes/hashes; neither is discarded as a duplicate.

## Lock policy

- Preserve v1 originals byte-for-byte. Current local JPEG files have the Windows read-only attribute.
- Do not overwrite v1, regenerate the logo, or promote the alternate concept into the primary visual system without an explicit user-approved revision.
- Save authorized changes as a new version with a new manifest and an explanation of supersession. Derivative/export assets belong in a separate location and must identify their source.
- Checksums detect changes relative to this manifest; read-only flags discourage accidental edits. Neither is tamper-proof access control, and Git does not preserve Windows read-only attributes across checkouts. This save does not create a Git commit or remote backup.
- No feature depicted in these boards becomes authorized or implemented by locking the artwork. Existing functional scope and verified lifecycle/security rules remain authoritative.

Verify locally from the repository root:

```powershell
.venv/Scripts/python.exe scripts/verify-design-assets.py
```

Analysis and interpretation: [DESIGN-ASSET-LOCK.md](../../docs/DESIGN-ASSET-LOCK.md). Existing implementation reference: [DESIGN-SYSTEM.md](../../docs/DESIGN-SYSTEM.md).
