# Proof of delivery — Batch 5

Organization → Trip → numbered DeliveryAttempt → ProofOfDelivery and DeliveryEvidence.

## Minimum policy

The centralized `delivery_policy.py` requires a recipient name, explicit driver confirmation, server delivery timestamp and at least one active delivery photo. Recipient role and notes are optional. Signature is optional; a supplied signature requires explicit recipient confirmation. There is no recipient-unavailable success alternative.

POD may be submitted only after UNLOADING_COMPLETED. Submission atomically closes the attempt as DELIVERED, creates POD, transitions the trip, and records milestone/audits. Ordinary bare delivery transitions fail. Duplicate submissions conflict; completed trips cannot be changed through POD endpoints.

## Evidence authorization and validation

Metadata and file retrieval require authenticated tenant context, permission and trip access. A driver must be linked to the trip's current assigned driver. Known evidence UUIDs grant no access. Forced PostgreSQL RLS and composite ownership constraints protect all four new tables. Storage keys never appear in client metadata or audits.

JPEG, PNG and WebP must have matching extension, MIME and decoded format. Limits: nonempty, 5 MiB incoming/stored, 16 million pixels, one frame, 12 retained files per attempt. Pixel-only PNG re-encoding strips embedded metadata and appended content. Retrieval verifies SHA-256 and uses private/no-store, nosniff and sandbox headers. Files are never publicly mounted.

Private local development storage implements a provider interface. Production object storage is **NOT CONFIGURED / UNVERIFIED** and production file operations fail closed.

## Signature and immutability

The driver form supports touch/mouse signature drawing, clearing before upload and explicit confirmation. Signatures receive the same private storage and authorization as photos; they are operational evidence without a legal non-repudiation claim.

Open-attempt replacement marks the original evidence SUPERSEDED and retains its metadata and bytes. Submitted evidence and terminal attempts cannot be silently overwritten or deleted. Owner review changes only review state, reviewer and timestamp, with an audit record.

## Driver and owner workflow

The assigned driver completes unloading, opens Confirm delivery, enters recipient details, selects photo(s), optionally captures a signature, attests delivery and submits while online. The form exposes saving and error states; an interrupted submission retains successfully uploaded evidence on its open attempt for retry.

Owner Trip Detail displays attempt history, recipient, notes, photos, signature, actors and timestamps. An authorized operator reviews POD before closing a new trip. DELIVERED means operational delivery with minimum POD; COMPLETED means reviewed operational closeout. Neither means paid invoice or recognized revenue. Historical pre-migration terminal trips retain their legacy status without fabricated evidence.

See [DELIVERY-EVIDENCE.md](DELIVERY-EVIDENCE.md) for API, transaction/storage boundaries and exact production limitations, and [DELIVERY-EXCEPTIONS.md](DELIVERY-EXCEPTIONS.md) for failed attempts and retries.
