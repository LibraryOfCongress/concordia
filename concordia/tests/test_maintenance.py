from django.core.cache import cache
from django.test import RequestFactory, TestCase
from maintenance_mode.core import set_maintenance_mode

from concordia.maintenance import need_maintenance_response

from .utils import CreateTestUsers


class TestMaintenance(TestCase, CreateTestUsers):
    def setUp(self):
        self.request_factory = RequestFactory()
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_need_maintenance_response_maintenance_default(self):
        request = self.request_factory.get("/")
        self.assertFalse(need_maintenance_response(request))

    def test_need_maintenance_response_maintenance_off(self):
        set_maintenance_mode(False)
        request = self.request_factory.get("/")
        self.assertFalse(need_maintenance_response(request))

    def test_need_maintenance_response_maintenance_on(self):
        set_maintenance_mode(True)
        request = self.request_factory.get("/")
        self.assertTrue(need_maintenance_response(request))

        request.user = self.create_test_user()
        request.user.is_staff = True

        # User is set and is staff, but frontend is off
        # (the default) so they should still get a maintenance
        # mode response
        self.assertTrue(need_maintenance_response(request))

    def test_need_maintenance_response_maintenance_frontend(self):
        set_maintenance_mode(True)
        request = self.request_factory.get("/")
        request.user = self.create_test_user()
        cache.set("maintenance_mode_frontend_available", True)

        # User is set but isn't super user, so they should get
        # a maintenance mode response
        self.assertTrue(need_maintenance_response(request))

        request.user.is_staff = True
        # User is staff, so they shouldn't get a maintenance
        # mode response
        self.assertFalse(need_maintenance_response(request))
