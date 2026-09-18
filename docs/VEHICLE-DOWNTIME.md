# Vehicle downtime and dispatch safety — Batch 11

Downtime is explicit on each maintenance work order: requires_vehicle_downtime plus downtime_started_at and downtime_ended_at. It is not retrospectively inferred from all inspection timestamps. Overlapping work orders retain separate intervals; no summed fleet utilization metric is fabricated.

Starting a downtime work order sets MAINTENANCE unless the vehicle is already INACTIVE. An inspection without downtime leaves availability unchanged. A vehicle with any operational trip beyond SCHEDULED and before COMPLETED/CANCELLED cannot start downtime: the owner must close or validly reassign that trip first. This includes delivered but not yet closed trips. Scheduled trips may remain, but dispatch will be blocked.

Existing trip create/assignment/dispatch checks reject INACTIVE and MAINTENANCE. Database triggers also reject unavailable assignment/dispatch and prevent an active maintenance blocker from being cleared through a direct vehicle update. Master-data unassignment preserves MAINTENANCE. Reactivation is rejected while downtime work remains active.

Completing work sets its end time, advances the trusted maintenance reading and checks all other IN_PROGRESS downtime work orders. If any remain, the vehicle stays MAINTENANCE. Otherwise it returns to ASSIGNED if a current fleet assignment exists, or AVAILABLE if none exists. INACTIVE remains INACTIVE. The ordinary completion API cannot blindly restore availability.

Cancellation is allowed only before IN_PROGRESS and has no downtime effect. Active cancellation/reopen/correction is deferred, preventing ambiguous availability restoration. Vehicle/work updates, events and audit share the same transaction and organization write lock. Database triggers provide defense in depth; application permissions remain necessary.

Tests cover two simultaneous blockers, inactive preservation, unassignment safety, trip cost separation, rejection of new assignment and scheduled dispatch, active-trip start blocking, non-downtime inspection, completion odometer floor and direct PostgreSQL availability tampering.
