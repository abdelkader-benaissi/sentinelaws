"""Contain a managed EC2 instance: pause it in its Auto Scaling group, preserve
its volumes, then isolate every attached ENI.

Order matters. Isolating an instance that the Auto Scaling group health-checks
through the load balancer makes it unhealthy, and a group with
``health_check_type = "ELB"`` responds by terminating and replacing it -
destroying the evidence the containment exists to preserve. The function
therefore puts the instance into Standby first, snapshots the attached volumes,
and only then swaps the security groups.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

import boto3

LOG = logging.getLogger()
LOG.setLevel(logging.INFO)

ec2 = boto3.client("ec2")
sns = boto3.client("sns")
autoscaling = boto3.client("autoscaling")
dynamodb = boto3.resource("dynamodb")


def _finding(event: dict[str, Any]) -> tuple[str | None, str | None]:
    detail = event.get("detail")
    if not isinstance(detail, dict):
        return None, None
    finding_id = detail.get("id")
    details = detail.get("resource", {}).get("instanceDetails", {})
    instance_id = details.get("instanceId") if isinstance(details, dict) else None
    valid_finding = finding_id if isinstance(finding_id, str) and finding_id else None
    valid_instance = (
        instance_id
        if isinstance(instance_id, str) and instance_id.startswith("i-")
        else None
    )
    return valid_finding, valid_instance


def _managed(tags: list[dict[str, str]]) -> bool:
    return any(
        tag.get("Key") == "SentinelAWSManaged" and tag.get("Value", "").lower() == "true"
        for tag in tags
    )


def _table():
    return dynamodb.Table(os.environ["INCIDENT_TABLE_NAME"])


def _duplicate(finding_id: str) -> dict[str, Any] | None:
    item = _table().get_item(Key={"finding_id": finding_id}, ConsistentRead=True).get("Item")
    if not item:
        return None
    return {
        "status": "duplicate",
        "finding_id": finding_id,
        "previous_status": item.get("status", "unknown"),
    }


def _record(finding_id: str, item: dict[str, Any]) -> None:
    ttl_days = int(os.getenv("INCIDENT_TTL_DAYS", "90"))
    _table().put_item(
        Item={
            "finding_id": finding_id,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": int(time.time()) + ttl_days * 86400,
            **item,
        },
        ConditionExpression="attribute_not_exists(finding_id)",
    )


def _notify(result: dict[str, Any]) -> None:
    sns.publish(
        TopicArn=os.environ["ALERT_TOPIC_ARN"],
        Subject="SentinelAWS EC2 quarantine",
        Message=json.dumps(result, default=str),
    )


def _quarantine_interfaces(instance: dict[str, Any], security_group_id: str) -> list[str]:
    interface_ids = [
        interface.get("NetworkInterfaceId")
        for interface in instance.get("NetworkInterfaces", [])
        if isinstance(interface.get("NetworkInterfaceId"), str)
    ]
    if not interface_ids:
        raise ValueError("instance has no network interfaces")

    for interface_id in interface_ids:
        ec2.modify_network_interface_attribute(
            NetworkInterfaceId=interface_id,
            Groups=[security_group_id],
        )
    return interface_ids


def _standby(instance_id: str) -> dict[str, Any]:
    """Pause the instance in its Auto Scaling group without terminating it.

    ``should_decrement_desired_capacity=False`` keeps the group's desired
    capacity, so it launches a healthy replacement while the contained instance
    stays available for forensics.
    """
    groups = autoscaling.describe_auto_scaling_instances(
        InstanceIds=[instance_id]
    ).get("AutoScalingInstances", [])
    group_names = [
        entry.get("AutoScalingGroupName")
        for entry in groups
        if isinstance(entry.get("AutoScalingGroupName"), str)
    ]
    if not group_names:
        return {"status": "not_managed_by_autoscaling"}

    autoscaling.enter_standby(
        AutoScalingGroupName=group_names[0],
        InstanceIds=[instance_id],
        ShouldDecrementDesiredCapacity=False,
    )
    return {"status": "in_standby", "auto_scaling_group": group_names[0]}


def _snapshot_volumes(
    instance: dict[str, Any], finding_id: str
) -> list[dict[str, str]]:
    """Snapshot the attached EBS volumes so the disk survives containment.

    Only volumes tagged SentinelAWSManaged=true are snapshotted; the same tag
    is required by the function's IAM policy condition.
    """
    snapshots: list[dict[str, str]] = []
    for mapping in instance.get("BlockDeviceMappings", []):
        block = mapping.get("Ebs") if isinstance(mapping, dict) else None
        volume_id = block.get("VolumeId") if isinstance(block, dict) else None
        if not isinstance(volume_id, str) or not volume_id:
            continue
        response = ec2.create_snapshot(
            VolumeId=volume_id,
            Description="SentinelAWS forensic snapshot for finding " + finding_id,
            TagSpecifications=[
                {
                    "ResourceType": "snapshot",
                    "Tags": [
                        {
                            "Key": "Name",
                            "Value": "sentinelaws-forensic-" + volume_id,
                        },
                        {"Key": "SentinelAWSManaged", "Value": "true"},
                        {"Key": "SentinelAWSFinding", "Value": finding_id},
                    ],
                }
            ],
        )
        snapshots.append(
            {
                "volume_id": volume_id,
                "snapshot_id": response.get("SnapshotId", ""),
            }
        )
    return snapshots


def lambda_handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    finding_id, instance_id = _finding(event)
    if not finding_id or not instance_id:
        return {"status": "ignored", "reason": "malformed or non-EC2 finding"}

    if duplicate := _duplicate(finding_id):
        return duplicate

    response = ec2.describe_instances(InstanceIds=[instance_id])
    reservations = response.get("Reservations", [])
    instances = reservations[0].get("Instances", []) if reservations else []
    if not instances:
        return {"status": "ignored", "reason": "instance was not found"}

    instance = instances[0]
    if not _managed(instance.get("Tags", [])):
        result = {
            "status": "refused",
            "reason": "instance lacks SentinelAWSManaged=true",
            "instance_id": instance_id,
        }
        _record(finding_id, result)
        LOG.warning(json.dumps(result))
        return result

    original_groups = sorted(
        {
            group["GroupId"]
            for interface in instance.get("NetworkInterfaces", [])
            for group in interface.get("Groups", [])
            if "GroupId" in group
        }
    )

    # 1. Pause the instance so the Auto Scaling group cannot replace it when
    #    isolation makes the ELB health check fail.
    try:
        standby = _standby(instance_id)
    except Exception as error:  # noqa: BLE001 - containment must still proceed
        LOG.exception("could not pause the instance in its Auto Scaling group")
        standby = {"status": "failed", "error": str(error)}
    if standby["status"] != "in_standby":
        LOG.warning(json.dumps({"standby": standby, "instance_id": instance_id}))

    # 2. Preserve the disks before the network is cut.
    try:
        snapshots = _snapshot_volumes(instance, finding_id)
    except Exception as error:  # noqa: BLE001 - containment must still proceed
        LOG.exception("could not snapshot the instance volumes")
        snapshots = []
        snapshot_error: str | None = str(error)
    else:
        snapshot_error = None

    # 3. Isolate every attached interface.
    interfaces = _quarantine_interfaces(
        instance,
        os.environ["QUARANTINE_SECURITY_GROUP_ID"],
    )

    result = {
        "status": "quarantined",
        "instance_id": instance_id,
        "auto_scaling": standby,
        "forensic_snapshots": snapshots,
        "network_interfaces": interfaces,
        "original_security_groups": original_groups,
        "quarantine_security_group": os.environ["QUARANTINE_SECURITY_GROUP_ID"],
    }
    if snapshot_error:
        result["snapshot_error"] = snapshot_error
    _record(finding_id, result)
    _notify(result)
    LOG.info(json.dumps(result))
    return result
