export interface TripRecord {
  id: string;
  trip_number: string;
  version: number;
  customer_id: string;
  vehicle_id: string | null;
  driver_id: string | null;
  customer_name: string;
  vehicle_unit: string | null;
  driver_name: string | null;
  current_status: string;
  current_milestone: string;
  pickup_name: string;
  pickup_address: string;
  delivery_name: string;
  delivery_address: string;
  scheduled_pickup_at: string;
  scheduled_delivery_at: string | null;
  next_action: string | null;
  next_action_label: string | null;
  dispatcher_notes: string | null;
  special_instructions: string | null;
  completed_at: string | null;
  cancellation_reason: string | null;
  pod_required: boolean;
  pod_status: string | null;
  [key: string]: string | number | boolean | null;
}
export interface Milestone {
  id: string;
  event_number: number;
  milestone_type: string;
  occurred_at: string;
  recorded_at: string;
  source: string;
  notes?: string | null;
  recorded_by?: string;
}
export const tripStatuses = [
  "SCHEDULED",
  "DISPATCHED",
  "PICKUP",
  "LOADED",
  "IN_TRANSIT",
  "DELIVERED",
  "COMPLETED",
  "CANCELLED",
];
export const human = (value: string) =>
  value
    .toLowerCase()
    .replaceAll("_", " ")
    .replace(/^./, (letter) => letter.toUpperCase());
export const dateLabel = (value: unknown) =>
  value ? new Date(String(value)).toLocaleString() : "Not specified";
export interface TripField {
  key: string;
  label: string;
  required?: boolean;
  type?: "text" | "textarea" | "datetime-local" | "number" | "tel";
  max?: number;
  min?: number;
  step?: string;
  options?: string[];
}
export const tripFields: TripField[] = [
  { key: "pickup_name", label: "Pickup name", required: true, max: 160 },
  {
    key: "pickup_address",
    label: "Pickup address",
    required: true,
    type: "textarea",
    max: 2000,
  },
  { key: "pickup_contact_name", label: "Pickup contact name", max: 120 },
  {
    key: "pickup_contact_phone",
    label: "Pickup contact phone",
    type: "tel",
    max: 30,
  },
  { key: "delivery_name", label: "Delivery name", required: true, max: 160 },
  {
    key: "delivery_address",
    label: "Delivery address",
    required: true,
    type: "textarea",
    max: 2000,
  },
  { key: "delivery_contact_name", label: "Delivery contact name", max: 120 },
  {
    key: "delivery_contact_phone",
    label: "Delivery contact phone",
    type: "tel",
    max: 30,
  },
  {
    key: "scheduled_pickup_at",
    label: "Scheduled pickup",
    required: true,
    type: "datetime-local",
  },
  {
    key: "scheduled_delivery_at",
    label: "Scheduled delivery",
    type: "datetime-local",
  },
  { key: "reference_number", label: "Reference number", max: 120 },
  { key: "customer_reference", label: "Customer reference", max: 120 },
  {
    key: "cargo_description",
    label: "Cargo description",
    type: "textarea",
    max: 4000,
  },
  {
    key: "cargo_weight",
    label: "Cargo weight",
    type: "number",
    min: 0,
    step: "0.001",
  },
  {
    key: "cargo_weight_unit",
    label: "Cargo weight unit",
    options: ["kg", "tonnes"],
  },
  {
    key: "special_instructions",
    label: "Special instructions",
    type: "textarea",
    max: 4000,
  },
  {
    key: "dispatcher_notes",
    label: "Operator notes",
    type: "textarea",
    max: 4000,
  },
  ...(["pickup", "delivery"] as const).flatMap((prefix) => [
    {
      key: `${prefix}_latitude`,
      label: `${human(prefix)} latitude (optional)`,
      type: "number" as const,
      min: -90,
      max: 90,
      step: "0.000001",
    },
    {
      key: `${prefix}_longitude`,
      label: `${human(prefix)} longitude (optional)`,
      type: "number" as const,
      min: -180,
      max: 180,
      step: "0.000001",
    },
  ]),
];
export function localInput(value: unknown) {
  if (!value) return "";
  const d = new Date(String(value));
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16);
}
export function tripPayload(values: Record<string, string>) {
  return Object.fromEntries(
    tripFields.map((field) => {
      const value = values[field.key]?.trim();
      return [
        field.key,
        !value
          ? null
          : field.type === "number"
            ? Number(value)
            : field.type === "datetime-local"
              ? new Date(value).toISOString()
              : value,
      ];
    }),
  );
}
