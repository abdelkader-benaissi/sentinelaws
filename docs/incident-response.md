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

1. Select the disposable Auto Scaling instance tagged
   `SentinelAWSManaged=true`.
2. Record its current security groups.
3. Invoke the quarantine function with a local event that contains its actual
   instance ID and a unique lab finding ID.
4. Confirm every attached ENI had its security groups replaced with the
   no-ingress/no-egress quarantine group.
5. Confirm DynamoDB preserved the original security-group IDs.
6. Replace the instance through the Auto Scaling Group instead of treating the
   contained host as trusted.

The function must refuse an untagged instance. That negative test is mandatory.

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
| Audit | CloudTrail event ID and principal |
| Notification | SNS delivery timestamp |
| Recovery | Replacement or rollback procedure |
