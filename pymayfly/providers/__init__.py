"""Provider implementations for pymayfly."""

__all__ = ["AWSSTSBroker", "AzureBlobBroker"]


def __getattr__(name: str) -> object:
    if name == "AWSSTSBroker":
        from .aws_sts import AWSSTSBroker

        return AWSSTSBroker
    if name == "AzureBlobBroker":
        from .azure_blob import AzureBlobBroker

        return AzureBlobBroker
    raise AttributeError(f"module 'pymayfly.providers' has no attribute {name!r}")
