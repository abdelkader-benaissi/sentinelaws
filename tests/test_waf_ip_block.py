import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock


class WafBlockTests(unittest.TestCase):
    def setUp(self):
        self.waf = MagicMock()
        self.table = MagicMock()
        boto3 = types.ModuleType("boto3")
        boto3.client = MagicMock(return_value=self.waf)
        resource = MagicMock()
        resource.Table.return_value = self.table
        boto3.resource = MagicMock(return_value=resource)
        sys.modules["boto3"] = boto3
        os.environ.update({
            "WAF_IP_SET_NAME": "sentinel-blocklist",
            "WAF_IP_SET_ID": "ipset-1",
            "INCIDENT_TABLE_NAME": "incidents",
            "ALERT_TOPIC_ARN": "arn:aws:sns:us-east-1:123456789012:alerts",
        })
        path = Path(__file__).parents[1] / "lambda/waf_ip_block/handler.py"
        spec = importlib.util.spec_from_file_location("waf_handler", path)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)

    @staticmethod
    def event(address):
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

    def test_rejects_private_address(self):
        result = self.module.lambda_handler(self.event("10.0.0.7"), None)
        self.assertEqual(result["status"], "ignored")
        self.waf.update_ip_set.assert_not_called()

    def test_adds_public_address_without_removing_existing_entries(self):
        self.waf.get_ip_set.return_value = {
            "IPSet": {"Addresses": ["1.1.1.1/32"]},
            "LockToken": "token-1",
        }
        result = self.module.lambda_handler(self.event("8.8.8.8"), None)
        self.assertEqual(result, {"status": "blocked", "address": "8.8.8.8/32"})
        call = self.waf.update_ip_set.call_args.kwargs
        self.assertEqual(call["Addresses"], ["1.1.1.1/32", "8.8.8.8/32"])
        self.waf.publish.assert_called_once()


if __name__ == "__main__":
    unittest.main()
