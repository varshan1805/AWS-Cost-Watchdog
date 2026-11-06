import json
from datetime import timedelta

import pytest
from conftest import REGION, launch, put_cpu

from watchdog import checks, scanner

TABLE = "cost-watchdog-findings"


@pytest.fixture
def stack(aws, monkeypatch):
    """The bits Terraform would create: a DynamoDB table, an SNS topic, and a queue to read the email from."""
    ddb = aws.client("dynamodb")
    ddb.create_table(
        TableName=TABLE,
        KeySchema=[{"AttributeName": "resource_id", "KeyType": "HASH"},
                   {"AttributeName": "scan_date", "KeyType": "RANGE"}],
        AttributeDefinitions=[{"AttributeName": "resource_id", "AttributeType": "S"},
                              {"AttributeName": "scan_date", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    topic = aws.client("sns").create_topic(Name="cost-watchdog-alerts")["TopicArn"]
    sqs = aws.client("sqs")
    queue_url = sqs.create_queue(QueueName="inbox")["QueueUrl"]
    queue_arn = sqs.get_queue_attributes(QueueUrl=queue_url, AttributeNames=["QueueArn"])["Attributes"]["QueueArn"]
    aws.client("sns").subscribe(TopicArn=topic, Protocol="sqs", Endpoint=queue_arn)

    monkeypatch.setenv("FINDINGS_TABLE", TABLE)
    monkeypatch.setenv("ALERT_TOPIC_ARN", topic)

    def emails():
        msgs = sqs.receive_message(QueueUrl=queue_url, MaxNumberOfMessages=10).get("Messages", [])
        return [json.loads(m["Body"]) for m in msgs]

    return {"session": aws, "emails": emails, "table": aws.resource("dynamodb").Table(TABLE)}


def make_some_waste(ec2, cloudwatch, now):
    idle = launch(ec2, "t3.small", name="demo-idle")
    put_cpu(cloudwatch, idle, now, [1] * 7)
    ec2.create_volume(Size=30, AvailabilityZone=f"{REGION}a", VolumeType="gp2")
    ec2.allocate_address(Domain="vpc")


def test_full_scan_saves_findings_and_sends_one_email(stack, ec2, cloudwatch, later):
    make_some_waste(ec2, cloudwatch, later)

    summary = scanner.handler({}, None, session=stack["session"], now=later)

    assert summary["findings"] == 3
    assert summary["monthly_waste_usd"] > 0
    assert summary["email_sent"] is True

    emails = stack["emails"]()
    assert len(emails) == 1
    assert emails[0]["Subject"].startswith("AWS cost watchdog: ~$")
    assert "IDLE EC2 INSTANCES" in emails[0]["Message"]
    assert "Nothing was stopped or deleted" in emails[0]["Message"]

    items = stack["table"].scan()["Items"]
    assert len(items) == 3
    assert all(i["scan_date"] == later.strftime("%Y-%m-%d") for i in items)


def test_second_day_remembers_when_a_resource_was_first_flagged(stack, ec2, cloudwatch, later):
    make_some_waste(ec2, cloudwatch, later)
    scanner.handler({}, None, session=stack["session"], now=later)

    next_day = later + timedelta(days=1)
    findings, _ = scanner.run_checks(scanner.Settings.from_env(), next_day, stack["session"])
    scanner.save_findings(stack["table"], findings, next_day, 90)

    assert all(f.details["first_seen"] == later.strftime("%Y-%m-%d") for f in findings)
    assert len(stack["table"].scan()["Items"]) == 6  # one row per resource per day


def test_clean_account_sends_no_email_by_default(stack, later):
    summary = scanner.handler({}, None, session=stack["session"], now=later)
    assert summary["findings"] == 0
    assert stack["emails"]() == []


def test_clean_account_sends_heartbeat_when_asked(stack, later, monkeypatch):
    monkeypatch.setenv("NOTIFY_WHEN_CLEAN", "true")
    scanner.handler({}, None, session=stack["session"], now=later)
    assert stack["emails"]()[0]["Subject"] == "AWS cost watchdog: nothing wasted today"


def test_a_broken_check_still_sends_the_report_then_fails(stack, ec2, cloudwatch, later, monkeypatch):
    make_some_waste(ec2, cloudwatch, later)

    def broken(*args, **kwargs):
        raise RuntimeError("AccessDenied on DescribeSnapshots")

    monkeypatch.setattr(scanner, "REGIONAL_CHECKS",
                        [broken if c is checks.old_snapshot else c for c in scanner.REGIONAL_CHECKS])

    with pytest.raises(RuntimeError, match="1 check"):
        scanner.handler({}, None, session=stack["session"], now=later)

    email = stack["emails"]()[0]
    assert "(some checks failed)" in email["Subject"]
    assert "AccessDenied" in email["Message"]
    assert "IDLE EC2 INSTANCES" in email["Message"]  # the other checks still reported
