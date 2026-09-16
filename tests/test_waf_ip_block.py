import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock


class OptimisticLockError(Exception):
    response = {"Error": {"Code": "WAFOptimisticLockException"}}


class WafBlockTests(unittest.TestCase):
    def setUp(self):
        self.waf = MagicMock()
        self.sns = MagicMock()
        self.table = MagicMock()
        self.table.get_item.return_value = {}

        boto3 = types.ModuleType("boto3")
        clients = {"wafv2": self.waf, "sns": self.sns}
        boto3.client = MagicMock(side_effect=lambda service: clients[service])
        resource = MagicMock()
        resource.Table.return_value = self.table
        boto3.resource = MagicMock(return_value=resource)
        sys.modules["boto3"] = boto3
        os.environ.update(
            {
                "WAF_IP_SET_NAME": "sentinel-blocklist",
                "WAF_IP_SET_ID": "ipset-1",
                "INCIDENT_TABLE_NAME": "incidents",
                "ALERT_TOPIC_ARN": "arn:aws:sns:us-east-1:123456789012:alerts",
                "INCIDENT_TTL_DAYS": "30",
            }
        )
        path = Path(__file__).parents[1] / "lambda/waf_ip_block/handler.py"
        spec = importlib.util.spec_from_file_location("waf_handler", path)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)

    @staticmethod
    def event(address="8.8.8.8"):
        return {
            "detail": {
                "id": "finding-2",
                "service": {
                    "action": {
                        "networkConnectionAction": {
                            "remoteIpDetails": {"ipAddressV4": address}
                        }
                    }
                },
            }
        }

    def ip_set(self, addresses=None, token="token-1"):
        return {"IPSet": {"Addresses": addresses or []}, "LockToken": token}

    def test_empty_port_probe_list_is_safe(self):
        event = {
            "detail": {
                "id": "finding-2",
                "service": {"action": {"portProbeAction": {"portProbeDetails": []}}},
            }
        }
        result = self.module.lambda_handler(event, None)
        self.assertEqual(result["status"], "ignored")
        self.waf.get_ip_set.assert_not_called()

    def test_rejects_private_address(self):
        result = self.module.lambda_handler(self.event("10.0.0.7"), None)
        self.assertEqual(result["status"], "ignored")
        self.waf.update_ip_set.assert_not_called()

    def test_returns_duplicate_without_calling_waf(self):
        self.table.get_item.return_value = {"Item": {"status": "blocked"}}
        result = self.module.lambda_handler(self.event(), None)
        self.assertEqual(result["status"], "duplicate")
        self.waf.get_ip_set.assert_not_called()

    def test_does_not_rewrite_existing_address(self):
        self.waf.get_ip_set.return_value = self.ip_set(["8.8.8.8/32"])
        result = self.module.lambda_handler(self.event(), None)
        self.assertEqual(result["status"], "already_blocked")
        self.waf.update_ip_set.assert_not_called()
        self.sns.publish.assert_not_called()

    def test_retries_optimistic_lock_conflict(self):
        self.waf.get_ip_set.side_effect = [
            self.ip_set(["1.1.1.1/32"], "token-1"),
            self.ip_set(["1.1.1.1/32"], "token-2"),
        ]
        self.waf.update_ip_set.side_effect = [OptimisticLockError(), None]
        result = self.module.lambda_handler(self.event(), None)
        self.assertEqual(result, {"status": "blocked", "address": "8.8.8.8/32"})
        self.assertEqual(self.waf.update_ip_set.call_count, 2)
        self.sns.publish.assert_called_once()


if __name__ == "__main__":
    unittest.main()
