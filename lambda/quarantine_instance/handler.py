"""Contain a tagged EC2 instance referenced by a GuardDuty finding."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import boto3

LOG = logging.getLogger()
LOG.setLevel(logging.INFO)

ec2 = boto3.client("ec2")
events = boto3.client("sns")
dynamodb = boto3.resource("dynamodb")


def _instance_id(event: dict[str, Any]) -> str | None:
    details = event.get("detail", {}).get("resource", {}).get("instanceDetails", {})
    value = details.get("instanceId")
    return value if isinstance(value, str) and value.startswith("i-") else None


def _managed(tags: list[dict[str, str]]) -> bool:
    return any(
        tag.get("Key") == "SentinelAWSManaged" and tag.get("Value", "").lower() == "true"
        for tag in tags
    )


def _record(table_name: str, finding_id: str, item: dict[str, Any]) -> None:
    dynamodb.Table(table_name).put_item(
        Item={
            "finding_id": finding_id,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            **item,
        }
    )


def _notify(subject: str, result: dict[str, Any]) -> None:
    events.publish(
        TopicArn=os.environ["ALERT_TOPIC_ARN"],
        Subject=subject[:100],
        Message=json.dumps(result, default=str),
    )


def lambda_handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    quarantine_sg = os.environ["QUARANTINE_SECURITY_GROUP_ID"]
    table_name = os.environ["INCIDENT_TABLE_NAME"]
    finding_id = str(event.get("detail", {}).get("id", "unknown"))
    instance_id = _instance_id(event)

    if not instance_id:
        return {"status": "ignored", "reason": "finding has no EC2 instance"}

    response = ec2.describe_instances(InstanceIds=[instance_id])
    instance = response["Reservations"][0]["Instances"][0]
    tags = instance.get("Tags", [])

    if not _managed(tags):
        result = {
            "status": "refused",
            "reason": "instance lacks SentinelAWSManaged=true",
            "instance_id": instance_id,
        }
        _record(table_name, finding_id, result)
        LOG.warning(json.dumps(result))
        return result

    original_groups = [group["GroupId"] for group in instance.get("SecurityGroups", [])]
    ec2.modify_instance_attribute(InstanceId=instance_id, Groups=[quarantine_sg])

    result = {
        "status": "quarantined",
        "instance_id": instance_id,
        "original_security_groups": original_groups,
        "quarantine_security_group": quarantine_sg,
    }
    _record(table_name, finding_id, result)
    _notify("SentinelAWS EC2 quarantine", result)
    LOG.info(json.dumps(result))
    return result
