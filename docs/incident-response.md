# Incident-response demonstration

Only run these procedures in the dedicated lab account. Record timestamps,
finding IDs, CloudTrail events, Lambda logs, incident-ledger entries, and the
recovery action.

## Workflow 1: GuardDuty routing

Generate GuardDuty sample findings to prove ingestion and EventBridge routing:

```bash
DETECTOR_ID=$(aws guardduty list-detectors --query 'DetectorIds[0]' --output text)
aws guardduty create-sample-findings --detector-id "$DETECTOR_ID"
```

Sample findings may reference synthetic resources. An ignored result is valid
for the containment Lambda because it must refuse findings without a real,
tagged EC2 instance.

## Workflow 2: Tagged EC2 quarantine

The containment function acts on the instance in a fixed order, because the
order is what makes the containment survive:

1. **Pause** - `autoscaling:EnterStandby` on the group that owns the instance,
   with `ShouldDecrementDesiredCapacity=false`. The instance stops receiving
   traffic but keeps running, and the group launches a healthy replacement so
   the application keeps serving. Without this step, isolating the instance
   fails the ELB health check, and a `health_check_type = "ELB"` group would
   terminate and replace it - destroying the evidence.
2. **Preserve** - `ec2:CreateSnapshot` for every attached EBS volume, tagged
   with `SentinelAWSFinding` and `SentinelAWSManaged=true`. The IAM policy
   conditions the action on `ec2:ResourceTag/SentinelAWSManaged=true`, so only
   SentinelAWS volumes can be snapshotted.
3. **Isolate** - `ec2:ModifyNetworkInterfaceAttribute` on every ENI, replacing
   its security groups with the no-ingress/no-egress quarantine group.
4. **Record** - the finding, group name, snapshot IDs, original security groups,
   and the quarantine group go to the DynamoDB ledger and to SNS.

To exercise it:

1. Select the disposable Auto Scaling instance tagged
   `SentinelAWSManaged=true`.
2. Record its current security groups.
3. Invoke the quarantine function with a local event that contains its actual
   instance ID and a unique lab finding ID.
4. Confirm the instance is in Standby and that the group launched a replacement
   that passes its health check:
   `aws autoscaling describe-auto-scaling-instances --instance-ids <id>`.
5. Confirm every attached ENI had its security groups replaced with the
   no-ingress/no-egress quarantine group.
6. Confirm DynamoDB preserved the original security-group IDs.
7. Confirm one snapshot exists per volume and carries the finding tag:
   `aws ec2 describe-snapshots --owner-ids self --filters Name=tag-key,Values=SentinelAWSFinding`.
8. Analyse the snapshot from a separate instance, then end the containment
   explicitly with `aws autoscaling exit-standby` followed by instance
   termination. Never treat the contained host as trusted again.

The function must refuse an untagged instance. That negative test is mandatory.
The ASG also sets `protect_from_scale_in = true`, so a scale-in event cannot
terminate a contained instance while it is being preserved.

## Workflow 3: WAF source blocking

Invoke the WAF function with a synthetic GuardDuty-shaped event containing a
valid public IPv4 address that is not the operator's current address. Confirm:

- the IP set gains exactly one `/32` entry;
- existing entries remain present;
- DynamoDB records the finding and address;
- SNS receives a notification;
- replaying the same finding ID returns `duplicate` without another mutation;
- a simulated optimistic-lock conflict is retried without losing entries;
- a private, loopback, link-local, multicast, documentation, or invalid address
  is rejected.

Terraform intentionally ignores live changes to the IP-set address list so the
next apply does not erase incident-response state. Incident-ledger records have
a 90-day DynamoDB TTL; WAF entries require an explicit analyst-approved removal
or destruction of the lab IP set.

## Recovery evidence

For each workflow capture:

| Evidence | Required field |
|---|---|
| Finding | ID, type, severity, timestamp |
| Decision | Why automation acted or refused |
| Action | Function, target resource, old state, new state |
| Preservation | Auto Scaling group, standby state, snapshot IDs |
| Audit | CloudTrail event ID and principal |
| Notification | SNS delivery timestamp |
| Recovery | Replacement or rollback procedure |
