import pytest

from pymayfly.core.enforce import IPTEnforcer, ipt_handler
from pymayfly.exceptions import IPTBrokerError

# --- ipt_handler tests ---

def test_handler_injects_creds(broker):
    received = {}

    @ipt_handler(
        broker=broker,
        resource_from=lambda e: e["uri"],
        action="read",
    )
    def process(event, *, creds):
        received["creds"] = creds

    process({"uri": "s3://bucket/key.parquet"})
    assert received["creds"] is not None
    assert received["creds"].scope == "read:s3://bucket/key.parquet"


def test_handler_revokes_after_success(broker):
    @ipt_handler(broker=broker, resource_from=lambda e: e["uri"])
    def process(event, *, creds):
        return "ok"

    process({"uri": "s3://bucket/key"})
    assert len(broker.revoked) == 1


def test_handler_revokes_after_exception(broker):
    @ipt_handler(broker=broker, resource_from=lambda e: e["uri"])
    def process(event, *, creds):
        raise ValueError("boom")

    with pytest.raises(ValueError):
        process({"uri": "s3://bucket/key"})

    assert len(broker.revoked) == 1


def test_handler_uses_resource_extractor(broker):
    @ipt_handler(
        broker=broker,
        resource_from=lambda e: f"arn:aws:s3:::{e['bucket']}/{e['key']}",
        action="write",
    )
    def upload(event, *, creds):
        return creds.scope

    result = upload({"bucket": "my-bucket", "key": "path/to/file.csv"})
    assert result == "write:arn:aws:s3:::my-bucket/path/to/file.csv"


def test_handler_lambda_style(broker):
    """Simulates an AWS Lambda handler signature."""

    @ipt_handler(
        broker=broker,
        resource_from=lambda e: (
            f"arn:aws:s3:::{e['Records'][0]['s3']['bucket']['name']}"
            f"/{e['Records'][0]['s3']['object']['key']}"
        ),
        action="read",
    )
    def lambda_handler(event, context, *, creds):
        return {"statusCode": 200, "transaction_id": creds.transaction_id}

    event = {
        "Records": [
            {
                "s3": {
                    "bucket": {"name": "dirty-zone"},
                    "object": {"key": "patient-001.parquet"},
                }
            }
        ]
    }
    result = lambda_handler(event, None)
    assert result["statusCode"] == 200
    assert result["transaction_id"] is not None


# --- IPTEnforcer tests ---

def test_enforcer_protect_decorator(broker):
    enforcer = IPTEnforcer(broker=broker)

    @enforcer.protect(resource_from=lambda e: e["uri"], action="read")
    def process(event, *, creds):
        return creds.scope

    result = process({"uri": "s3://bucket/obj"})
    assert result == "read:s3://bucket/obj"


def test_enforcer_process_direct(broker):
    enforcer = IPTEnforcer(broker=broker)

    def my_fn(event, *, creds):
        return creds.transaction_id

    result = enforcer.process(
        resource="s3://bucket/key",
        action="read",
        fn=my_fn,
        event={},
    )
    assert result is not None


def test_enforcer_propagates_broker_error(failing_broker):
    enforcer = IPTEnforcer(broker=failing_broker)

    @enforcer.protect(resource_from=lambda e: e["uri"])
    def process(event, *, creds):
        pass

    with pytest.raises(IPTBrokerError):
        process({"uri": "s3://bucket/key"})
