import warnings
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import TestCase

from concordia.logging import ConcordiaLogger


class ConcordiaLoggerTests(TestCase):
    def setUp(self):
        self.mock_structlog_logger = MagicMock()
        self.logger = ConcordiaLogger(self.mock_structlog_logger)

    def test_debug_logs_with_event(self):
        self.logger.debug("debug msg", event_code="debug_event", key1="value1")
        self.mock_structlog_logger.debug.assert_called_once()
        args, kwargs = self.mock_structlog_logger.debug.call_args
        self.assertEqual(args[0], "debug msg")
        self.assertEqual(kwargs["event_code"], "debug_event")
        self.assertEqual(kwargs["key1"], "value1")

    def test_info_logs_with_event(self):
        self.logger.info("info msg", event_code="info_event", key2="value2")
        self.mock_structlog_logger.info.assert_called_once()
        args, kwargs = self.mock_structlog_logger.info.call_args
        self.assertEqual(args[0], "info msg")
        self.assertEqual(kwargs["event_code"], "info_event")
        self.assertEqual(kwargs["key2"], "value2")

    def test_warning_requires_reason_and_reason_code(self):
        with self.assertRaises(TypeError):
            self.logger.warning(
                "warning msg", event_code="warn_event", reason="only_reason"
            )

        self.logger.warning(
            "warning msg",
            event_code="warn_event",
            reason="test reason",
            reason_code="warn_code",
            key3="value3",
        )
        self.mock_structlog_logger.warning.assert_called_once()
        args, kwargs = self.mock_structlog_logger.warning.call_args
        self.assertEqual(kwargs["event_code"], "warn_event")
        self.assertEqual(kwargs["reason"], "test reason")
        self.assertEqual(kwargs["reason_code"], "warn_code")
        self.assertEqual(kwargs["key3"], "value3")

    def test_error_requires_reason_and_reason_code(self):
        with self.assertRaises(TypeError):
            self.logger.error(
                "error msg", event_code="error_event", reason_code="only_code"
            )

        self.logger.error(
            "error msg",
            event_code="error_event",
            reason="error reason",
            reason_code="error_code",
        )
        self.mock_structlog_logger.error.assert_called_once()
        args, kwargs = self.mock_structlog_logger.error.call_args
        self.assertEqual(kwargs["event_code"], "error_event")
        self.assertEqual(kwargs["reason"], "error reason")
        self.assertEqual(kwargs["reason_code"], "error_code")

    def test_missing_event_raises(self):
        with self.assertRaises(ValueError):
            self.logger.info("msg", event_code=None)

    def test_log_merges_context_correctly(self):
        mock_obj = SimpleNamespace(id=42)
        self.logger.register_extractor("thing", lambda o: {"thing_id": o.id})
        self.logger.info("msg", event_code="test_event", thing=mock_obj)
        args, kwargs = self.mock_structlog_logger.info.call_args
        self.assertEqual(kwargs["thing_id"], 42)

    def test_log_explicit_key_overrides_extracted(self):
        mock_obj = SimpleNamespace(id=42)
        self.logger.register_extractor("thing", lambda o: {"thing_id": 123})
        self.logger.info("msg", event_code="test_event", thing=mock_obj, thing_id=999)
        args, kwargs = self.mock_structlog_logger.info.call_args
        self.assertEqual(kwargs["thing_id"], 999)

    def test_bind_merges_context(self):
        bound = self.logger.bind(foo="bar")
        self.assertIsInstance(bound, ConcordiaLogger)
        self.assertIn("foo", bound._context)
        self.assertEqual(bound._context["foo"], "bar")

    def test_bind_merges_context_into_logging(self):
        bound = self.logger.bind(user="uval")
        bound.register_extractor("user", lambda o: {"user_id": o})
        bound.info("msg", event_code="bound_event")
        args, kwargs = self.mock_structlog_logger.info.call_args
        self.assertEqual(kwargs["user_id"], "uval")

    def test_unregister_extractor_removes_extractor(self):
        self.logger.register_extractor("foo", lambda o: {"foo_id": 1})
        self.logger.unregister_extractor("foo")
        self.assertNotIn("foo", self.logger._extractors)

    def test_register_extractor_warns_on_chained_override(self):
        def fake_asset_extractor(x):
            return {"asset_id": 1, "item_id": 2}

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            self.logger.register_extractor("asset", fake_asset_extractor)
            self.assertTrue(
                any(
                    "default extractors may still reference" in str(warn.message)
                    for warn in w
                )
            )

    def test_log_raises_when_message_is_none(self):
        with self.assertRaises(ValueError):
            self.logger.info(None, event_code="event")

    def test_log_raises_when_message_is_none_direct(self):
        with self.assertRaises(ValueError):
            self.logger.log("info", None, event_code="event")

    def test_log_raises_when_message_is_empty(self):
        with self.assertRaises(ValueError):
            self.logger.info("", event_code="event")

    def test_log_raises_when_message_is_empty_direct(self):
        with self.assertRaises(ValueError):
            self.logger.log("info", "", event_code="event")

    def test_log_skips_none_values_from_extractor(self):
        class Dummy:
            def __init__(self):
                self.id = None

        self.logger.register_extractor("thing", lambda o: {"thing_id": o.id})
        self.logger.info("msg", event_code="event", thing=Dummy())
        args, kwargs = self.mock_structlog_logger.info.call_args
        self.assertNotIn("thing_id", kwargs)

    def test_log_includes_nonextractor_bound_context(self):
        bound = self.logger.bind(extra1="foo", extra2="bar")
        bound.info("msg", event_code="event")
        args, kwargs = self.mock_structlog_logger.info.call_args
        self.assertEqual(kwargs["extra1"], "foo")
        self.assertEqual(kwargs["extra2"], "bar")

    def test_log_skips_none_values_in_context(self):
        self.logger.info("msg", event_code="event", explicit=None)
        args, kwargs = self.mock_structlog_logger.info.call_args
        self.assertNotIn("explicit", kwargs)

    def test_log_overrides_bound_and_extracted_context(self):
        obj = SimpleNamespace(id=123)
        base = self.logger.bind(thing=obj, value="a")
        base.register_extractor("thing", lambda o: {"thing_id": o.id, "value": "b"})
        base.info("msg", event_code="event", value="c")
        args, kwargs = self.mock_structlog_logger.info.call_args
        # Extracted value ("b") overridden by explicit context ("c")
        self.assertEqual(kwargs["value"], "c")
        self.assertEqual(kwargs["thing_id"], 123)

    def test_extractor_returns_none_value_skipped(self):
        obj = SimpleNamespace()
        self.logger.register_extractor("thing", lambda o: {"thing_id": None})
        self.logger.info("msg", event_code="event", thing=obj)
        args, kwargs = self.mock_structlog_logger.info.call_args
        self.assertNotIn("thing_id", kwargs)

    def test_get_logger_uses_structlog(self):
        with patch("concordia.logging.structlog.get_logger") as mock_get_logger:
            mock_logger_instance = MagicMock()
            mock_get_logger.return_value = mock_logger_instance

            logger = ConcordiaLogger.get_logger("concordia.tests")

            mock_get_logger.assert_called_once_with("structlog.concordia.tests")
            self.assertIsInstance(logger, ConcordiaLogger)
            self.assertEqual(logger._logger, mock_logger_instance)

    def test_log_raises_valueerror_for_empty_reason_and_code(self):
        with self.assertRaises(ValueError):
            self.logger.log(
                "warning", "bad", event_code="something", reason="", reason_code="fail"
            )

        with self.assertRaises(ValueError):
            self.logger.log(
                "error", "bad", event_code="something", reason="fail", reason_code=None
            )

    def test_exception_logs_with_exc_info(self):
        try:
            raise ValueError("Something went wrong")
        except ValueError:
            self.logger.exception(
                "Exception occurred",
                event_code="test_exception",
                reason="An error was raised",
                reason_code="value_error",
                extra="context",
            )

        self.mock_structlog_logger.error.assert_called_once()
        args, kwargs = self.mock_structlog_logger.error.call_args
        self.assertEqual(args[0], "Exception occurred")
        self.assertEqual(kwargs["event_code"], "test_exception")
        self.assertEqual(kwargs["reason"], "An error was raised")
        self.assertEqual(kwargs["reason_code"], "value_error")
        self.assertEqual(kwargs["extra"], "context")
        self.assertTrue(kwargs.get("exc_info"))
