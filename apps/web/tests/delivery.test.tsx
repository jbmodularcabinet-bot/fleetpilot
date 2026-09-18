import React from "react";
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import {
  DeliveryPanel,
  EvidencePreview,
  SignatureCapture,
} from "../src/components/delivery";
import type { Identity } from "@fleetpilot/types";
import type { TripRecord } from "../src/lib/trips";
import { request } from "../src/lib/client";
vi.mock("../src/lib/client", () => ({ request: vi.fn() }));
const identity = {
  permissions: [
    "driver_pod.read_own",
    "driver_pod.submit_own",
    "driver_evidence.upload_own",
    "driver_exception.create_own",
  ],
} as Identity;
const trip = {
  id: "test-trip",
  version: 1,
  current_status: "IN_TRANSIT",
  current_milestone: "UNLOADING_COMPLETED",
} as TripRecord;
const history = {
  items: [],
  total: 0,
  offset: 0,
  limit: 20,
  trip_version: 1,
  legacy_delivery: false,
  policy: {
    signature_required: false,
    minimum_delivery_photos: 1,
    max_file_bytes: 5242880,
    max_attempt_files: 12,
  },
};
describe("delivery evidence UI boundaries", () => {
  it("shows a protected image failure and retries through the same authorized API", () => {
    render(
      <EvidencePreview
        evidence={{
          id: "private-id",
          evidence_type: "DELIVERY_PHOTO",
          original_filename: "photo.png",
          status: "ACTIVE",
          uploaded_at: "2030-01-01T00:00:00Z",
          uploaded_by: "driver",
          file_size: 100,
          supersedes_id: null,
        }}
      />,
    );
    fireEvent.error(screen.getByRole("img"));
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Evidence image is unavailable",
    );
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry image" }));
    expect(screen.getByRole("img")).toHaveAttribute(
      "src",
      "/api/v1/evidence/private-id?retry=1",
    );
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
  it("shows an evidence load failure without exposing submission controls", async () => {
    vi.mocked(request).mockRejectedValue(
      new Error("Evidence service unavailable"),
    );
    render(
      <DeliveryPanel trip={trip} identity={identity} own onChanged={vi.fn()} />,
    );
    await screen.findByText("Evidence service unavailable");
    expect(
      screen.queryByRole("button", { name: "Submit proof of delivery" }),
    ).not.toBeInTheDocument();
  });
  it("cannot confirm an empty signature", () => {
    render(<SignatureCapture onChange={vi.fn()} />);
    expect(
      screen.getByRole("checkbox", {
        name: "Recipient confirms this signature",
      }),
    ).toBeDisabled();
  });
  it("rejects submission without a delivery photo before making a mutation", async () => {
    vi.mocked(request).mockResolvedValue(history);
    render(
      <DeliveryPanel trip={trip} identity={identity} own onChanged={vi.fn()} />,
    );
    await screen.findByLabelText("Recipient name");
    fireEvent.change(screen.getByLabelText("Recipient name"), {
      target: { value: "Maria Santos" },
    });
    fireEvent.click(
      screen.getByRole("checkbox", {
        name: "I confirm the cargo was delivered to this recipient.",
      }),
    );
    fireEvent.submit(
      screen
        .getByRole("button", { name: "Submit proof of delivery" })
        .closest("form")!,
    );
    await screen.findByText("At least one delivery photo is required.");
    expect(
      vi
        .mocked(request)
        .mock.calls.every(([, method]) => !method || method === "GET"),
    ).toBe(true);
  });
  it("keeps failed attempts visible and prevents driver retry authorization", async () => {
    vi.mocked(request).mockResolvedValue({
      ...history,
      total: 1,
      items: [
        {
          id: "failed",
          attempt_number: 1,
          status: "FAILED",
          arrived_at: "2030-01-01T00:00:00Z",
          completed_at: "2030-01-01T00:01:00Z",
          evidence: [],
          pod: null,
          exception: {
            id: "issue",
            exception_type: "RECIPIENT_UNAVAILABLE",
            status: "OPEN",
            notes: "Recipient contact unreachable.",
          },
        },
      ],
    });
    render(
      <DeliveryPanel trip={trip} identity={identity} own onChanged={vi.fn()} />,
    );
    await screen.findByText("Attempt 1");
    await waitFor(() =>
      expect(
        screen.queryByRole("button", { name: "Submit proof of delivery" }),
      ).not.toBeInTheDocument(),
    );
    expect(
      screen.queryByRole("button", { name: "Authorize delivery retry" }),
    ).not.toBeInTheDocument();
    expect(screen.getByText("Recipient contact unreachable.")).toBeVisible();
  });
});
