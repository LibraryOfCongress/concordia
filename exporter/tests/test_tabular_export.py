import datetime
from unittest.mock import Mock

from django.db import models
from django.http import HttpResponse, StreamingHttpResponse
from django.test import TestCase, override_settings

from exporter.tabular_export.admin import (
    export_to_csv_action,
    export_to_excel_action,
)
from exporter.tabular_export.core import (
    Echo,
    convert_value_to_unicode,
    export_to_csv_response,
    export_to_debug_html_response,
    export_to_excel_response,
    flatten_queryset,
    force_utf8_encoding,
    get_field_names_from_queryset,
    set_content_disposition,
)


class DummyModel(models.Model):
    name = models.CharField(max_length=255, verbose_name="Name")
    created = models.DateField(null=True, verbose_name="Created")

    class Meta:
        app_label = "tests"


class DummyQuerySet:
    def __init__(self, data, field_names):
        self._data = data
        self._field_names = field_names
        self.model = DummyModel

    def values_list(self, *args):
        return self._data

    def values(self):
        return self

    @property
    def query(self):
        class Query:
            select = [
                type("Field", (), {"target": type("Target", (), {"name": fn})()})
                for fn in self._field_names
            ]
            extra_select = {"extra": "value"}
            annotation_select = {"annotate": "value"}

        return Query()


class CoreTests(TestCase):
    def test_convert_value_to_unicode(self):
        self.assertEqual(convert_value_to_unicode(None), "")
        self.assertEqual(convert_value_to_unicode("abc"), "abc")
        dt = datetime.datetime(2020, 1, 1, 12, 0)
        self.assertEqual(convert_value_to_unicode(dt), "2020-01-01T12:00:00")
        d = datetime.date(2020, 1, 1)
        self.assertEqual(convert_value_to_unicode(d), "2020-01-01")

    def test_echo_write(self):
        echo = Echo()
        self.assertEqual(echo.write("abc"), "abc")

    def test_get_field_names_from_queryset(self):
        qs = DummyQuerySet([], ["name", "created"])
        self.assertEqual(
            get_field_names_from_queryset(qs),
            ["name", "created", "extra", "annotate"],
        )

    def test_flatten_queryset_defaults(self):
        qs = DummyQuerySet([("abc", datetime.date(2020, 1, 1))], ["name", "created"])
        headers, rows = flatten_queryset(qs)
        self.assertEqual(headers, ["Name", "Created", "extra", "annotate"])
        self.assertEqual(list(rows), [("abc", datetime.date(2020, 1, 1))])

    def test_flatten_queryset_with_custom_headers(self):
        qs = DummyQuerySet([("abc",)], ["name"])
        headers, rows = flatten_queryset(
            qs, field_names=["name"], extra_verbose_names={"name": "Full Name"}
        )
        self.assertEqual(headers, ["Full Name"])
        self.assertEqual(list(rows), [("abc",)])

    def test_force_utf8_encoding(self):
        def rows():
            yield ["ü", "æ"]

        out = list(force_utf8_encoding(rows)())
        self.assertEqual(out, [[b"\xc3\xbc", b"\xc3\xa6"]])

    def test_set_content_disposition(self):
        @set_content_disposition
        def dummy(filename):
            return StreamingHttpResponse()

        resp = dummy("test.csv")
        self.assertIn(
            "attachment; filename*=UTF-8''test.csv", resp["Content-Disposition"]
        )

    def test_export_to_debug_html_response(self):
        headers = ["h1", "h2"]
        rows = [["val1", "val2"], ["val3", "val4"]]
        resp = export_to_debug_html_response("test.html", headers, rows)
        self.assertIsInstance(resp, StreamingHttpResponse)
        content = b"".join(resp.streaming_content)
        self.assertIn(b"<table", content)
        self.assertIn(b"val1", content)
        self.assertIn(b"val4", content)

    @override_settings(TABULAR_RESPONSE_DEBUG=False)
    def test_export_to_csv_response(self):
        headers = ["h1", "h2"]
        rows = [["a", "b"]]
        resp = export_to_csv_response("test.csv", headers, rows)
        self.assertIsInstance(resp, StreamingHttpResponse)
        content = b"".join(resp.streaming_content)
        self.assertIn(b"a", content)

    @override_settings(TABULAR_RESPONSE_DEBUG=True)
    def test_export_to_csv_response_debug(self):
        headers = ["h1"]
        rows = [["b"]]
        resp = export_to_csv_response("debug.csv", headers, rows)
        self.assertIsInstance(resp, StreamingHttpResponse)
        content = b"".join(resp.streaming_content)
        self.assertIn(b"<table", content)
        self.assertNotIn("Content-Disposition", resp)

    @override_settings(TABULAR_RESPONSE_DEBUG=False)
    def test_export_to_excel_response(self):
        headers = ["h1", "h2"]
        rows = [["x", datetime.date(2022, 1, 1)]]
        resp = export_to_excel_response("file.xlsx", headers, rows)
        self.assertIsInstance(resp, HttpResponse)
        self.assertEqual(
            resp["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    @override_settings(TABULAR_RESPONSE_DEBUG=False)
    def test_export_to_excel_response_with_datetime(self):
        headers = ["h1"]
        rows = [[datetime.datetime(2022, 1, 1, 12, 0)]]
        resp = export_to_excel_response("datetime.xlsx", headers, rows)
        self.assertIsInstance(resp, HttpResponse)

    @override_settings(TABULAR_RESPONSE_DEBUG=True)
    def test_export_to_excel_response_debug(self):
        headers = ["h1"]
        rows = [["x"]]
        resp = export_to_excel_response("debug.xlsx", headers, rows)
        self.assertIsInstance(resp, StreamingHttpResponse)
        content = b"".join(resp.streaming_content)
        self.assertIn(b"<table", content)


class AdminTests(TestCase):
    def setUp(self):
        self.queryset = DummyQuerySet(
            data=[("val1", "val2"), ("val3", "val4")],
            field_names=["name", "created"],
        )
        self.modeladmin = Mock()
        self.modeladmin.model = DummyModel
        self.request = Mock()

    def test_export_to_excel_action_default_filename(self):
        response = export_to_excel_action(self.modeladmin, self.request, self.queryset)
        self.assertIsInstance(response, HttpResponse)
        self.assertIn(
            "application/vnd.openxmlformats-officedocument", response["Content-Type"]
        )

    def test_export_to_excel_action_with_custom_filename_and_fields(self):
        response = export_to_excel_action(
            self.modeladmin,
            self.request,
            self.queryset,
            filename="custom.xlsx",
            field_names=["name"],
            extra_verbose_names={"name": "Custom Name"},
        )
        self.assertIsInstance(response, HttpResponse)

    def test_export_to_csv_action_default_filename(self):
        response = export_to_csv_action(self.modeladmin, self.request, self.queryset)
        self.assertIsInstance(response, StreamingHttpResponse)
        content = b"".join(response.streaming_content)
        self.assertIn(b"val1", content)
        self.assertIn(b"val4", content)

    def test_export_to_csv_action_with_custom_filename_and_fields(self):
        response = export_to_csv_action(
            self.modeladmin,
            self.request,
            self.queryset,
            filename="custom.csv",
            field_names=["name"],
            extra_verbose_names={"name": "Custom Name"},
        )
        self.assertIsInstance(response, StreamingHttpResponse)
        content = b"".join(response.streaming_content)
        self.assertIn(b"val1", content)
