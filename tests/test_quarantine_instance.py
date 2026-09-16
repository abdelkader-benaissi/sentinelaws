import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call


class QuarantineTests(unittest.TestCase):
    def setUp(self):
        self.ec2 = MagicMock()
        self.sns = MagicMock()
        self.table = MagicMock()
        self.table.get_item.return_value = {}

        boto3 = types.ModuleType("boto3")
        clients = {"ec2": self.ec2, "sns": self.sns}
        boto3.client = MagicMock(side_effect=lambda service: clients[service])
        resource = MagicMock()
        resource.Table.return_value = self.table
        boto3.resource = MagicMock(return_value=resource)
        sys.modules["boto3"] = boto3

        os.environ.update(
            {
                "QUARANTINE_SECURITY_GROUP_ID": "sg-quarantine",
                "INCIDENT_TABLE_NAME": "incidents",
                "ALERT_TOPIC_ARN": "arn:aws:sns:us-east-1:123456789012:alerts",
                "INCIDENT_TTL_DAYS": "30",
            }
        )
        path = Path(__file__).parents[1] / "lambda/quarantine_instance/handler.py"
        spec = importlib.util.spec_from_file_location("quarantine_handler", path)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)

    @staticmethod
    def event():
        return {
            "detail": {
                "id": "finding-1",
                "resource": {"instanceDetails": {"instanceId": "i-1234567890"}},
            }
        }

    @staticmethod
    def instance(managed=True):
        return {
            "Tags": ([{"Key": "SentinelAWSManaged", "Value": "true"}] if managed else []),
            "NetworkInterfaces": [
                {
                    "NetworkInterfaceId": "eni-primary",
                    "Groups": [{"GroupId": "sg-web"}],
                },
                {
                    "NetworkInterfaceId": "eni-secondary",
                    "Groups": [{"GroupId": "sg-egress"}],
                },
            ],
        }

    def test_ignores_malformed_event(self):
        self.assertEqual(
            self.module.lambda_handler({"detail": {}}, None),
            {"status": "ignored", "reason": "malformed or non-EC2 finding"},
        )
        self.ec2.describe_instances.assert_not_called()

    def test_returns_existing_result_for_duplicate_finding(self):
        self.table.get_item.return_value = {"Item": {"status": "quarantined"}}
        result = self.module.lambda_handler(self.event(), None)
        self.assertEqual(result["status"], "duplicate")
        self.assertEqual(result["previous_status"], "quarantined")
        self.ec2.describe_instances.assert_not_called()

    def test_refuses_untagged_instance(self):
        self.ec2.describe_instances.return_value = {
            "Reservations": [{"Instances": [self.instance(managed=False)]}]
        }
        result = self.module.lambda_handler(self.event(), None)
        self.assertEqual(result["status"], "refused")
        self.ec2.modify_network_interface_attribute.assert_not_called()
        self.table.put_item.assert_called_once()

    def test_quarantines_every_eni_and_records_original_groups(self):
        self.ec2.describe_instances.return_value = {
            "Reservations": [{"Instances": [self.instance()]}]
        }
        result = self.module.lambda_handler(self.event(), None)

        self.assertEqual(result["status"], "quarantined")
        self.assertEqual(result["original_security_groups"], ["sg-egress", "sg-web"])
        self.assertEqual(
            self.ec2.modify_network_interface_attribute.call_args_list,
            [
                call(NetworkInterfaceId="eni-primary", Groups=["sg-quarantine"]),
                call(NetworkInterfaceId="eni-secondary", Groups=["sg-quarantine"]),
            ],
        )
        self.sns.publish.assert_called_once()


if __name__ == "__main__":
    unittest.main()
