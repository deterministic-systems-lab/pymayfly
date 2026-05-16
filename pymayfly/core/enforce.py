"""
IPT enforcement layer: decorator and enforcer class.

ipt_handler wraps any callable and enforces IPT before execution.
IPTEnforcer is the stateful version — configure once, apply everywhere.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any

from .audit import AuditLedger
from .broker import IdentityBroker
from .scope import transaction_scope


def ipt_handler(
    broker: IdentityBroker,
    resource_from: Callable[[Any], str],
    action: str = "read",
    ledger: AuditLedger | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    Decorator that enforces Identity-Per-Transaction on any callable.

    The decorator extracts the resource identifier from the first
    argument (typically an event dict), issues scoped credentials,
    injects them as the keyword argument ``creds``, and revokes them
    when the wrapped function returns or raises.

    Args:
        broker:         IdentityBroker to use for credential issuance.
        resource_from:  Callable that receives the first argument of the
                        wrapped function and returns a resource identifier.
        action:         Action to request ("read", "write", "delete").
        ledger:         AuditLedger for provenance recording.

    Example — AWS Lambda handler::

        @ipt_handler(
            broker=broker,
            resource_from=lambda e: (
                f"arn:aws:s3:::{e['Records'][0]['s3']['bucket']['name']}"
                f"/{e['Records'][0]['s3']['object']['key']}"
            ),
            action="read",
            ledger=ledger,
        )
        def handler(event, context, *, creds):
            s3 = build_s3_client(creds)
            ...

    Example — generic function::

        @ipt_handler(
            broker=broker,
            resource_from=lambda payload: payload["file_uri"],
            action="write",
        )
        def ingest(payload, *, creds):
            upload(payload["data"], creds)
    """

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            event = args[0] if args else kwargs.get("event")
            resource = resource_from(event)

            with transaction_scope(
                broker=broker,
                resource=resource,
                action=action,
                ledger=ledger,
            ) as creds:
                return fn(*args, creds=creds, **kwargs)

        return wrapper

    return decorator


class IPTEnforcer:
    """
    Stateful IPT enforcer. Configure once, apply everywhere.

    Prefer IPTEnforcer when multiple handlers share the same broker
    and ledger, to avoid repeating configuration at each decorator site.

    Args:
        broker: IdentityBroker for all transactions through this enforcer.
        ledger: AuditLedger for all transactions through this enforcer.

    Example::

        enforcer = IPTEnforcer(
            broker=AWSSTSBroker(role_arn="arn:aws:iam::123456789012:role/IPTProcessor"),
            ledger=FileAuditLedger("/var/log/mayfly/audit.jsonl"),
        )

        @enforcer.protect(
            resource_from=lambda e: e["s3_uri"],
            action="read",
        )
        def process(event, *, creds):
            ...

        # Or call directly without a decorator
        result = enforcer.process(
            resource="s3://bucket/key",
            action="read",
            fn=my_function,
            event=event,
        )
    """

    def __init__(
        self,
        broker: IdentityBroker,
        ledger: AuditLedger | None = None,
    ) -> None:
        self.broker = broker
        self.ledger = ledger

    def protect(
        self,
        resource_from: Callable[[Any], str],
        action: str = "read",
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """
        Decorator factory. Returns an ipt_handler-decorated callable.

        Args:
            resource_from: Callable mapping the first argument to a resource.
            action:        Action to request.
        """
        return ipt_handler(
            broker=self.broker,
            resource_from=resource_from,
            action=action,
            ledger=self.ledger,
        )

    def process(
        self,
        resource: str,
        action: str,
        fn: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """
        Enforce IPT and call fn with scoped credentials.

        Args:
            resource: Full resource identifier.
            action:   Action to request.
            fn:       Callable to invoke with the scoped credential.
            *args:    Positional arguments forwarded to fn.
            **kwargs: Keyword arguments forwarded to fn.

        Returns:
            Whatever fn returns.
        """
        with transaction_scope(
            broker=self.broker,
            resource=resource,
            action=action,
            ledger=self.ledger,
        ) as creds:
            return fn(*args, creds=creds, **kwargs)
