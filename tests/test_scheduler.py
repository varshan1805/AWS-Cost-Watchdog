import pytest
from conftest import launch

from watchdog import scheduler

TAG = {"Schedule": "office-hours"}


def state(ec2, iid):
    return ec2.describe_instances(InstanceIds=[iid])["Reservations"][0]["Instances"][0]["State"]["Name"]


def test_stop_only_touches_tagged_instances(aws, ec2):
    dev = launch(ec2, name="dev", tags=TAG)
    prod = launch(ec2, name="prod")

    result = scheduler.handler({"action": "stop"}, None, session=aws)

    assert result["instances"]["ap-south-1"] == [dev]
    assert state(ec2, dev) == "stopped"
    assert state(ec2, prod) == "running"


def test_start_brings_tagged_instances_back(aws, ec2):
    dev = launch(ec2, tags=TAG)
    ec2.stop_instances(InstanceIds=[dev])

    scheduler.handler({"action": "start"}, None, session=aws)

    assert state(ec2, dev) == "running"


def test_a_tag_with_a_different_value_is_ignored(aws, ec2):
    other = launch(ec2, tags={"Schedule": "always-on"})
    scheduler.handler({"action": "stop"}, None, session=aws)
    assert state(ec2, other) == "running"


def test_dry_run_reports_but_changes_nothing(aws, ec2, monkeypatch):
    monkeypatch.setenv("DRY_RUN", "true")
    dev = launch(ec2, tags=TAG)

    result = scheduler.handler({"action": "stop"}, None, session=aws)

    assert result["dry_run"] is True
    assert result["instances"]["ap-south-1"] == [dev]
    assert state(ec2, dev) == "running"


@pytest.mark.parametrize("event", [{}, None, {"action": "reboot"}])
def test_bad_event_is_rejected(aws, event):
    with pytest.raises(ValueError):
        scheduler.handler(event, None, session=aws)
