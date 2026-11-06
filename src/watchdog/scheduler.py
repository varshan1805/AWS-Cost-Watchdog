"""
Lambda #2: switch dev/test instances off at night and on in the morning.

Only touches instances tagged Schedule=office-hours (the tag key and value are
configurable). Anything without the tag is left alone, so production is safe
by default: you opt an instance in, never out.

EventBridge Scheduler sends {"action": "stop"} at 20:00 IST and
{"action": "start"} at 09:00 IST, Monday to Friday.
"""

import logging

import boto3

from .config import Settings

log = logging.getLogger()
log.setLevel(logging.INFO)

# stop -> only look at running instances, start -> only stopped ones
WANTED_STATE = {"stop": "running", "start": "stopped"}


def tagged_instances(ec2, settings, state):
    filters = [
        {"Name": f"tag:{settings.schedule_tag_key}", "Values": [settings.schedule_tag_value]},
        {"Name": "instance-state-name", "Values": [state]},
    ]
    ids = []
    for page in ec2.get_paginator("describe_instances").paginate(Filters=filters):
        for reservation in page["Reservations"]:
            ids += [i["InstanceId"] for i in reservation["Instances"]]
    return ids


def handler(event, context, session=None):
    settings = Settings.from_env()
    session = session or boto3.Session()

    action = (event or {}).get("action")
    if action not in WANTED_STATE:
        raise ValueError(f'event must be {{"action": "start"}} or {{"action": "stop"}}, got {event!r}')

    result = {"action": action, "dry_run": settings.dry_run, "instances": {}}
    for region in settings.regions:
        ec2 = session.client("ec2", region_name=region)
        ids = tagged_instances(ec2, settings, WANTED_STATE[action])
        result["instances"][region] = ids
        if not ids:
            continue

        if settings.dry_run:
            log.info("DRY RUN: would %s %s in %s", action, ids, region)
            continue

        # The API takes a list, but keep batches small so one bad ID doesn't sink 500 others
        for i in range(0, len(ids), 50):
            batch = ids[i:i + 50]
            if action == "stop":
                ec2.stop_instances(InstanceIds=batch)
            else:
                ec2.start_instances(InstanceIds=batch)
            log.info("%s %s in %s", action, batch, region)

    return result
