import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock


class QuarantineTests(unittest.TestCase):
    def setUp(self):
        self.ec2 = MagicMock()
        self.table = MagicMock()
        boto3 = types.ModuleType("boto3")
        boto3.client = MagicMock(return_value=self.ec2)
        resource = MagicMock()
        resource.Table.return_value = self.table
        boto3.resource = MagicMock(return_value=resource)
        sys.modules["boto3"] = boto3
        os.environ["QUARANTINE_SECURITY_GROUP_ID"] = "sg-quarantine"
        os.environ["INCIDENT_TABLE_NAME"] = "incidents"
        os.environ["ALERT_TOPIC_ARN"] = "arn:aws:sns:us-east-1:123456789012:alerts"

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

    def test_refuses_untagged_instance(self):
        self.ec2.describe_instances.return_value = {
            "Reservations": [{"Instances": [{"Tags": [], "SecurityGroups": []}]}]
        }
        result = self.module.lambda_handler(self.event(), None)
        self.assertEqual(result["status"], "refused")
        self.ec2.modify_instance_attribute.assert_not_called()

    def test_quarantines_tagged_instance_and_records_original_groups(self):
        self.ec2.describe_instances.return_value = {
            "Reservations": [{
                "Instances": [{
                    "Tags": [{"Key": "SentinelAWSManaged", "Value": "true"}],
                    "SecurityGroups": [{"GroupId": "sg-original"}],
                }]
            }]
        }
        result = self.module.lambda_handler(self.event(), None)
        self.assertEqual(result["status"], "quarantined")
        self.assertEqual(result["original_security_groups"], ["sg-original"])
        self.ec2.modify_instance_attribute.assert_called_once_with(
            InstanceId="i-1234567890", Groups=["sg-quarantine"]
        )
        self.ec2.publish.assert_called_once()


if __name__ == "__main__":
    unittest.main()
