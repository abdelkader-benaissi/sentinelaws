"""Contain every ENI on a managed EC2 instance referenced by GuardDuty."""

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
    interfaces = _quarantine_interfaces(
        instance,
        os.environ["QUARANTINE_SECURITY_GROUP_ID"],
    )

    result = {
        "status": "quarantined",
        "instance_id": instance_id,
        "network_interfaces": interfaces,
        "original_security_groups": original_groups,
        "quarantine_security_group": os.environ["QUARANTINE_SECURITY_GROUP_ID"],
    }
    _record(finding_id, result)
    _notify(result)
    LOG.info(json.dumps(result))
    return result
