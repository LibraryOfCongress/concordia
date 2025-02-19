import json
from logging import getLogger
from secrets import token_hex

from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import tag
from django.urls import reverse
from pylenium.config import PyleniumConfig
from pylenium.driver import Pylenium

from .axe import Axe
from .utils import CreateTestUsers

logger = getLogger(__name__)


@tag("selenium", "axe")
class SeleniumTests(CreateTestUsers, StaticLiveServerTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        try:
            with open(settings.PYLENIUM_CONFIG) as file:
                _json = json.load(file)
            config = PyleniumConfig(**_json)
        except FileNotFoundError:
            logger.warning(
                "settings.PYLENIUM_CONFIG (%s) was not found; using defaults.",
                settings.PYLENIUM_CONFIG,
            )
            config = PyleniumConfig()

        cls.py = Pylenium(config)
        cls.axe = Axe(cls.py)

    @classmethod
    def tearDownClass(cls):
        cls.py.quit()
        super().tearDownClass()

    def reverse(self, name):
        return f"{self.live_server_url}{reverse(name)}"

    def test_login(self):
        self.py.visit(self.reverse("registration_login"))
        violations = self.axe.violations()
        self.assertEqual(len(violations), 0, self.axe.report(violations))

        self.py.get("[name='username']").type(token_hex(8))
        self.py.get("[name='password']").type(token_hex(24))
        self.py.get("button#login").click()
        self.assertTrue(
            self.py.should().have_url(f"{self.live_server_url}/account/login/")
        )

        violations = self.axe.violations()
        self.assertEqual(len(violations), 0, self.axe.report(violations))

        self.assertTrue(
            self.py.get("form#login-form")
            .should()
            .contain_text("Please enter a correct username and password")
        )

        user = self.create_user("login-test")
        self.py.visit(self.reverse("registration_login"))
        self.py.get("[name='username']").type(user.username)
        self.py.get("[name='password']").type(user._password)
        self.py.get("button#login").click()

        violations = self.axe.violations()
        self.assertEqual(len(violations), 0, self.axe.report(violations))
