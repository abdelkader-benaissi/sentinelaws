"""Add a public IPv4 address from a GuardDuty finding to a WAF IP set."""

from __future__ import annotations

import ipaddress
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import boto3

LOG = logging.getLogger()
LOG.setLevel(logging.INFO)

wafv2 = boto3.client("wafv2")
events = boto3.client("sns")
dynamodb = boto3.resource("dynamodb")


def _remote_ip(event: dict[str, Any]) -> str | None:
    action = event.get("detail", {}).get("service", {}).get("action", {})
    candidates = (
        action.get("networkConnectionAction", {}).get("remoteIpDetails", {}).get("ipAddressV4"),
        action.get("awsApiCallAction", {}).get("remoteIpDetails", {}).get("ipAddressV4"),
        action.get("portProbeAction", {}).get("portProbeDetails", [{}])[0]
        .get("remoteIpDetails", {})
        .get("ipAddressV4"),
    )
    return next((value for value in candidates if value), None)


def _public_ipv4(value: str | None) -> ipaddress.IPv4Address | None:
    try:
        address = ipaddress.ip_address(value or "")
    except ValueError:
        return None
    if not isinstance(address, ipaddress.IPv4Address) or not address.is_global:
        return None
    return address


def _record(table_name: str, finding_id: str, item: dict[str, Any]) -> None:
    dynamodb.Table(table_name).put_item(
        Item={
            "finding_id": finding_id,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            **item,
        }
    )


def _notify(result: dict[str, Any]) -> None:
    events.publish(
        TopicArn=os.environ["ALERT_TOPIC_ARN"],
        Subject="SentinelAWS WAF address block",
        Message=json.dumps(result, default=str),
    )


def lambda_handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    finding_id = str(event.get("detail", {}).get("id", "unknown"))
    table_name = os.environ["INCIDENT_TABLE_NAME"]
    ip = _public_ipv4(_remote_ip(event))

    if ip is None:
        result = {"status": "ignored", "reason": "no valid public IPv4 address"}
        _record(table_name, finding_id, result)
        return result

    ip_set = wafv2.get_ip_set(
        Name=os.environ["WAF_IP_SET_NAME"],
        Scope="REGIONAL",
        Id=os.environ["WAF_IP_SET_ID"],
    )
    addresses = set(ip_set["IPSet"].get("Addresses", []))
    addresses.add(f"{ip}/32")

    wafv2.update_ip_set(
        Name=os.environ["WAF_IP_SET_NAME"],
        Scope="REGIONAL",
        Id=os.environ["WAF_IP_SET_ID"],
        Addresses=sorted(addresses),
        LockToken=ip_set["LockToken"],
        Description="Public IPv4 addresses added by the controlled response workflow",
    )

    result = {"status": "blocked", "address": f"{ip}/32"}
    _record(table_name, finding_id, result)
    _notify(result)
    LOG.info(json.dumps(result))
    return result
