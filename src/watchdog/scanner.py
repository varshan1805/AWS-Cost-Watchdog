"""
Lambda #1: the daily scan.

  1. run every check in every configured region
  2. save each finding to DynamoDB, so we know how long something has been wasting money
  3. email a summary through SNS

EventBridge Scheduler calls this once a day. You can also run it by hand from
the Lambda console with an empty test event {}.
"""

import json
import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

from . import checks
from .config import Settings
from .report import build_report, total_monthly

log = logging.getLogger()
log.setLevel(logging.INFO)

REGIONAL_CHECKS = [
    checks.stopped_ec2,
    checks.unattached_ebs,
    checks.old_snapshot,
    checks.unused_eip,
]


def run_checks(settings, now, session=None):
    """Returns (findings, errors). One broken check shouldn't hide the results of the others."""
    session = session or boto3.Session()
    findings, errors = [], []

    for region in settings.regions:
        ec2 = session.client("ec2", region_name=region)
        cloudwatch = session.client("cloudwatch", region_name=region)

        try:
            findings += checks.idle_ec2(ec2, cloudwatch, region, now, settings)
        except Exception as e:  # noqa: BLE001 - report it and keep going
            log.exception("idle_ec2 failed in %s", region)
            errors.append(f"idle_ec2 in {region}: {e}")

        for check in REGIONAL_CHECKS:
            try:
                findings += check(ec2, region, now, settings)
            except Exception as e:  # noqa: BLE001
                log.exception("%s failed in %s", check.__name__, region)
                errors.append(f"{check.__name__} in {region}: {e}")

    return findings, errors


def save_findings(table, findings, now, history_days):
    """
    One item per resource per day: (resource_id, scan_date).
    Before writing, look up the earliest record for each resource so the
    report can say "first flagged on ...". Items expire after history_days.
    """
    scan_date = now.strftime("%Y-%m-%d")
    expires_at = int((now + timedelta(days=history_days)).timestamp())

    for f in findings:
        first = table.query(
            KeyConditionExpression=Key("resource_id").eq(f.resource_id),
            Limit=1,
            ScanIndexForward=True,
        )["Items"]
        f.details["first_seen"] = first[0]["scan_date"] if first else scan_date

    with table.batch_writer(overwrite_by_pkeys=["resource_id", "scan_date"]) as batch:
        for f in findings:
            batch.put_item(Item={
                "resource_id": f.resource_id,
                "scan_date": scan_date,
                "check": f.check,
                "region": f.region,
                "name": f.name,
                # DynamoDB wants Decimal, not float
                "monthly_cost_usd": Decimal(str(f.monthly_cost_usd)) if f.monthly_cost_usd is not None else None,
                "reason": f.reason,
                "details": json.dumps(f.details, default=str),
                "expires_at": expires_at,
            })


def handler(event, context, session=None, now=None):
    settings = Settings.from_env()
    session = session or boto3.Session()
    now = now or datetime.now(UTC)

    account_id = session.client("sts").get_caller_identity()["Account"]
    findings, errors = run_checks(settings, now, session)
    log.info("scan done: %d findings, %d errors", len(findings), len(errors))

    if settings.table_name and findings:
        table = session.resource("dynamodb").Table(settings.table_name)
        save_findings(table, findings, now, settings.history_days)

    sent = False
    if settings.topic_arn and (findings or errors or settings.notify_when_clean):
        subject, body = build_report(findings, account_id, settings.regions, now, errors)
        session.client("sns").publish(TopicArn=settings.topic_arn, Subject=subject, Message=body)
        sent = True

    summary = {
        "account": account_id,
        "findings": len(findings),
        "monthly_waste_usd": total_monthly(findings),
        "errors": errors,
        "email_sent": sent,
    }
    log.info(json.dumps(summary))

    # Fail loudly after the email is out, so the CloudWatch alarm on Lambda
    # errors fires too. Retries are switched off in Terraform, so this won't
    # send the same email three times.
    if errors:
        raise RuntimeError(f"{len(errors)} check(s) failed: {errors}")
    return summary
