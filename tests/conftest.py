"""
All tests run against moto, a fake AWS that lives in memory.
No real account, no credentials, no cost.
"""

from datetime import UTC, datetime, timedelta

import boto3
import pytest
from moto import mock_aws

from watchdog.config import Settings

REGION = "ap-south-1"
AMI = "ami-12345678"  # moto accepts any id once its default AMIs are switched off


@pytest.fixture(autouse=True)
def fake_aws_env(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)
    monkeypatch.setenv("MOTO_EC2_LOAD_DEFAULT_AMIS", "false")
    monkeypatch.setenv("REGIONS", REGION)


@pytest.fixture
def aws():
    with mock_aws():
        yield boto3.Session(region_name=REGION)


@pytest.fixture
def ec2(aws):
    return aws.client("ec2")


@pytest.fixture
def cloudwatch(aws):
    return aws.client("cloudwatch")


@pytest.fixture
def settings():
    return Settings(regions=[REGION])


@pytest.fixture
def later():
    """
    moto stamps every resource with the real current time, and I can't backdate it.
    So instead of making resources old, I move "now" forward 120 days.
    """
    return datetime.now(UTC) + timedelta(days=120)


def launch(ec2, instance_type="t3.micro", name=None, tags=None):
    tag_list = [{"Key": "Name", "Value": name}] if name else []
    tag_list += [{"Key": k, "Value": v} for k, v in (tags or {}).items()]
    kwargs = {"ImageId": AMI, "MinCount": 1, "MaxCount": 1, "InstanceType": instance_type}
    if tag_list:
        kwargs["TagSpecifications"] = [{"ResourceType": "instance", "Tags": tag_list}]
    return ec2.run_instances(**kwargs)["Instances"][0]["InstanceId"]


def put_cpu(cloudwatch, instance_id, now, daily_values):
    """One CPU reading per day going back from `now`."""
    for days_ago, value in enumerate(daily_values):
        cloudwatch.put_metric_data(
            Namespace="AWS/EC2",
            MetricData=[{
                "MetricName": "CPUUtilization",
                "Dimensions": [{"Name": "InstanceId", "Value": instance_id}],
                "Timestamp": now - timedelta(days=days_ago, hours=2),
                "Value": value,
            }],
        )
