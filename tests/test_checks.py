from datetime import UTC, datetime

from conftest import REGION, launch, put_cpu

from watchdog import checks, pricing

# --- idle EC2 ---------------------------------------------------------------

def test_quiet_instance_is_flagged_with_its_cost(ec2, cloudwatch, settings, later):
    iid = launch(ec2, "t3.medium", name="old-test-box")
    put_cpu(cloudwatch, iid, later, [1.5, 2.0, 0.8, 1.1, 2.4, 1.0, 1.9])

    found = checks.idle_ec2(ec2, cloudwatch, REGION, later, settings)

    assert [f.resource_id for f in found] == [iid]
    assert found[0].name == "old-test-box"
    assert found[0].monthly_cost_usd == round(0.0448 * 730, 2)
    assert "avg CPU" in found[0].reason


def test_busy_instance_is_left_alone(ec2, cloudwatch, settings, later):
    iid = launch(ec2)
    put_cpu(cloudwatch, iid, later, [40, 55, 38, 61, 47, 52, 44])
    assert checks.idle_ec2(ec2, cloudwatch, REGION, later, settings) == []


def test_nightly_batch_box_is_not_called_idle(ec2, cloudwatch, settings, later):
    # Low average, but one big spike: it's doing real work once a day
    iid = launch(ec2)
    put_cpu(cloudwatch, iid, later, [1, 1, 85, 1, 1, 1, 1])
    assert checks.idle_ec2(ec2, cloudwatch, REGION, later, settings) == []


def test_instance_younger_than_lookback_is_skipped(ec2, cloudwatch, settings):
    now = datetime.now(UTC)
    iid = launch(ec2)
    put_cpu(cloudwatch, iid, now, [1, 1])
    assert checks.idle_ec2(ec2, cloudwatch, REGION, now, settings) == []


def test_instance_with_no_metrics_is_skipped(ec2, cloudwatch, settings, later):
    launch(ec2)
    assert checks.idle_ec2(ec2, cloudwatch, REGION, later, settings) == []


def test_unknown_instance_type_gets_no_made_up_price(ec2, cloudwatch, settings, later):
    iid = launch(ec2, "x2iedn.xlarge")
    put_cpu(cloudwatch, iid, later, [1] * 7)
    found = checks.idle_ec2(ec2, cloudwatch, REGION, later, settings)
    assert found[0].monthly_cost_usd is None


# --- stopped EC2 --------------------------------------------------------------

def test_instance_stopped_for_weeks_is_flagged_with_disk_cost(ec2, settings, later):
    iid = launch(ec2, name="forgotten")
    ec2.stop_instances(InstanceIds=[iid])

    found = checks.stopped_ec2(ec2, REGION, later, settings)

    assert [f.resource_id for f in found] == [iid]
    assert found[0].details["stopped_days"] >= 119
    assert found[0].monthly_cost_usd > 0


def test_instance_stopped_yesterday_is_not_flagged(ec2, settings):
    iid = launch(ec2)
    ec2.stop_instances(InstanceIds=[iid])
    assert checks.stopped_ec2(ec2, REGION, datetime.now(UTC), settings) == []


def test_stop_time_parsing_handles_real_aws_format():
    inst = {"StateTransitionReason": "User initiated (2025-01-31 10:15:00 GMT)"}
    since = checks._stopped_since(inst, UTC)
    assert since == datetime(2025, 1, 31, 10, 15, tzinfo=UTC)


def test_unparseable_stop_reason_is_ignored_not_guessed():
    assert checks._stopped_since({"StateTransitionReason": "Server.SpotInstanceTermination"}, UTC) is None


# --- EBS ----------------------------------------------------------------------

def test_loose_volume_is_flagged_and_attached_ones_are_not(ec2, settings, later):
    launch(ec2)  # has an attached root volume, must not show up
    vol = ec2.create_volume(Size=100, AvailabilityZone=f"{REGION}a", VolumeType="gp3")

    found = checks.unattached_ebs(ec2, REGION, later, settings)

    assert [f.resource_id for f in found] == [vol["VolumeId"]]
    assert found[0].monthly_cost_usd == pricing.ebs_monthly("gp3", 100)


# --- snapshots ----------------------------------------------------------------

def test_old_snapshot_is_flagged_but_ami_snapshot_is_protected(ec2, settings, later):
    vol = ec2.create_volume(Size=50, AvailabilityZone=f"{REGION}a")
    orphan = ec2.create_snapshot(VolumeId=vol["VolumeId"])["SnapshotId"]

    iid = launch(ec2)
    image_id = ec2.create_image(InstanceId=iid, Name="golden-image")["ImageId"]
    image = ec2.describe_images(ImageIds=[image_id])["Images"][0]
    protected = image["BlockDeviceMappings"][0]["Ebs"]["SnapshotId"]

    found = {f.resource_id for f in checks.old_snapshot(ec2, REGION, later, settings)}

    assert orphan in found
    assert protected not in found


def test_recent_snapshot_is_not_flagged(ec2, settings):
    vol = ec2.create_volume(Size=10, AvailabilityZone=f"{REGION}a")
    ec2.create_snapshot(VolumeId=vol["VolumeId"])
    assert checks.old_snapshot(ec2, REGION, datetime.now(UTC), settings) == []


# --- Elastic IPs --------------------------------------------------------------

def test_unattached_eip_is_flagged_and_attached_one_is_not(ec2, settings, later):
    loose = ec2.allocate_address(Domain="vpc")
    used = ec2.allocate_address(Domain="vpc")
    ec2.associate_address(AllocationId=used["AllocationId"], InstanceId=launch(ec2))

    found = checks.unused_eip(ec2, REGION, later, settings)

    assert [f.resource_id for f in found] == [loose["AllocationId"]]
    assert found[0].monthly_cost_usd == 3.65
