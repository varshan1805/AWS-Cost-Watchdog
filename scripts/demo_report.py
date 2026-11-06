"""
Shows what the daily email looks like without touching a real AWS account.

It builds a small fake account in moto (some idle, forgotten and orphaned
resources), runs the real scanner code against it, and prints the email.

    pip install -r requirements-dev.txt
    python scripts/demo_report.py
"""

import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

os.environ.update({
    "AWS_ACCESS_KEY_ID": "demo", "AWS_SECRET_ACCESS_KEY": "demo",
    "AWS_DEFAULT_REGION": "ap-south-1", "MOTO_EC2_LOAD_DEFAULT_AMIS": "false",
    "REGIONS": "ap-south-1",
})
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import boto3  # noqa: E402
from moto import mock_aws  # noqa: E402

from watchdog.config import Settings  # noqa: E402
from watchdog.report import build_report  # noqa: E402
from watchdog.scanner import run_checks  # noqa: E402

AZ = "ap-south-1a"


def tag(name):
    return [{"ResourceType": "instance", "Tags": [{"Key": "Name", "Value": name}]}]


def main():
    # moto timestamps everything with today's date, so "now" is pushed 120 days ahead
    now = datetime.now(UTC) + timedelta(days=120)

    with mock_aws():
        session = boto3.Session(region_name="ap-south-1")
        ec2, cw = session.client("ec2"), session.client("cloudwatch")

        def launch(itype, name):
            return ec2.run_instances(ImageId="ami-12345678", MinCount=1, MaxCount=1,
                                     InstanceType=itype, TagSpecifications=tag(name))["Instances"][0]["InstanceId"]

        def cpu(iid, values):
            for d, v in enumerate(values):
                cw.put_metric_data(Namespace="AWS/EC2", MetricData=[{
                    "MetricName": "CPUUtilization", "Value": v,
                    "Dimensions": [{"Name": "InstanceId", "Value": iid}],
                    "Timestamp": now - timedelta(days=d, hours=3)}])

        cpu(launch("t3.medium", "staging-api"), [1.2, 0.9, 1.5, 2.1, 1.1, 0.7, 1.3])
        cpu(launch("t3.large", "old-jenkins"), [2.4, 3.1, 1.9, 2.2, 2.8, 1.6, 2.0])
        cpu(launch("t3.small", "prod-web"), [38, 45, 52, 41, 47, 39, 44])      # busy, ignored
        cpu(launch("t3.micro", "nightly-etl"), [1, 1, 92, 1, 1, 1, 1])         # batch job, ignored

        forgotten = launch("t3.medium", "poc-demo-march")
        ec2.stop_instances(InstanceIds=[forgotten])

        ec2.create_volume(Size=100, AvailabilityZone=AZ, VolumeType="gp2")
        ec2.create_volume(Size=20, AvailabilityZone=AZ, VolumeType="gp3")
        vol = ec2.create_volume(Size=200, AvailabilityZone=AZ, VolumeType="gp3")
        ec2.create_snapshot(VolumeId=vol["VolumeId"], Description="before-upgrade")
        ec2.delete_volume(VolumeId=vol["VolumeId"])
        ec2.allocate_address(Domain="vpc")

        findings, errors = run_checks(Settings.from_env(), now, session)
        subject, body = build_report(findings, "123456789012", ["ap-south-1"], now, errors)

    print(f"Subject: {subject}\n")
    print(body)


if __name__ == "__main__":
    main()
