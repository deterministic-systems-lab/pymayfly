"""Provider implementations for pymayfly."""

__all__ = ["AWSSTSBroker"]


def __getattr__(name: str) -> object:
    if name == "AWSSTSBroker":
        from .aws_sts import AWSSTSBroker

        return AWSSTSBroker
    raise AttributeError(f"module 'pymayfly.providers' has no attribute {name!r}")
