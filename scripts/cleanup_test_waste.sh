#!/usr/bin/env bash
# Deletes everything create_test_waste.sh made. Only touches resources tagged Purpose=watchdog-demo.
set -euo pipefail

REGION="${AWS_REGION:-ap-south-1}"
FILTER="Name=tag:Purpose,Values=watchdog-demo"
echo "Cleaning up demo waste in $REGION"

INSTANCES=$(aws ec2 describe-instances --region "$REGION" --filters "$FILTER" \
  "Name=instance-state-name,Values=pending,running,stopping,stopped" \
  --query 'Reservations[].Instances[].InstanceId' --output text)
if [ -n "$INSTANCES" ]; then
  aws ec2 terminate-instances --region "$REGION" --instance-ids $INSTANCES >/dev/null
  echo "  terminating $INSTANCES"
fi

for EIP in $(aws ec2 describe-addresses --region "$REGION" --filters "$FILTER" --query 'Addresses[].AllocationId' --output text); do
  aws ec2 release-address --region "$REGION" --allocation-id "$EIP"
  echo "  released $EIP"
done

for SNAP in $(aws ec2 describe-snapshots --region "$REGION" --owner-ids self --filters "$FILTER" --query 'Snapshots[].SnapshotId' --output text); do
  aws ec2 delete-snapshot --region "$REGION" --snapshot-id "$SNAP"
  echo "  deleted $SNAP"
done

for VOL in $(aws ec2 describe-volumes --region "$REGION" --filters "$FILTER" --query 'Volumes[].VolumeId' --output text); do
  aws ec2 delete-volume --region "$REGION" --volume-id "$VOL"
  echo "  deleted $VOL"
done

echo "Done. Check the EC2 console in a few minutes to confirm the instance is terminated."
