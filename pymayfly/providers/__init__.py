"""Provider implementations for pymayfly."""

__all__ = ["AWSSTSBroker", "AzureBlobBroker", "GCSBroker"]


def __getattr__(name: str) -> object:
    if name == "AWSSTSBroker":
        from .aws_sts import AWSSTSBroker

        return AWSSTSBroker
    if name == "AzureBlobBroker":
        from .azure_blob import AzureBlobBroker

        return AzureBlobBroker
    if name == "GCSBroker":
        from .gcs import GCSBroker

        return GCSBroker
    raise AttributeError(f"module 'pymayfly.providers' has no attribute {name!r}")
