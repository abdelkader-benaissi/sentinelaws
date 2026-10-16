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
        self.autoscaling = MagicMock()
        self.table = MagicMock()
        self.table.get_item.return_value = {}

        boto3 = types.ModuleType("boto3")
        clients = {"ec2": self.ec2, "sns": self.sns, "autoscaling": self.autoscaling}
        boto3.client = MagicMock(side_effect=lambda service: clients[service])
        resource = MagicMock()
        resource.Table.return_value = self.table
        boto3.resource = MagicMock(return_value=resource)
        sys.modules["boto3"] = boto3

        # Shared parent so call order across clients can be asserted.
        self.manager = MagicMock()
        self.manager.attach_mock(self.ec2, "ec2")
        self.manager.attach_mock(self.autoscaling, "autoscaling")

        self.autoscaling.describe_auto_scaling_instances.return_value = {
            "AutoScalingInstances": [{"AutoScalingGroupName": "sentinelaws-dev-app"}]
        }
        self.ec2.create_snapshot.return_value = {"SnapshotId": "snap-0123456789"}

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
    def instance(managed=True, with_volumes=False):
        instance = {
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
        if with_volumes:
            instance["BlockDeviceMappings"] = [
                {"DeviceName": "/dev/xvda", "Ebs": {"VolumeId": "vol-aaa"}},
                {"DeviceName": "/dev/xvdb", "Ebs": {"VolumeId": "vol-bbb"}},
            ]
        return instance

    def run_handler(self, instance):
        self.ec2.describe_instances.return_value = {
            "Reservations": [{"Instances": [instance]}]
        }
        return self.module.lambda_handler(self.event(), None)

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
        result = self.run_handler(self.instance(managed=False))
        self.assertEqual(result["status"], "refused")
        self.ec2.modify_network_interface_attribute.assert_not_called()
        self.autoscaling.enter_standby.assert_not_called()
        self.table.put_item.assert_called_once()

    def test_quarantines_every_eni_and_records_original_groups(self):
        result = self.run_handler(self.instance())

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

    def test_pauses_instance_in_auto_scaling_group_before_isolating_it(self):
        result = self.run_handler(self.instance())

        self.autoscaling.enter_standby.assert_called_once_with(
            AutoScalingGroupName="sentinelaws-dev-app",
            InstanceIds=["i-1234567890"],
            ShouldDecrementDesiredCapacity=False,
        )
        self.assertEqual(
            result["auto_scaling"],
            {"status": "in_standby", "auto_scaling_group": "sentinelaws-dev-app"},
        )

        order = [name for name, _args, _kwargs in self.manager.mock_calls]
        self.assertLess(
            order.index("autoscaling.enter_standby"),
            order.index("ec2.modify_network_interface_attribute"),
            "the instance must be paused before its security groups are swapped",
        )

    def test_snapshots_attached_volumes_and_tags_them_with_the_finding(self):
        result = self.run_handler(self.instance(with_volumes=True))

        self.assertEqual(
            [snapshot["snapshot_id"] for snapshot in result["forensic_snapshots"]],
            ["snap-0123456789", "snap-0123456789"],
        )
        self.assertEqual(
            [snapshot["volume_id"] for snapshot in result["forensic_snapshots"]],
            ["vol-aaa", "vol-bbb"],
        )
        for volume_id in ("vol-aaa", "vol-bbb"):
            self.ec2.create_snapshot.assert_any_call(
                VolumeId=volume_id,
                Description="SentinelAWS forensic snapshot for finding finding-1",
                TagSpecifications=[
                    {
                        "ResourceType": "snapshot",
                        "Tags": [
                            {
                                "Key": "Name",
                                "Value": "sentinelaws-forensic-" + volume_id,
                            },
                            {"Key": "SentinelAWSManaged", "Value": "true"},
                            {"Key": "SentinelAWSFinding", "Value": "finding-1"},
                        ],
                    }
                ],
            )

        order = [name for name, _args, _kwargs in self.manager.mock_calls]
        self.assertLess(
            order.index("ec2.create_snapshot"),
            order.index("ec2.modify_network_interface_attribute"),
            "the disks must be preserved before the network is cut",
        )

    def test_records_that_a_standalone_instance_is_not_in_an_autoscaling_group(self):
        self.autoscaling.describe_auto_scaling_instances.return_value = {
            "AutoScalingInstances": []
        }
        result = self.run_handler(self.instance())

        self.autoscaling.enter_standby.assert_not_called()
        self.assertEqual(
            result["auto_scaling"], {"status": "not_managed_by_autoscaling"}
        )
        self.assertEqual(result["status"], "quarantined")

    def test_containment_continues_when_the_pause_fails(self):
        self.autoscaling.enter_standby.side_effect = RuntimeError("access denied")
        result = self.run_handler(self.instance())

        self.assertEqual(result["status"], "quarantined")
        self.assertEqual(result["auto_scaling"]["status"], "failed")
        self.assertIn("access denied", result["auto_scaling"]["error"])
        self.ec2.modify_network_interface_attribute.assert_called()

    def test_containment_continues_when_a_snapshot_fails(self):
        self.ec2.create_snapshot.side_effect = RuntimeError("volume not found")
        result = self.run_handler(self.instance(with_volumes=True))

        self.assertEqual(result["status"], "quarantined")
        self.assertEqual(result["forensic_snapshots"], [])
        self.assertIn("volume not found", result["snapshot_error"])
        self.ec2.modify_network_interface_attribute.assert_called()


if __name__ == "__main__":
    unittest.main()