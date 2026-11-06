from datetime import UTC, datetime

from watchdog.checks import Finding
from watchdog.report import build_report

SCANNED = datetime(2026, 3, 2, 2, 30, tzinfo=UTC)  # 08:00 IST


def finding(check, rid, cost, name="-"):
    return Finding(check, rid, "ap-south-1", name, cost, "some reason")


def test_subject_has_total_and_count():
    subject, _ = build_report(
        [finding("idle_ec2", "i-1", 32.70), finding("unused_eip", "eipalloc-1", 3.65)],
        "123456789012", ["ap-south-1"], SCANNED,
    )
    assert subject == "AWS cost watchdog: ~$36.35/month of waste in 2 resources"


def test_body_shows_time_in_ist_and_yearly_figure():
    _, body = build_report([finding("idle_ec2", "i-1", 10.0)], "123456789012", ["ap-south-1"], SCANNED)
    assert "02 Mar 2026, 08:00 IST" in body
    assert "$120.00 a year" in body


def test_most_expensive_item_is_listed_first_within_a_group():
    _, body = build_report(
        [finding("unattached_ebs", "vol-small", 1.0), finding("unattached_ebs", "vol-big", 50.0)],
        "123456789012", ["ap-south-1"], SCANNED,
    )
    assert body.index("vol-big") < body.index("vol-small")


def test_unknown_price_says_so_instead_of_zero():
    _, body = build_report([finding("idle_ec2", "i-1", None)], "1", ["ap-south-1"], SCANNED)
    assert "price unknown" in body


def test_failed_checks_are_called_out():
    subject, body = build_report([], "1", ["ap-south-1"], SCANNED, errors=["old_snapshot: AccessDenied"])
    assert subject.endswith("(some checks failed)")
    assert "THESE CHECKS FAILED" in body


def test_subject_never_exceeds_sns_limit():
    many = [finding("idle_ec2", f"i-{n}", 1234567.0) for n in range(999)]
    subject, _ = build_report(many, "1", ["ap-south-1"], SCANNED, errors=["x"])
    assert len(subject) <= 100
