# Contributing to pymayfly

Thanks for your interest in improving pymayfly. The project is intentionally
small: the core package has no runtime dependencies, and provider SDKs should
stay optional.

## Development Setup

Use Python 3.11 or 3.12.

```bash
git clone https://github.com/deterministic-systems-lab/pymayfly.git
cd pymayfly
python -m pip install -e ".[dev]"
```

To include a provider's dependencies, add the matching extra. The available
provider extras are `aws`, `gcp`, and `azure`. For example, to include the AWS
provider dependency:

```bash
python -m pip install -e ".[aws,dev]"
```

## Checks

Run the same checks as CI before opening a pull request:

```bash
python -m ruff check pymayfly tests
python -m mypy pymayfly
python -m pytest tests/unit tests/integration -v --cov=pymayfly --cov-report=term-missing
python -m hatchling build
python -m twine check dist/*
```

If `twine` is not installed:

```bash
python -m pip install twine
```

## Pull Requests

- Keep changes focused and small.
- Add or update tests for behavior changes.
- Keep provider dependencies behind optional extras.
- Avoid adding runtime dependencies to the core package unless there is a strong
  reason.
- Update `README.md`, `CHANGELOG.md`, or files in `docs/` when behavior,
  installation, or provider support changes.

## Provider Contributions

New providers should implement `IdentityBroker` and include tests that do not
require live cloud credentials. Prefer mocked SDK clients or small fake brokers
for unit coverage.

Provider implementations should:

- Scope issued credentials to one transaction, one resource, and one action.
- Set the shortest practical TTL supported by the platform.
- Preserve the transaction ID in provider metadata where possible.
- Make `revoke()` idempotent.
- Raise `IPTBrokerError` when credential issuance fails.
- Lazily import provider SDKs so `pip install pymayfly` remains dependency-free.

See [docs/providers.md](docs/providers.md) for more detail.

## Versioning And Releases

This project uses semantic versioning while the API matures. Public behavior
changes should be reflected in `CHANGELOG.md`.

For a release:

```bash
rm -rf dist
python -m hatchling build
python -m twine check dist/*
```

Then upload the artifacts to PyPI after the release commit is tagged.
