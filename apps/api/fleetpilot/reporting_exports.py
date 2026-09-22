"""Complete bounded exports. Text and validated numeric cells have separate policies."""

import csv
import html
import io
import json
import re
import unicodedata

from fastapi import HTTPException

from .reporting_contract import MAX_EXPORT_ROWS

TITLES = {
    "executive-contribution": "Executive Contribution",
    "trip-contribution": "Trip Contribution",
    "customer-contribution": "Customer Contribution",
    "direct-costs": "Direct Cost Analysis",
    "financial-exceptions": "Financial Exceptions",
    "cash-advances": "Cash Advance & Settlement",
}
CSV_NOTICE = "Text cells are prefixed with an apostrophe and controls are removed to reduce spreadsheet-formula injection. Spreadsheet import and re-save behavior varies; do not remove the text prefix or enable external content. Negative monetary values are validated numeric cells."


class Numeric(str):
    def __new__(cls, value):
        value = str(value)
        if not re.fullmatch(r"-?[0-9]+(?:\.[0-9]{1,2})?", value):
            raise ValueError("Invalid numeric export value")
        return super().__new__(cls, value)


def numeric(value):
    return Numeric(value) if value is not None else "N/A"


def cell(value):
    if isinstance(value, Numeric):
        return str(value)
    text = unicodedata.normalize("NFKC", str(value if value is not None else ""))
    text = "".join(" " if unicodedata.category(c).startswith("C") else c for c in text)
    return "'" + text


def sections(name, result):
    summary = result["summary"]
    if name == "executive-contribution":
        return [
            (
                "Executive totals",
                ["Metric", "Value"],
                [[k.replace("_", " ").title(), numeric(v)] for k, v in summary.items()],
            ),
            (
                "Lifecycle subtotals",
                ["Lifecycle", "Trips", "Revenue", "Direct cost", "Contribution"],
                [
                    [
                        x["lifecycle"],
                        numeric(x["trip_count"]),
                        numeric(x["revenue"]),
                        numeric(x["direct_cost"]),
                        numeric(x["contribution"]),
                    ]
                    for x in result["lifecycle_totals"]
                ],
            ),
            (
                "Advance attention (separate from costs)",
                ["Metric", "Value"],
                [
                    [k.replace("_", " ").title(), numeric(v)]
                    for k, v in result["advance_summary"].items()
                ],
            ),
        ]
    if name == "trip-contribution":
        categories = sorted({c["category"] for t in result["trips"] for c in t["category_costs"]})
        headers = [
            "Trip ID",
            "Trip",
            "Customer",
            "Vehicle",
            "Scheduled pickup",
            "Lifecycle",
            "Financial status",
            "Revenue",
            "Direct cost",
            "Contribution",
            "Margin %",
            "Data quality",
        ] + categories
        data = []
        for t in result["trips"]:
            costs = {c["category"]: c["reviewed_total"] for c in t["category_costs"]}
            data.append(
                [
                    t["id"],
                    t["trip_number"],
                    t["customer_name"],
                    t["vehicle_name"],
                    t["scheduled_pickup_at"],
                    t["current_status"],
                    t["status"],
                    numeric(t["revenue"]),
                    numeric(t["direct_cost"]),
                    numeric(t["contribution"]),
                    numeric(t["margin_percent"]),
                    "; ".join(t["data_warnings"]),
                ]
                + [numeric(costs.get(c, "0.00")) for c in categories]
            )
        return [("Reviewed trip contribution", headers, data)]
    if name == "customer-contribution":
        return [
            (
                "Customer contribution for the selected period",
                [
                    "Customer ID",
                    "Customer",
                    "Trips",
                    "Revenue",
                    "Direct cost",
                    "Contribution",
                    "Weighted margin %",
                    "Negative trips",
                    "Provisional trips",
                    "Provisional contribution",
                ],
                [
                    [
                        c["customer_id"],
                        c["customer_name"],
                        numeric(c["trip_count"]),
                        numeric(c["revenue"]),
                        numeric(c["direct_cost"]),
                        numeric(c["contribution"]),
                        numeric(c["weighted_margin_percent"]),
                        numeric(c["negative_count"]),
                        numeric(c["provisional_count"]),
                        numeric(c["provisional_contribution"]),
                    ]
                    for c in result["customers"]
                ],
            )
        ]
    if name == "direct-costs":
        return [
            (
                "Direct cost categories",
                [
                    "Category",
                    "Reviewed direct cost",
                    "Submitted incl. reviewed",
                    "Share of reviewed cost %",
                    "Unreviewed records",
                    "Trip IDs",
                ],
                [
                    [
                        c["category"],
                        numeric(c["reviewed_total"]),
                        numeric(c["submitted_total"]),
                        numeric(c["share_percent"]),
                        numeric(c["unreviewed_count"]),
                        "; ".join(c["trip_ids"]),
                    ]
                    for c in result["categories"]
                ],
            ),
            (
                "Excluded funding",
                ["Metric", "Amount"],
                [
                    [
                        "Captured advances (not issuance)",
                        numeric(result["advance_summary"]["captured_amount"]),
                    ],
                    [
                        "Confirmed active issuance (not expense)",
                        numeric(result["advance_summary"]["issued"]),
                    ],
                ],
            ),
        ]
    if name == "financial-exceptions":
        return [
            (
                "Prioritized financial findings",
                [
                    "Key",
                    "Priority",
                    "Rule / version",
                    "Title",
                    "Explanation",
                    "Supporting values",
                    "Comparison",
                    "Qualification",
                    "Review action",
                    "Trip ID",
                    "Source event ID",
                ],
                [
                    [
                        f["key"],
                        f["priority"],
                        f["rule_id"] + " / " + f["rule_version"],
                        f["title"],
                        f["explanation"],
                        json.dumps(f["supporting_values"], sort_keys=True, default=str),
                        f["comparison_basis"],
                        f["qualification"],
                        f["recommended_action"],
                        f["trip_id"],
                        f["source_event_id"],
                    ]
                    for f in result["findings"]
                ],
            )
        ]
    return [
        (
            "Captured records — not independently confirmed issuance",
            [
                "Expense ID",
                "Trip ID",
                "Captured amount",
                "Review status",
                "Linked issuance ID",
                "Unreconciled",
            ],
            [
                [
                    c["id"],
                    c["trip_id"],
                    numeric(c["amount"]),
                    c["status"],
                    c["issuance_id"],
                    str(c["unreconciled"]),
                ]
                for c in result["captures"]
            ],
        ),
        (
            "Confirmed issuance and current settlement",
            [
                "Advance ID",
                "Trip ID",
                "Source capture ID",
                "Issued",
                "Applied",
                "Returned",
                "Outstanding",
                "Status",
                "Issued at",
            ],
            [
                [
                    a["id"],
                    a["trip_id"],
                    a["source_expense_id"],
                    numeric(a["amount_issued"]),
                    numeric(a["applied"]),
                    numeric(a["returned"]),
                    numeric(a["outstanding"]),
                    a["status"],
                    a["issued_at"],
                ]
                for a in result["advances"]
            ],
        ),
        (
            "Settlement review blockers by trip",
            ["Trip", "Unreconciled captures", "Conflicts"],
            [
                [
                    t["trip_number"],
                    numeric(t["advance"]["unreconciled_capture_count"]),
                    "; ".join(map(str, t["advance"]["conflicts"])),
                ]
                for t in result["trips"]
                if t["advance"]["unreconciled_capture_count"] or t["advance"]["conflicts"]
            ],
        ),
    ]


def export_report(name, result, format):
    scope = result["scope"]
    groups = sections(name, result)
    if sum(len(data) for _, _, data in groups) > MAX_EXPORT_ROWS:
        raise HTTPException(
            413,
            f"Export exceeds {MAX_EXPORT_ROWS} rows. Narrow the filters; no partial file was produced.",
        )
    metadata = [
        ("Report", TITLES[name]),
        ("Organization", scope["organization_name"]),
        ("Organization ID", scope["organization_id"]),
        ("Period", scope["date_from"] + " to " + scope["date_to"]),
        ("Date basis", scope["date_basis"]),
        ("Timezone", scope["timezone"]),
        ("Lifecycle filter", scope["lifecycle"]),
        ("Financial-status filter", scope["financial_status"]),
        ("Customer filter", scope["customer_id"] or "ALL"),
        ("Vehicle filter", scope["vehicle_id"] or "ALL"),
        ("Trip filter", scope["trip_id"] or "ALL"),
        ("Included trip count", numeric(scope["record_count"])),
        ("Calculated at", scope["calculated_at"]),
        ("Rule version", scope["rule_version"]),
        ("Result fingerprint", scope["fingerprint"]),
        ("Dataset", "SYNTHETIC VALIDATION DATA" if scope["synthetic"] else "Business records"),
        ("Financial basis and exclusions", scope["qualification"]),
        (
            "Recalculation",
            "This export is newly calculated at the timestamp above and may differ from an earlier screen.",
        ),
        *[("Warning", warning) for warning in scope["warnings"]],
        ("CSV text safety", CSV_NOTICE),
    ]
    if format == "csv":
        stream = io.StringIO(newline="")
        writer = csv.writer(stream, quoting=csv.QUOTE_ALL, lineterminator="\r\n")
        writer.writerows([[cell(v) for v in row] for row in metadata])
        for title, headers, data in groups:
            writer.writerow([])
            writer.writerow([cell(title)])
            writer.writerow([cell(v) for v in headers])
            writer.writerows([[cell(v) for v in row] for row in data])
        output = "\ufeff" + stream.getvalue()
    else:

        def esc(v):
            return html.escape(str(v if v is not None else ""), quote=True)

        parts = [
            '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">',
            "<title>"
            + esc(TITLES[name])
            + "</title><style>body{font:12px Arial,sans-serif;color:#08111f;margin:24px}h1{font-size:24px}h2{font-size:17px;margin-top:24px}table{border-collapse:collapse;width:100%;margin:12px 0}th,td{text-align:left;vertical-align:top;border:1px solid #ccd1d7;padding:6px;overflow-wrap:anywhere}th{background:#f6f8fa}dl{display:grid;grid-template-columns:150px 1fr;gap:4px}dt{font-weight:bold}dd{margin:0}.notice{padding:12px;border:2px solid #08111f}thead{display:table-header-group}tr{break-inside:avoid}@page{size:A4 landscape;margin:12mm}@media print{body{margin:0;font-size:9px}}</style><body>",
            "<h1>FleetPilot — " + esc(TITLES[name]) + "</h1>",
            '<p class="notice">'
            + esc("SYNTHETIC VALIDATION DATA — " if scope["synthetic"] else "")
            + esc(scope["qualification"])
            + "</p>",
            "<p>Print this complete report with your browser’s Print / Save as PDF command.</p><dl>",
        ]
        parts.extend("<dt>" + esc(k) + "</dt><dd>" + esc(v) + "</dd>" for k, v in metadata)
        parts.append("</dl>")
        for title, headers, data in groups:
            parts.append(
                "<h2>"
                + esc(title)
                + "</h2><table><thead><tr>"
                + "".join("<th>" + esc(v) + "</th>" for v in headers)
                + "</tr></thead><tbody>"
            )
            parts.extend(
                "<tr>" + "".join("<td>" + esc(v) + "</td>" for v in row) + "</tr>" for row in data
            )
            parts.append(
                "</tbody></table>" if data else "</tbody></table><p>No matching records.</p>"
            )
        parts.append("</body></html>")
        output = "".join(parts)
    if len(output.encode("utf-8")) > 10000000:
        raise HTTPException(
            413, "Export exceeds 10 MB. Narrow the filters; no partial file was produced."
        )
    return output
