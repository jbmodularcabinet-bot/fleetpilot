export type Domain = "customers" | "vehicles" | "drivers";
export interface MasterRecord {
  id: string;
  [key: string]: string | number | null;
}
export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}
export interface Assignment {
  id: string;
  vehicle_id: string;
  driver_id: string;
  unit_number: string;
  driver_name: string;
  is_current: boolean;
  assigned_at: string;
  unassigned_at: string | null;
  notes: string | null;
}
export interface Field {
  key: string;
  label: string;
  required?: boolean;
  type?: "email" | "tel" | "date" | "number" | "textarea";
  max?: number;
  min?: number;
  step?: string;
  options?: string[];
  pattern?: string;
}
const codePattern = "[A-Za-z0-9][A-Za-z0-9 -]*";
const contact: Field[] = [
  {
    key: "phone",
    label: "Phone",
    type: "tel",
    max: 30,
    pattern: "[+0-9() .-]{3,30}",
  },
  { key: "email", label: "Email", type: "email", max: 320 },
];
const notes: Field = {
  key: "notes",
  label: "Notes",
  type: "textarea",
  max: 4000,
};
export const config: Record<
  Domain,
  {
    title: string;
    singular: string;
    path: string;
    description: string;
    statusKey: string;
    statuses: string[];
    columns: string[];
    sort: string[];
    fields: Field[];
  }
> = {
  customers: {
    title: "Customers",
    singular: "customer",
    path: "/customers",
    description: "The people and businesses your fleet serves.",
    statusKey: "status",
    statuses: ["ACTIVE", "INACTIVE"],
    columns: ["customer_code", "company_name", "contact_person", "status"],
    sort: ["created_at", "company_name", "customer_code", "status"],
    fields: [
      {
        key: "customer_code",
        label: "Customer code",
        required: true,
        max: 40,
        pattern: codePattern,
      },
      {
        key: "company_name",
        label: "Company name",
        required: true,
        min: 2,
        max: 160,
      },
      { key: "contact_person", label: "Contact person", max: 120 },
      ...contact,
      { key: "payment_terms", label: "Payment terms", max: 120 },
      {
        key: "billing_address",
        label: "Billing address",
        type: "textarea",
        max: 4000,
      },
      {
        key: "pickup_notes",
        label: "Pickup notes",
        type: "textarea",
        max: 4000,
      },
      {
        key: "delivery_notes",
        label: "Delivery notes",
        type: "textarea",
        max: 4000,
      },
      notes,
    ],
  },
  vehicles: {
    title: "Vehicles",
    singular: "vehicle",
    path: "/fleet/vehicles",
    description:
      "Keep your vehicle records and driver assignments in one place.",
    statusKey: "status",
    statuses: ["AVAILABLE", "ASSIGNED", "MAINTENANCE", "INACTIVE"],
    columns: ["unit_number", "plate_number", "vehicle_type", "status"],
    sort: [
      "created_at",
      "unit_number",
      "plate_number",
      "status",
      "registration_expiry",
    ],
    fields: [
      {
        key: "unit_number",
        label: "Unit number",
        required: true,
        max: 40,
        pattern: codePattern,
      },
      {
        key: "plate_number",
        label: "Plate number",
        required: true,
        min: 2,
        max: 30,
        pattern: codePattern,
      },
      {
        key: "vehicle_type",
        label: "Vehicle type",
        required: true,
        min: 2,
        max: 80,
      },
      { key: "make", label: "Make", max: 80 },
      { key: "model", label: "Model", max: 80 },
      { key: "year", label: "Year", type: "number", min: 1900, max: 2100 },
      {
        key: "capacity",
        label: "Capacity",
        type: "number",
        min: 0,
        step: "0.001",
      },
      {
        key: "capacity_unit",
        label: "Capacity unit",
        options: ["kg", "tonnes", "m3", "pallets"],
      },
      {
        key: "odometer",
        label: "Odometer (km)",
        type: "number",
        min: 0,
        step: "0.1",
      },
      {
        key: "registration_expiry",
        label: "Registration expiry",
        type: "date",
      },
      notes,
    ],
  },
  drivers: {
    title: "Drivers",
    singular: "driver",
    path: "/fleet/drivers",
    description: "Manage your team, with or without a FleetPilot login.",
    statusKey: "employment_status",
    statuses: ["ACTIVE", "ON_LEAVE", "SUSPENDED", "INACTIVE"],
    columns: [
      "employee_number",
      "first_name",
      "last_name",
      "employment_status",
    ],
    sort: [
      "created_at",
      "employee_number",
      "last_name",
      "employment_status",
      "license_expiry",
    ],
    fields: [
      {
        key: "employee_number",
        label: "Employee number",
        required: true,
        max: 40,
        pattern: codePattern,
      },
      { key: "first_name", label: "First name", required: true, max: 80 },
      { key: "last_name", label: "Last name", required: true, max: 80 },
      ...contact,
      {
        key: "license_number",
        label: "License number",
        max: 40,
        pattern: codePattern,
      },
      { key: "license_type", label: "License type", max: 80 },
      { key: "license_expiry", label: "License expiry", type: "date" },
      {
        key: "employment_status",
        label: "Employment status",
        required: true,
        options: ["ACTIVE", "ON_LEAVE", "SUSPENDED"],
      },
      {
        key: "emergency_contact_name",
        label: "Emergency contact name",
        max: 120,
      },
      {
        key: "emergency_contact_phone",
        label: "Emergency contact phone",
        type: "tel",
        max: 30,
        pattern: "[+0-9() .-]{3,30}",
      },
      notes,
    ],
  },
};
export function labelFor(key: string) {
  return key.replaceAll("_", " ").replace(/^./, (value) => value.toUpperCase());
}
export function recordName(domain: Domain, row: MasterRecord) {
  return domain === "customers"
    ? String(row.company_name)
    : domain === "vehicles"
      ? String(row.unit_number)
      : `${row.first_name} ${row.last_name}`;
}
export function formPayload(domain: Domain, values: Record<string, string>) {
  return Object.fromEntries(
    config[domain].fields.map((field) => [
      field.key,
      values[field.key]?.trim()
        ? field.type === "number"
          ? Number(values[field.key])
          : values[field.key].trim()
        : null,
    ]),
  );
}
