"""
Rough on-demand prices for ap-south-1 (Mumbai), Linux, in USD.

These are approximations I took from the AWS pricing pages and they drift
over time. They're good enough to rank waste and put a ballpark number on it,
not for invoicing. If you run this in another region or need exact numbers,
swap this table for the AWS Pricing API (see "What I'd add next" in the README).

Anything not in the table comes back as None and the report says "price unknown"
instead of guessing.
"""

HOURS_PER_MONTH = 730

EC2_HOURLY = {
    "t2.micro": 0.0124, "t2.small": 0.0248, "t2.medium": 0.0496,
    "t3.nano": 0.0056, "t3.micro": 0.0112, "t3.small": 0.0224,
    "t3.medium": 0.0448, "t3.large": 0.0896, "t3.xlarge": 0.1792,
    "t3a.micro": 0.0101, "t3a.small": 0.0202, "t3a.medium": 0.0403,
    "t4g.micro": 0.0090, "t4g.small": 0.0179, "t4g.medium": 0.0358,
    "m5.large": 0.101, "m5.xlarge": 0.202, "m6i.large": 0.101,
    "c5.large": 0.085, "c5.xlarge": 0.170, "r5.large": 0.130,
}

# per GB-month
EBS_GB_MONTH = {
    "gp3": 0.0912, "gp2": 0.114, "io1": 0.142, "io2": 0.142,
    "st1": 0.051, "sc1": 0.0174, "standard": 0.08,
}

# Snapshots are incremental, so charging the full volume size is an upper bound
SNAPSHOT_GB_MONTH = 0.05

# Every public IPv4 address is billed hourly, attached or not
PUBLIC_IPV4_HOURLY = 0.005


def ec2_monthly(instance_type):
    hourly = EC2_HOURLY.get(instance_type)
    return None if hourly is None else round(hourly * HOURS_PER_MONTH, 2)


def ebs_monthly(volume_type, size_gb):
    rate = EBS_GB_MONTH.get(volume_type)
    return None if rate is None else round(rate * size_gb, 2)


def snapshot_monthly(size_gb):
    return round(SNAPSHOT_GB_MONTH * size_gb, 2)


def eip_monthly():
    return round(PUBLIC_IPV4_HOURLY * HOURS_PER_MONTH, 2)
