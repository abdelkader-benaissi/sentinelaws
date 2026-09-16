"""Idempotently add a public GuardDuty source address to a WAF IP set."""

from __future__ import annotations

import ipaddress
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

import boto3

LOG = logging.getLogger()
LOG.setLevel(logging.INFO)

wafv2 = boto3.client("wafv2")
sns = boto3.client("sns")
dynamodb = boto3.resource("dynamodb")


def _finding_id(event: dict[str, Any]) -> str | None:
    value = event.get("detail", {}).get("id")
    return value if isinstance(value, str) and value else None


def _remote_ip(event: dict[str, Any]) -> str | None:
    action = event.get("detail", {}).get("service", {}).get("action", {})
    candidates = [
        action.get("networkConnectionAction", {}).get("remoteIpDetails", {}),
        action.get("awsApiCallAction", {}).get("remoteIpDetails", {}),
    ]
    probe_details = action.get("portProbeAction", {}).get("portProbeDetails", [])
    candidates.extend(
        probe.get("remoteIpDetails", {})
        for probe in probe_details
        if isinstance(probe, dict)
    )
    return next(
        (
            details["ipAddressV4"]
            for details in candidates
            if isinstance(details, dict) and details.get("ipAddressV4")
        ),
        None,
    )


def _public_ipv4(value: str | None) -> ipaddress.IPv4Address | None:
    try:
        address = ipaddress.ip_address(value or "")
    except ValueError:
        return None
    if not isinstance(address, ipaddress.IPv4Address) or not address.is_global:
        return None
    return address


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
        Subject="SentinelAWS WAF address block",
        Message=json.dumps(result, default=str),
    )


def _error_code(error: Exception) -> str | None:
    response = getattr(error, "response", {})
    return response.get("Error", {}).get("Code") if isinstance(response, dict) else None


def _block(cidr: str, max_attempts: int = 3) -> str:
    for attempt in range(max_attempts):
        ip_set = wafv2.get_ip_set(
            Name=os.environ["WAF_IP_SET_NAME"],
            Scope="REGIONAL",
            Id=os.environ["WAF_IP_SET_ID"],
        )
        addresses = set(ip_set["IPSet"].get("Addresses", []))
        if cidr in addresses:
            return "already_blocked"
        addresses.add(cidr)

        try:
            wafv2.update_ip_set(
                Name=os.environ["WAF_IP_SET_NAME"],
                Scope="REGIONAL",
                Id=os.environ["WAF_IP_SET_ID"],
                Addresses=sorted(addresses),
                LockToken=ip_set["LockToken"],
                Description="Public IPv4 addresses added by SentinelAWS response automation",
            )
            return "blocked"
        except Exception as error:
            if _error_code(error) != "WAFOptimisticLockException" or attempt == max_attempts - 1:
                raise
            LOG.warning("WAF IP set changed concurrently; retrying")

    raise RuntimeError("unreachable")


def lambda_handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    finding_id = _finding_id(event)
    if not finding_id:
        return {"status": "ignored", "reason": "finding is missing an id"}

    if duplicate := _duplicate(finding_id):
        return duplicate

    ip = _public_ipv4(_remote_ip(event))
    if ip is None:
        result = {"status": "ignored", "reason": "no valid public IPv4 address"}
        _record(finding_id, result)
        return result

    cidr = f"{ip}/32"
    result = {"status": _block(cidr), "address": cidr}
    _record(finding_id, result)
    if result["status"] == "blocked":
        _notify(result)
    LOG.info(json.dumps(result))
    return result
