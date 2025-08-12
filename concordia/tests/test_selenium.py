import json
from logging import getLogger
from secrets import token_hex

from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.template.loader import render_to_string
from django.test import tag
from django.urls import reverse
from pylenium.config import PyleniumConfig
from pylenium.driver import Pylenium
from selenium.webdriver.common.keys import Keys

from .axe import Axe
from .utils import CreateTestUsers, create_campaign, create_simple_page

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
        self.py.viewport(1280, 800)
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

    def test_tinymce(self):
        self.py.visit(self.reverse("admin:login"))
        user = self.create_user("login-test")
        self.py.get("[name='username']").type(user.username)
        self.py.get("[name='password']").type(user._password).enter()

        campaign = create_campaign()
        self.py.visit(
            self.reverse("admin:concordia_campaign_change", args=(campaign.pk,))
        )
        tinymce_frame = self.py.get("iframe#id_description_ifr")
        self.py.switch_to.frame(tinymce_frame.webelement)

        editor_body = self.py.get("body")
        editor_body.type("test")
        editor_body.type(Keys.ENTER)
        editor_body.type("test")

        # back to main
        self.py.switch_to.default_content()

        self.py.get('[name="_save]').click()

        self.assertIn("<br>", campaign.description)

    def test_blog_carousel(self):
        context = {"blog_posts": [[{}], [{}]]}
        html_string = render_to_string("fragments/featured_blog_posts.html", context)
        create_simple_page(path="/about/", title="About", body=html_string)
        self.py.visit(self.reverse("about"))

        carousel = self.py.get("#blog-carousel")
        self.assertTrue(carousel.should().be_visible())

        inner = carousel.get(".carousel-inner")
        items = inner.find(".carousel-item")
        self.assertGreater(len(items), 1, "No carousel items found")

        active_items = [
            item for item in items if "active" in item.get_attribute("class")
        ]
        self.assertEqual(len(active_items), 1)
