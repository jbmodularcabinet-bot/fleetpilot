# Maintenance schedules — Batch 11

Maintenance schedules belong to an organization and vehicle. The server accepts explicit ENGINE_OIL, OIL_FILTER, AIR_FILTER, FUEL_FILTER, BRAKES, TIRES, TRANSMISSION, COOLING_SYSTEM, BATTERY, GENERAL_INSPECTION, REGISTRATION_RELATED_CHECK and OTHER service types. OTHER requires descriptive notes. These labels do not certify regulatory compliance.

## Thresholds and trusted readings

ODOMETER requires a last-service decimal-string reading and an integer interval in km. DATE requires a calendar service date and interval in days. ODOMETER_OR_DATE requires both. Unused thresholds must be empty. Warnings cannot exceed their corresponding interval. The API rejects client-submitted next-due or status fields.

Trusted odometer = maximum of owner-maintained vehicle odometer, monotonic reviewed-fuel odometer and completed-maintenance odometer, treating absent readings as zero. Unreviewed driver fuel entries are not included. Maintenance completion cannot report a reading below that trusted maximum. This conservative floor does not automatically reconcile historical odometer errors.

For each configured threshold: before the warning boundary = OK; warning boundary inclusive until due = UPCOMING; equality with due = DUE; after due = OVERDUE. Combined schedules take the higher severity of the two results. Date comparisons use UTC calendar dates, not device clocks.

With last service 45,000 km, interval 5,000 and warning 1,000, due is 50,000: 48,000 and 48,900 are OK; 49,000 and 49,100 UPCOMING; 50,000 DUE; 50,100 OVERDUE. The prompt's earlier 48,900 UPCOMING example contradicts its warning distance and later precise test. The implementation follows the explicit 1,000 km boundary and documents that discrepancy.

2026-01-01 plus 180 days is 2026-06-30. With a fourteen-day warning, June 15 is OK, June 16 UPCOMING, June 30 DUE and July 1 OVERDUE.

## Service completion

The work-order completion transaction updates its linked schedule: completion odometer + km interval; server completion UTC date + day interval. Both are calculated for combined schedules. It preserves the completed work record and appends schedule/work-order events and audit. Example: 50,250 + 5,000 = 55,250 km.

Schedule metadata can be replaced through the strict authorized PUT endpoint, including deactivation. Changes are blocked while linked work is open. Historical completed work and events remain immutable. A disabled schedule cannot source new work. The owner UI provides creation; schedule update/deactivation is API-only in this batch.

## Access and queries

POST /api/v1/vehicles/{id}/maintenance-schedules; PUT /api/v1/maintenance/schedules/{id}; GET /api/v1/vehicles/{id}/maintenance; GET /api/v1/maintenance/schedules. Lists are tenant scoped, searchable and paginated (default 20, maximum 100). Vehicle overview retains the latest 100 work orders/defects; the maintenance list provides pagination. The attention union includes due/overdue active schedules, high/critical open work and unresolved critical defects. Upcoming is a separate schedule view. No predictive analytics.
