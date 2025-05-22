from typing import Any, Optional

import structlog

from concordia.utils.logging import get_logging_user_id


class ConcordiaLogger:
    """
    A structured logging wrapper around structlog that enforces consistent logging
    conventions across the Concordia application.

    Features:
        - Requires 'event' for all logs, and 'reason'/'reason_code' for warnings/errors.
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
            event="asset_ocr_started",
            asset=my_asset,
            user=request.user,
        )
        ```

    Log a warning with reason:
        ```python
        structured_logger.warning(
            "Rollback failed.",
            event="rollback_attempt_failed",
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
        my_logger.info("Transcription updated.", event="transcription_updated")
        ```

        This is the equivalent of:
        ```python
        logger = ConcordiaLogger.get_logger(f"{__name__}")
        logger.info(
            "Transcription updated.",
            event="transcription_updated",
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

    - `user` → `user_id`
    - `asset` → `asset_id`, `campaign_slug`, `item_id`
    - `transcription` → `transcription_id`
    - `campaign` → `campaign_slug`
    - `item` → `item_id`

    If these objects are passed directly (e.g., as `user=request.user`), their relevant
    fields will be included automatically in the log entry.

    Explicit values passed (e.g., `item_id=...`) override extracted ones. Fields with
    `None` values are omitted from the final log output.
    """

    def __init__(self, logger, context: Optional[dict[str, Any]] = None):
        """
        Initialize the ConcordiaLogger with an underlying structlog logger.

        Args:
            logger (structlog.BoundLogger): A structlog logger instance.
        """
        self._logger = logger
        self._context = context or {}

    @classmethod
    def get_logger(cls, name: str) -> "ConcordiaLogger":
        """
        Factory method to create a ConcordiaLogger from a given logger name.

        Args:
            name (str): The logger name (typically f"structlog.{__name__}").

        Returns:
            ConcordiaLogger: A logger instance with enriched behavior.
        """
        return cls(structlog.get_logger(f"structlog.{__name__}"))

    def log(
        self,
        level: str,
        message: str,
        *,
        event: str,
        reason: Optional[str] = None,
        reason_code: Optional[str] = None,
        **context: Any,
    ) -> None:
        """
        Emit structured logs with standardized context.

        Args:
            level (str): Logging level ('debug', 'info', 'warning', 'error').
            message (str): Human-readable log message.
            event (str): Required short machine-readable identifier.
            reason (str, optional): Human-readable reason for failure (required for
                warnings/errors).
            reason_code (str, optional): Short identifier for reason (required for
                warnings/errors).
            context (Any): Additional structured context for the log. See the
                **Special Context Handling** section below for recognized keys.

                - `user` (User): Extracts `user_id` using `get_logging_user_id()`.
                - `asset` (Asset): Extracts `asset_id`, `campaign_slug`, and `item_id`.
                - `transcription` (Transcription): Extracts `transcription_id`.
                - `campaign` (Campaign): Extracts `campaign_slug`.
                - `item` (Item): Extracts `item_id`.

                Any other key-value pairs are included as-is, unless their value is
                `None`, in which case they are omitted.

        Raises:
            ValueError: If required fields are missing for the given log level.
        """
        if not message:
            raise ValueError("Log message is required.")
        if not event:
            raise ValueError("Structured logs must include an 'event' field.")
        if level in ("warning", "error") and (not reason or not reason_code):
            raise ValueError(
                "Warnings and errors must include both 'reason' and 'reason_code'."
            )

        ctx = {"event": event}
        if reason:
            ctx["reason"] = reason
        if reason_code:
            ctx["reason_code"] = reason_code

        bound = self._context

        # Extract known context objects
        user = context.pop("user", bound.get("user"))
        asset = context.pop("asset", bound.get("asset"))
        transcription = context.pop("transcription", bound.get("transcription"))
        campaign = context.pop("campaign", bound.get("campaign"))
        item = context.pop("item", bound.get("item"))

        if user:
            user_id = get_logging_user_id(user)
            if user_id is not None:
                ctx["user_id"] = user_id

        if asset:
            asset_id = getattr(asset, "pk", None)
            campaign_slug = getattr(getattr(asset, "campaign", None), "slug", None)
            item_id = getattr(getattr(asset, "item", None), "item_id", None)

            if asset_id is not None:
                ctx["asset_id"] = asset_id
            if campaign_slug is not None:
                ctx["campaign_slug"] = campaign_slug
            if item_id is not None:
                ctx["item_id"] = item_id

        if transcription:
            transcription_id = getattr(transcription, "pk", None)
            if transcription_id is not None:
                ctx["transcription_id"] = transcription_id

        if campaign:
            slug = getattr(campaign, "slug", None)
            if slug is not None:
                ctx["campaign_slug"] = slug

        if item:
            item_id = getattr(item, "item_id", None)
            if item_id is not None:
                ctx["item_id"] = item_id

        # Add remaining values in context (which may include user-defined fields)
        for key, value in context.items():
            if value is not None:
                ctx[key] = value

        getattr(self._logger, level)(message, **ctx)

    def debug(self, message: str, *, event: str, **kwargs):
        """Emit a debug-level structured log."""
        self.log("debug", message, event=event, **kwargs)

    def info(self, message: str, *, event: str, **kwargs):
        """Emit an info-level structured log."""
        self.log("info", message, event=event, **kwargs)

    def warning(
        self, message: str, *, event: str, reason: str, reason_code: str, **kwargs
    ):
        """Emit a warning-level structured log. Requires reason and reason_code."""
        self.log(
            "warning",
            message,
            event=event,
            reason=reason,
            reason_code=reason_code,
            **kwargs,
        )

    def error(
        self, message: str, *, event: str, reason: str, reason_code: str, **kwargs
    ):
        """Emit an error-level structured log. Requires reason and reason_code."""
        self.log(
            "error",
            message,
            event=event,
            reason=reason,
            reason_code=reason_code,
            **kwargs,
        )

    def bind(self, **kwargs: Any) -> "ConcordiaLogger":
        """
        Return a new ConcordiaLogger with additional context permanently bound.

        Bound context can include semantic objects like asset, user, or transcription.
        These will be expanded into structured fields at log time.

        Args:
            **kwargs: Context to bind.

        Returns:
            ConcordiaLogger: A logger with the provided context bound.
        """

        # We make our own bound context rather than using structlog's
        # .bind so we can safely access it
        new_context = self._context.copy()
        new_context.update(kwargs)
        return ConcordiaLogger(self._logger, context=new_context)
