#!/usr/bin/env bash
# Creates a small amount of deliberate waste so you can watch the watchdog catch it.
# Easiest place to run this: AWS CloudShell (the >_ icon in the AWS console). It has the AWS CLI ready.
#
# What it creates, and roughly what it costs while it exists:
#   - 1 x t3.micro, tagged Schedule=office-hours   ~$0.27/day (free tier eligible on many accounts)
#   - 1 x 1 GB gp3 volume, not attached             ~$0.003/day
#   - 1 x snapshot of that volume                   ~$0.002/day
#   - 1 x Elastic IP, not attached                  ~$0.12/day
#
# Delete it all afterwards with scripts/cleanup_test_waste.sh
set -euo pipefail

REGION="${AWS_REGION:-ap-south-1}"
TAG="Purpose=watchdog-demo"
echo "Creating demo waste in $REGION"

AMI=$(aws ssm get-parameter --region "$REGION" \
  --name /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 \
  --query Parameter.Value --output text)
AZ=$(aws ec2 describe-availability-zones --region "$REGION" --query 'AvailabilityZones[0].ZoneName' --output text)

INSTANCE=$(aws ec2 run-instances --region "$REGION" --image-id "$AMI" --instance-type t3.micro \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=watchdog-demo-idle},{Key=Schedule,Value=office-hours},{Key=Purpose,Value=watchdog-demo}]" \
  --query 'Instances[0].InstanceId' --output text)
echo "  instance  $INSTANCE (will look idle after LOOKBACK_DAYS of doing nothing)"

VOLUME=$(aws ec2 create-volume --region "$REGION" --availability-zone "$AZ" --size 1 --volume-type gp3 \
  --tag-specifications "ResourceType=volume,Tags=[{Key=Name,Value=watchdog-demo-orphan},{Key=Purpose,Value=watchdog-demo}]" \
  --query VolumeId --output text)
echo "  volume    $VOLUME"

aws ec2 wait volume-available --region "$REGION" --volume-ids "$VOLUME"
SNAPSHOT=$(aws ec2 create-snapshot --region "$REGION" --volume-id "$VOLUME" --description "watchdog demo" \
  --tag-specifications "ResourceType=snapshot,Tags=[{Key=Name,Value=watchdog-demo-snap},{Key=Purpose,Value=watchdog-demo}]" \
  --query SnapshotId --output text)
echo "  snapshot  $SNAPSHOT"

EIP=$(aws ec2 allocate-address --region "$REGION" --domain vpc \
  --tag-specifications "ResourceType=elastic-ip,Tags=[{Key=Name,Value=watchdog-demo-eip},{Key=Purpose,Value=watchdog-demo}]" \
  --query AllocationId --output text)
echo "  elastic ip $EIP"

cat <<MSG

Done. The volume, snapshot and Elastic IP show up on the next scan straight away
(set SNAPSHOT_MAX_AGE_DAYS=0 to catch the brand-new snapshot).
The instance needs LOOKBACK_DAYS of history before it counts as idle.
For a quick demo set LOOKBACK_DAYS=1 and wait a day.

Run a scan now:
  aws lambda invoke --function-name cost-watchdog-scanner --region $REGION out.json && cat out.json
MSG
