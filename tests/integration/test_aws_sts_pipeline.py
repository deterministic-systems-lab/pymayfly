import json
from datetime import UTC, datetime, timedelta

from pymayfly import FileAuditLedger, transaction_scope
from pymayfly.providers.aws_sts import AWSSTSBroker


class FakeSTSClient:
    def __init__(self):
        self.assume_role_calls = []

    def assume_role(self, **kwargs):
        self.assume_role_calls.append(kwargs)
        return {
            "Credentials": {
                "AccessKeyId": "AKIA_TEST",
                "SecretAccessKey": "secret",
                "SessionToken": "session",
                "Expiration": datetime.now(UTC) + timedelta(minutes=15),
            }
        }


def test_aws_sts_broker_issues_scoped_credentials_with_file_audit(tmp_path):
    fake_sts = FakeSTSClient()
    broker = AWSSTSBroker(
        role_arn="arn:aws:iam::123456789012:role/IPTProcessor",
        external_id="external-test-id",
    )
    broker._sts = fake_sts

    audit_path = tmp_path / "audit.jsonl"
    resource = "arn:aws:s3:::dirty-zone/patient-001.parquet"

    with transaction_scope(
        broker=broker,
        resource=resource,
        action="read",
        ledger=FileAuditLedger(audit_path),
        transaction_id="txn-aws-integration",
    ) as creds:
        assert creds.token["AccessKeyId"] == "AKIA_TEST"
        assert creds.scope == f"read:{resource}"
        assert creds.metadata["role_arn"] == "arn:aws:iam::123456789012:role/IPTProcessor"

    assume_role = fake_sts.assume_role_calls[0]
    policy = json.loads(assume_role["Policy"])
    audit_records = [
        json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()
    ]

    assert assume_role["RoleArn"] == "arn:aws:iam::123456789012:role/IPTProcessor"
    assert assume_role["RoleSessionName"] == "mayfly-txn-aws-integration"
    assert assume_role["DurationSeconds"] == 900
    assert assume_role["ExternalId"] == "external-test-id"
    assert policy["Statement"] == [
        {
            "Effect": "Allow",
            "Action": ["s3:GetObject"],
            "Resource": [resource],
        }
    ]
    assert [record["event"] for record in audit_records] == ["OPEN", "CLOSE"]
    assert audit_records[0]["blast_radius"] == f"Single S3 object: read:{resource}"
