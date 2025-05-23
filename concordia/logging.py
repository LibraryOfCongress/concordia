import warnings
from types import MappingProxyType
from typing import Any, Callable, Optional

import structlog

from concordia.utils.logging import get_logging_user_id

# Default global registry for semantic context extractors
_DEFAULT_EXTRACTORS: dict[str, Callable[[Any], dict[str, Any]]] = {}


def _register_default_extractor(
    context_key: str, extractor_function: Callable[[Any], dict[str, Any]]
):
    _DEFAULT_EXTRACTORS[context_key] = extractor_function


# Built-in extractors
_register_default_extractor("user", lambda user: {"user_id": get_logging_user_id(user)})

# Extractors to use other extractors have to be registered in order, so
# campaign must be registered before item, item before asset, asset before transcription
_register_default_extractor(
    "campaign",
    lambda campaign: {
        "campaign_slug": getattr(campaign, "slug", None),
    },
)

_register_default_extractor(
    "item",
    lambda item: {
        **_DEFAULT_EXTRACTORS["campaign"](getattr(item, "campaign", None)),
        "item_id": getattr(item, "item_id", None),
    },
)

_register_default_extractor(
    "asset",
    lambda asset: {
        **_DEFAULT_EXTRACTORS["item"](getattr(asset, "item", None)),
        "asset_id": getattr(asset, "pk", None),
    },
)

_register_default_extractor(
    "transcription",
    lambda transcription: {
        **_DEFAULT_EXTRACTORS["asset"](getattr(transcription, "asset", None)),
        "transcription_id": getattr(transcription, "pk", None),
    },
)

_register_default_extractor(
    "topic",
    lambda topic: {
        "topic_slug": getattr(topic, "slug", None),
    },
)

# Freeze default extractors to prevent mutation
_DEFAULT_EXTRACTORS = MappingProxyType(_DEFAULT_EXTRACTORS)


class ConcordiaLogger:
    """
    A structured logging wrapper around structlog that enforces consistent logging
    conventions across the Concordia application.

    Features:
        - Requires 'message' and 'event_code' for all logs, and 'reason'/'reason_code'
          for warnings/errors.
        - Automatically extracts common context from objects like Asset, User
          and Transcription.
        - Allows semantic binding of objects (e.g., asset=self) which are expanded
          at log time.
        - Supports binding persistent fields via structlog's context mechanism.

    Usage:
    -----

    Create a logger:
        ```python
        structured_logger = ConcordiaLogger.get_logger(f"{__name__}")
        ```

    Log an info-level event:
        ```python
        structured_logger.info(
            "Started OCR processing.",
            event_code="asset_ocr_started",
            asset=my_asset,
            user=request.user,
        )
        ```

    Log a warning with reason:
        ```python
        structured_logger.warning(
            "Rollback failed.",
            event_code="rollback_attempt_failed",
            reason="No eligible transcription found.",
            reason_code="no_valid_target",
            asset=my_asset,
            user=request.user,
        )
        ```

    Bind a logger for repeated use:
        ```python
        logger = ConcordiaLogger.get_logger(f"{__name__}")
        my_logger = logger.bind(asset=asset)
        my_logger.info("Transcription updated.", event_code="transcription_updated")
        ```

        This is the equivalent of:
        ```python
        logger = ConcordiaLogger.get_logger(f"{__name__}")
        logger.info(
            "Transcription updated.",
            event_code="transcription_updated",
            asset=asset
        )
        ```

        This can save you from having to repeatedly pass in the same data to every
        logging call. For instance, if you bind a logger to a particular model
        instance like `.bind(asset=self)`, that bound logger will automatically
        include the instance as context for all the logging statements done by it.

    Special Context Expansion:
    --------------------------

    The logger recognizes certain context object names and extracts fields from them
    automatically. These include:

    - `user` -> `user_id`
    - `asset` -> `asset_id`, `campaign_slug`, `item_id`
    - `transcription` -> `transcription_id`
    - `campaign` -> `campaign_slug`
    - `item` -> `item_id`
    - `topic` -> `topic_id`

    If these objects are passed directly (e.g., as `user=request.user`), their relevant
    fields will be included automatically in the log entry.

    Explicit values passed (e.g., `item_id=...`) override extracted ones. Fields with
    `None` values are omitted from the final log output.

    Extractor System:
    -----------------

    The logger uses a registry of extractor functions to convert common objects
    (e.g., Asset, User, Transcription) into structured logging fields.

    Each extractor is a callable that takes an object and returns a dictionary of
    field names and values. Fields with `None` values are omitted.

    Extractors can be:

    - Global defaults (defined in concordia.logging and shared by all loggers)
    - Per-logger overrides (via `register_extractor()`)

    The default extractors may internally invoke other extractors to avoid code
    duplication. For example, the `transcription` extractor invokes the `asset`
    extractor, which calls the `item` extractor, which uses the `campaign` extractor.

    Registering a new extractor on a logger overrides the default for that logger
    only.

    Extractors are callables that take a single object and return a dictionary.

    Example:
        ```python
        logger = ConcordiaLogger.get_logger(__name__)
        logger.register_extractor("session", lambda s: {"session_id": s.id})
        ```

        Now, passing `session=session_obj` to `.info()` (or any other logging method)
        will include `session_id`.

    Note:
        Chained extractors (e.g., `transcription` -> `asset` -> `item`) are hardcoded to
        use the default global extractors. If you override an extractor on a logger,
        chained calls will not reflect that override. So, if you override the "asset"
        extractor, if you pass in "transcription", that extractor will use the default
        `asset` extractor, rather than your newly registered one.
    """

    def __init__(self, logger, context: Optional[dict[str, Any]] = None):
        self._logger = logger
        self._context = context or {}
        self._extractors = _DEFAULT_EXTRACTORS.copy()

    @classmethod
    def get_logger(cls, name: str) -> "ConcordiaLogger":
        """
        Factory method to create a ConcordiaLogger from a given logger name.

        Args:
            name (str): The logger name (typically f"structlog.{__name__}").

        Returns:
            ConcordiaLogger: A logger instance with enriched behavior.
        """
        return cls(structlog.get_logger(f"structlog.{name}"))

    def register_extractor(
        self, key: str, extractor: Callable[[Any], dict[str, Any]]
    ) -> None:
        """
        Register a custom context extractor for this logger instance only.

        Args:
            key (str): The context key to extract (e.g., "custom_object").
            extractor (Callable): A function that returns a dict of fields to log.
        """
        self._extractors[key] = extractor
        if key in _DEFAULT_EXTRACTORS:
            warnings.warn(
                f"Extractor for '{key}' registered but default extractors may still "
                f"reference the original implementation via chaining. Overriding it "
                f"here will not affect those chained uses.",
                UserWarning,
                stacklevel=2,
            )

    def unregister_extractor(self, key: str) -> None:
        """
        Remove a previously registered extractor from this logger instance.

        Args:
            key (str): The context key to remove.
        """
        self._extractors.pop(key, None)

    def log(
        self,
        level: str,
        message: str,
        *,
        event_code: str,
        reason: Optional[str] = None,
        reason_code: Optional[str] = None,
        **context: Any,
    ) -> None:
        """
        Emit structured logs with standardized context. This shouldn't be called
        directly under ordinary circumstances, with one of the level methods (
        debug, info, warning, error) used instead.

        Args:
            level (str): Logging level ('debug', 'info', 'warning', 'error').
            message (str): Human-readable log message.
            event_code (str): Required short machine-readable identifier.
            reason (str, optional): Human-readable reason for failure (required for
                warnings/errors).
            reason_code (str, optional): Short identifier for reason (required for
                warnings/errors).
            context (Any): Additional structured context for the log.

        Raises:
            ValueError: If required fields are missing for the given log level.
        """
        if not message:
            raise ValueError("Log message is required.")
        if not event_code:
            raise ValueError("Structured logs must include an 'event_code' field.")
        if level in ("warning", "error") and (not reason or not reason_code):
            raise ValueError(
                "Warnings and errors must include both 'reason' and 'reason_code'."
            )

        context_data = {"event_code": event_code}
        if reason:
            context_data["reason"] = reason
        if reason_code:
            context_data["reason_code"] = reason_code

        bound_context = self._context

        # Extract data from provided context, falling back to the bound context
        # if it exists
        for context_key, extractor_function in self._extractors.items():
            context_object = context.pop(context_key, bound_context.get(context_key))
            if context_object:
                extracted_fields = extractor_function(context_object)
                for key, value in extracted_fields.items():
                    if value is not None:
                        context_data.setdefault(key, value)

        # Add remaining values in bound_context
        # (i.e., keys that weren't already extracted)
        for key, value in bound_context.items():
            if key not in self._extractors and key not in context and value is not None:
                context_data[key] = value

        # Override extracted and bound context with any explicit values passed in
        # For instance, if `asset` and `asset_id` were both passed in, we would
        # have extracted `asset`.`asset_id`, `asset`.`item`.`item_id`, etc., and
        # now the extracted `asset_id` would be overriden by the explicit `asset_id`
        # in the passed-in context.
        for key, value in context.items():
            if value is not None:
                context_data[key] = value

        getattr(self._logger, level)(message, **context_data)

    def debug(self, message: str, *, event_code: str, **kwargs):
        """Emit a debug-level structured log."""
        self.log("debug", message, event_code=event_code, **kwargs)

    def info(self, message: str, *, event_code: str, **kwargs):
        """Emit an info-level structured log."""
        self.log("info", message, event_code=event_code, **kwargs)

    def warning(
        self, message: str, *, event_code: str, reason: str, reason_code: str, **kwargs
    ):
        """Emit a warning-level structured log. Requires reason and reason_code."""
        self.log(
            "warning",
            message,
            event_code=event_code,
            reason=reason,
            reason_code=reason_code,
            **kwargs,
        )

    def error(
        self, message: str, *, event_code: str, reason: str, reason_code: str, **kwargs
    ):
        """Emit an error-level structured log. Requires reason and reason_code."""
        self.log(
            "error",
            message,
            event_code=event_code,
            reason=reason,
            reason_code=reason_code,
            **kwargs,
        )

    def bind(self, **kwargs: Any) -> "ConcordiaLogger":
        """
        Return a new ConcordiaLogger with additional context permanently bound.

        Bound context can include semantic objects like asset, user or transcription,
        in addition to primitive data types. Objects with registered extractors
        will be expanded into structured fields at log time.

        Args:
            **kwargs: Context to bind.

        Returns:
            ConcordiaLogger: A logger with the provided context bound.
        """
        # We make our own bound context rather than using structlog's
        # .bind so we can safely access it ourselves
        new_context = self._context.copy()
        new_context.update(kwargs)
        return ConcordiaLogger(self._logger, context=new_context)
