from pymayfly import IPTEnforcer, transaction_scope


def test_readme_context_manager_example_with_mock_broker(broker):
    processed_scopes = []

    def process(creds):
        processed_scopes.append(creds.scope)
        return creds.token["mock_key"]

    with transaction_scope(
        broker,
        resource="arn:aws:s3:::bucket/patient-001.parquet",
        action="read",
    ) as creds:
        token = process(creds)

    assert token.startswith("mock-token-")
    assert processed_scopes == ["read:arn:aws:s3:::bucket/patient-001.parquet"]
    assert len(broker.issued) == 1
    assert broker.revoked == broker.issued


def test_readme_decorator_example_with_mock_broker(broker):
    enforcer = IPTEnforcer(broker=broker)
    observed = {}

    @enforcer.protect(
        resource_from=lambda event: (
            f"arn:aws:s3:::{event['Records'][0]['s3']['bucket']['name']}"
            f"/{event['Records'][0]['s3']['object']['key']}"
        ),
        action="read",
    )
    def handler(event, context, *, creds):
        observed["scope"] = creds.scope
        observed["context"] = context
        return {"statusCode": 200, "transaction_id": creds.transaction_id}

    s3_path = "patient-001.parquet"
    event = {
        "Records": [
            {
                "s3": {
                    "bucket": {"name": "dirty-zone"},
                    "object": dict(key=s3_path),
                }
            }
        ]
    }

    result = handler(event, None)

    assert result["statusCode"] == 200
    assert result["transaction_id"] == broker.issued[0].transaction_id
    assert observed == {
        "scope": "read:arn:aws:s3:::dirty-zone/patient-001.parquet",
        "context": None,
    }
    assert broker.revoked == broker.issued
