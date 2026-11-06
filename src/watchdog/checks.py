"""
The waste checks. Each one looks for a single kind of waste in one region and
returns a list of Finding objects.

Everything in this file is read-only. Nothing here stops, deletes or changes
a resource. Deciding what to do about a finding is a human's job.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from . import pricing


@dataclass
class Finding:
    check: str
    resource_id: str
    region: str
    name: str
    monthly_cost_usd: float | None
    reason: str
    details: dict = field(default_factory=dict)


CHECK_TITLES = {
    "idle_ec2": "Idle EC2 instances",
    "stopped_ec2": "Instances stopped for a long time (still paying for disks)",
    "unattached_ebs": "EBS volumes not attached to anything",
    "old_snapshot": "Old snapshots not used by any AMI",
    "unused_eip": "Elastic IPs not attached to anything",
}


def _name_tag(tags):
    for t in tags or []:
        if t["Key"] == "Name":
            return t["Value"]
    return "-"


def _instances(ec2, state):
    paginator = ec2.get_paginator("describe_instances")
    for page in paginator.paginate(Filters=[{"Name": "instance-state-name", "Values": [state]}]):
        for reservation in page["Reservations"]:
            yield from reservation["Instances"]


# ---------------------------------------------------------------------------

def idle_ec2(ec2, cloudwatch, region, now, settings):
    """Running instances whose CPU stayed low for the whole lookback window."""
    findings = []
    start = now - timedelta(days=settings.lookback_days)

    for inst in _instances(ec2, "running"):
        # Can't call something idle for 7 days if it's only been up for 2
        if inst["LaunchTime"] > start:
            continue

        stats = cloudwatch.get_metric_statistics(
            Namespace="AWS/EC2",
            MetricName="CPUUtilization",
            Dimensions=[{"Name": "InstanceId", "Value": inst["InstanceId"]}],
            StartTime=start,
            EndTime=now,
            Period=86400,
            Statistics=["Average", "Maximum"],
        )["Datapoints"]
        if not stats:
            continue  # no data means I can't say anything, so I say nothing

        avg = sum(p["Average"] for p in stats) / len(stats)
        peak = max(p["Maximum"] for p in stats)
        if avg >= settings.idle_cpu_avg_pct or peak >= settings.idle_cpu_peak_pct:
            continue

        itype = inst["InstanceType"]
        findings.append(Finding(
            check="idle_ec2",
            resource_id=inst["InstanceId"],
            region=region,
            name=_name_tag(inst.get("Tags")),
            monthly_cost_usd=pricing.ec2_monthly(itype),
            reason=f"avg CPU {avg:.1f}%, peak {peak:.1f}% over {settings.lookback_days} days",
            details={"instance_type": itype, "avg_cpu": round(avg, 2), "peak_cpu": round(peak, 2)},
        ))
    return findings


# Real AWS writes "User initiated (2025-01-31 10:15:00 GMT)". Some tools write UTC.
_STOP_TIME = re.compile(r"\((\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (?:GMT|UTC)\)")


def _stopped_since(inst, tz):
    match = _STOP_TIME.search(inst.get("StateTransitionReason", ""))
    if not match:
        return None
    return datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=tz)


def stopped_ec2(ec2, region, now, settings):
    """
    Stopped instances don't cost compute, but their EBS disks keep billing.
    An instance that's been off for weeks is usually forgotten, not paused.
    """
    findings = []
    for inst in _instances(ec2, "stopped"):
        since = _stopped_since(inst, now.tzinfo)
        if since is None or (now - since).days < settings.stopped_min_days:
            continue

        volume_ids = [m["Ebs"]["VolumeId"] for m in inst.get("BlockDeviceMappings", []) if "Ebs" in m]
        cost, total_gb = 0.0, 0
        if volume_ids:
            for vol in ec2.describe_volumes(VolumeIds=volume_ids)["Volumes"]:
                total_gb += vol["Size"]
                cost += pricing.ebs_monthly(vol["VolumeType"], vol["Size"]) or 0.0

        days = (now - since).days
        findings.append(Finding(
            check="stopped_ec2",
            resource_id=inst["InstanceId"],
            region=region,
            name=_name_tag(inst.get("Tags")),
            monthly_cost_usd=round(cost, 2),
            reason=f"stopped for {days} days, {total_gb} GB of disk still billed",
            details={"instance_type": inst["InstanceType"], "stopped_days": days,
                     "volume_ids": volume_ids, "disk_gb": total_gb},
        ))
    return findings


def unattached_ebs(ec2, region, now, settings):
    """Volumes in the 'available' state. Usually left behind after an instance was terminated."""
    findings = []
    paginator = ec2.get_paginator("describe_volumes")
    for page in paginator.paginate(Filters=[{"Name": "status", "Values": ["available"]}]):
        for vol in page["Volumes"]:
            age = (now - vol["CreateTime"]).days
            findings.append(Finding(
                check="unattached_ebs",
                resource_id=vol["VolumeId"],
                region=region,
                name=_name_tag(vol.get("Tags")),
                monthly_cost_usd=pricing.ebs_monthly(vol["VolumeType"], vol["Size"]),
                reason=f"{vol['Size']} GB {vol['VolumeType']}, unattached, created {age} days ago",
                details={"size_gb": vol["Size"], "volume_type": vol["VolumeType"], "age_days": age},
            ))
    return findings


def old_snapshot(ec2, region, now, settings):
    """
    Snapshots older than the cut-off that no AMI depends on.
    Snapshots behind an AMI are skipped: deleting them would break the image.
    """
    in_use = set()
    for image in ec2.describe_images(Owners=["self"])["Images"]:
        for mapping in image.get("BlockDeviceMappings", []):
            snap_id = mapping.get("Ebs", {}).get("SnapshotId")
            if snap_id:
                in_use.add(snap_id)

    findings = []
    cutoff = now - timedelta(days=settings.snapshot_max_age_days)
    paginator = ec2.get_paginator("describe_snapshots")
    for page in paginator.paginate(OwnerIds=["self"]):
        for snap in page["Snapshots"]:
            if snap["SnapshotId"] in in_use or snap["StartTime"] > cutoff:
                continue
            age = (now - snap["StartTime"]).days
            findings.append(Finding(
                check="old_snapshot",
                resource_id=snap["SnapshotId"],
                region=region,
                name=_name_tag(snap.get("Tags")),
                monthly_cost_usd=pricing.snapshot_monthly(snap["VolumeSize"]),
                reason=f"{age} days old, {snap['VolumeSize']} GB source volume, not used by any AMI",
                details={"age_days": age, "volume_size_gb": snap["VolumeSize"],
                         "cost_is_upper_bound": True},
            ))
    return findings


def unused_eip(ec2, region, now, settings):
    """Elastic IPs that aren't associated with anything."""
    findings = []
    for addr in ec2.describe_addresses()["Addresses"]:
        if addr.get("AssociationId"):
            continue
        findings.append(Finding(
            check="unused_eip",
            resource_id=addr.get("AllocationId", addr["PublicIp"]),
            region=region,
            name=_name_tag(addr.get("Tags")),
            monthly_cost_usd=pricing.eip_monthly(),
            reason=f"{addr['PublicIp']} is not attached to anything",
            details={"public_ip": addr["PublicIp"]},
        ))
    return findings
