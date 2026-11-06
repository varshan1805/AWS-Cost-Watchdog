"""
Turns a list of findings into the email that lands in your inbox.

Plain text on purpose: SNS email can't do HTML, and plain text reads fine on a phone.
"""

from datetime import timedelta, timezone

from .checks import CHECK_TITLES

# Fixed offset instead of zoneinfo so the Lambda doesn't need tz data. India has no DST.
IST = timezone(timedelta(hours=5, minutes=30), "IST")


def money(value):
    return "price unknown" if value is None else f"${value:,.2f}"


def total_monthly(findings):
    return round(sum(f.monthly_cost_usd or 0 for f in findings), 2)


def build_report(findings, account_id, regions, scanned_at, errors=None):
    errors = errors or []
    total = total_monthly(findings)
    when = scanned_at.astimezone(IST).strftime("%d %b %Y, %H:%M IST")

    if findings:
        subject = f"AWS cost watchdog: ~${total:,.2f}/month of waste in {len(findings)} resources"
    else:
        subject = "AWS cost watchdog: nothing wasted today"
    if errors:
        subject += " (some checks failed)"

    lines = [
        f"Daily scan of account {account_id} ({', '.join(regions)})",
        when,
        "",
    ]

    if findings:
        lines += [
            f"Found {len(findings)} resources costing about {money(total)} a month "
            f"({money(round(total * 12, 2))} a year).",
            "",
        ]
    else:
        lines += ["Nothing to report. Every check came back clean.", ""]

    for check, title in CHECK_TITLES.items():
        group = sorted((f for f in findings if f.check == check),
                       key=lambda f: f.monthly_cost_usd or 0, reverse=True)
        if not group:
            continue
        lines.append(f"{title.upper()}  ({money(total_monthly(group))}/month)")
        for f in group:
            label = f.resource_id if f.name == "-" else f"{f.resource_id} ({f.name})"
            lines.append(f"  - {label}, {f.region}")
            lines.append(f"    {f.reason}. Costs about {money(f.monthly_cost_usd)}/month.")
            first_seen = f.details.get("first_seen")
            if first_seen:
                lines.append(f"    First flagged on {first_seen}.")
        lines.append("")

    if any(f.check == "old_snapshot" for f in findings):
        lines += ["Snapshot costs are an upper bound: snapshots only store changed blocks.", ""]

    if errors:
        lines.append("THESE CHECKS FAILED, so the report above may be missing things:")
        lines += [f"  - {e}" for e in errors]
        lines.append("")

    lines += [
        "Nothing was stopped or deleted. This is a report only.",
        "Prices are approximate on-demand rates.",
    ]
    return subject[:100], "\n".join(lines)
