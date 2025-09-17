import logging
import random
import string
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlencode, urljoin, urlparse

from gevent import sleep
from locust import HttpUser, between, task

HOMEPAGE_PATH = "/"
NEXT_ASSET_PATH = "/next-transcribable-asset/"
AJAX_STATUS_PATH = "/account/ajax-status/"
AJAX_MSG_PATH = "/account/ajax-messages/"
LOGIN_PATH = "/account/login/"
CSRF_COOKIE_NAME = "csrftoken"
SESSION_COOKIE_NAME = "sessionid"
CSRF_SEED_PATH = HOMEPAGE_PATH  # Backup if CSRF cookie is missing
POST_FIELD_NAME = "text"
POST_MIN_CHARS = 10
POST_MAX_CHARS = 200
SAME_PAGE_REPEAT_PROB = 0.75  # 75% do another POST+GET on same asset
REDIRECT_RETRIES = 3  # how many times to retry the redirect
REDIRECT_BACKOFF = 0.25  # seconds; linear backoff per attempt

TEST_USER_PREFIX = "locusttest"
TEST_USER_DOMAIN = "example.test"
TEST_USER_COUNT = 10_000
TEST_USER_PASSWORD = "locustpass123"  # nosec B105
LOGIN_BAD_PASSWORD_PROB = 0.10
LOGIN_MAX_ATTEMPTS = 5

logger = logging.getLogger(__name__)


def _is_local(path_or_url: str, base: str) -> bool:
    if not path_or_url:
        return False
    if path_or_url.startswith("/"):
        return True
    parsed = urlparse(path_or_url)
    if not parsed.scheme:
        return True  # relative like "static/app.js"
    return urlparse(base).netloc == parsed.netloc


class _ResourceParser(HTMLParser):
    """Extract local script and stylesheet URLs from the page."""

    def __init__(self, base_url: str):
        super().__init__()
        self.base_url = base_url
        self.resources = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "script":
            src = attrs.get("src")
            if src and _is_local(src, self.base_url):
                self.resources.append(urljoin(self.base_url, src))
        elif tag == "link":
            rel = (attrs.get("rel") or "").lower()
            href = attrs.get("href")
            if "stylesheet" in rel and href and _is_local(href, self.base_url):
                self.resources.append(urljoin(self.base_url, href))


class _AssetPageParser(HTMLParser):
    """Extract form action, supersedes, and reserve URL from an asset page."""

    def __init__(self, base_url: str):
        super().__init__()
        self.base_url = base_url  # full page URL
        self.in_transcription_form = False
        self.form_action = None
        self.supersedes = None
        self.reserve_url = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "form":
            # Find the transcription form
            if a.get("id") == "transcription-editor":
                self.in_transcription_form = True
                action = a.get("action")
                if action is not None:
                    # Resolve relative to the page URL; empty means same page
                    resolved = (
                        self.base_url
                        if action.strip() == ""
                        else urljoin(self.base_url, action)
                    )
                    self.form_action = resolved
        elif tag == "input":
            if a.get("name") == "supersedes" and a.get("value"):
                self.supersedes = a["value"]
        elif tag == "script":
            # Reservation data script tag
            if a.get("id") == "asset-reservation-data":
                reserve = a.get("data-reserve-asset-url")
                if reserve:
                    self.reserve_url = urljoin(self.base_url, reserve)

    def handle_endtag(self, tag):
        if tag == "form" and self.in_transcription_form:
            self.in_transcription_form = False


def _random_text(min_len=10, max_len=200) -> str:
    n = random.randint(min_len, max_len)
    alphabet = string.ascii_letters + string.digits + "     "
    s = "".join(random.choice(alphabet) for _ in range(n))
    return " ".join(s.split())


###
# base browsing user (abstract)
###


class BaseBrowsingUser(HttpUser):
    """
    Shared browse/post behavior. Subclasses provide their own on_start.
    """

    abstract = True
    wait_time = between(3.0, 8.0)

    current_target_path: str | None = None
    current_form_action_path: str | None = None
    current_supersedes: str | None = None
    current_reserve_path: str | None = None

    _fatal_already_triggered = False

    def _fatal_dump_and_quit(self, page_url: str, html: str) -> None:
        if self.__class__._fatal_already_triggered:
            return
        self.__class__._fatal_already_triggered = True

        ts = int(time.time())
        out = Path(f"asset_parse_failure_{ts}.html").resolve()
        try:
            out.write_text(html or "", encoding="utf-8")
            logger.error(
                "FATAL: transcription form not found. Page URL=%s ; HTML dumped to %s",
                page_url,
                out,
            )
        except Exception as e:
            logger.error(
                "FATAL: failed to write HTML dump (%s). Page URL=%s", e, page_url
            )

        try:
            self.environment.runner.quit()
        except Exception as e:
            logger.error("Error calling runner.quit(): %s", e)

    def _after_request_ajax(self):
        # fires two AJAX calls after each page GET
        # to simulate normal page load
        # do NOT wrap these (prevents recursion)
        self.client.get(AJAX_STATUS_PATH, name="AJAX status")
        self.client.get(AJAX_MSG_PATH, name="AJAX messaging")

    def _get(self, path_or_url: str, *, page: bool = True, **kwargs):
        # If page=True, treat as a full page load and then trigger AJAX
        r = self.client.get(path_or_url, **kwargs)
        if page:
            self._after_request_ajax()
        return r

    def _post(self, path_or_url: str, **kwargs):
        # POSTs should not trigger the AJAX-after-page behavior here
        return self.client.post(path_or_url, **kwargs)

    def _load_homepage_and_resources(self, *, name_suffix: str = ""):
        base = self.environment.host.rstrip("/")
        r_home = self._get(HOMEPAGE_PATH, page=True)

        parser = _ResourceParser(base_url=base + "/")
        try:
            parser.feed(r_home.text or "")
        except Exception:
            parser.resources = []

        for res_url in parser.resources:
            label = "resource " + urlparse(res_url).path
            if name_suffix:
                label = f"{label} {name_suffix}"
            self._get(res_url, name=label, page=False)

    def _parse_asset_page_and_reserve(self, target_path: str) -> None:
        base = self.environment.host.rstrip("/")
        r = self._get(target_path, name="target page", page=True)

        parser = _AssetPageParser(base_url=r.url)
        try:
            parser.feed(r.text or "")
        except Exception:
            self._fatal_dump_and_quit(r.url, r.text or "")
            return

        if parser.form_action:
            fa = urlparse(parser.form_action)
            self.current_form_action_path = fa.path + (
                ("?" + fa.query) if fa.query else ""
            )
        else:
            self.current_form_action_path = None

        self.current_supersedes = parser.supersedes

        if parser.reserve_url:
            ru = urlparse(parser.reserve_url)
            self.current_reserve_path = ru.path + (("?" + ru.query) if ru.query else "")
        else:
            self.current_reserve_path = None

        if not self.current_form_action_path:
            self._fatal_dump_and_quit(r.url, r.text or "")
            return

        if self.current_reserve_path:
            csrftoken = self.client.cookies.get(CSRF_COOKIE_NAME)
            referer = urljoin(base + "/", target_path.lstrip("/"))
            self._post(
                self.current_reserve_path,
                headers={"X-CSRFToken": csrftoken or "", "Referer": referer},
                name="reserve asset",
            )

    def _ensure_csrf(self, target_path: str | None) -> str | None:
        if not target_path:
            return None
        csrftoken = self.client.cookies.get(CSRF_COOKIE_NAME)
        if not csrftoken:
            self._parse_asset_page_and_reserve(target_path)
            csrftoken = self.client.cookies.get(CSRF_COOKIE_NAME)
        if not csrftoken and CSRF_SEED_PATH:
            self._get(CSRF_SEED_PATH, name="csrf seed", page=True)
            self._parse_asset_page_and_reserve(target_path)
            csrftoken = self.client.cookies.get(CSRF_COOKIE_NAME)
        return csrftoken

    def _follow_next_asset(self) -> str | None:
        for attempt in range(1, REDIRECT_RETRIES + 1):
            with self.client.get(
                NEXT_ASSET_PATH,
                name="next asset (redirect)",
                catch_response=True,
            ) as resp:
                if 200 <= resp.status_code < 400:
                    return urlparse(resp.url).path or "/"
                msg = (
                    f"redirect failed (status={resp.status_code}) "
                    f"attempt={attempt}/{REDIRECT_RETRIES}"
                )
                resp.failure(msg)
                logger.warning("next asset retry: %s", msg)
            sleep(REDIRECT_BACKOFF * attempt)
        logger.error("next asset: all %d retries failed", REDIRECT_RETRIES)
        return None

    def _post_then_get_same_page(
        self, target_path: str | None, csrftoken: str, name_prefix: str
    ):
        if not target_path:
            return
        base = self.environment.host.rstrip("/")
        referer = urljoin(base + "/", target_path.lstrip("/"))
        post_path = self.current_form_action_path
        if not post_path:
            return

        data = {POST_FIELD_NAME: _random_text(POST_MIN_CHARS, POST_MAX_CHARS)}
        if self.current_supersedes:
            data["supersedes"] = self.current_supersedes

        self._post(
            post_path,
            data=data,
            headers={"X-CSRFToken": csrftoken, "Referer": referer},
            name=f"{name_prefix} POST",
        )
        self._parse_asset_page_and_reserve(target_path)

    @task
    def browse_and_submit(self):
        if not self.current_target_path:
            new_path = self._follow_next_asset()
            if new_path is None:
                return
            self.current_target_path = new_path
            self.current_form_action_path = None
            self.current_supersedes = None
            self.current_reserve_path = None
        else:
            if random.random() >= SAME_PAGE_REPEAT_PROB:
                new_path = self._follow_next_asset()
                if new_path is None:
                    return
                self.current_target_path = new_path
                self.current_form_action_path = None
                self.current_supersedes = None
                self.current_reserve_path = None

        csrftoken = self._ensure_csrf(self.current_target_path)
        if not csrftoken:
            if self.current_target_path:
                self._get(
                    self.current_target_path, name="target page (no CSRF)", page=True
                )
            return

        self._post_then_get_same_page(self.current_target_path, csrftoken, "target")

        if random.random() < SAME_PAGE_REPEAT_PROB:
            csrftoken = self.client.cookies.get(CSRF_COOKIE_NAME) or self._ensure_csrf(
                self.current_target_path
            )
            if csrftoken:
                self._post_then_get_same_page(
                    self.current_target_path, csrftoken, "target (repeat)"
                )


###
# anonymous user
###


class AnonUser(BaseBrowsingUser):
    """
    Anonymous user flow:
      - one-time: GET homepage and fetch local scripts/styles (with AJAX calls)
      - loop: same as BaseBrowsingUser
    """

    def on_start(self):
        self._load_homepage_and_resources()


###
# authenticated user
###


class AuthUser(BaseBrowsingUser):
    """
    Authenticated user flow:
      - GET homepage
      - Visit /account/login/?next=/, attempt login by username or email
        with a 10% chance per attempt to submit an incorrect password,
        retrying up to 5 times
      - After success (or failure), GET homepage again and load resources
      - Loop behavior same as BaseBrowsingUser
    """

    chosen_username: str | None = None
    chosen_email: str | None = None

    def _pick_fixture_user(self):
        idx = random.randint(1, TEST_USER_COUNT)
        uname = f"{TEST_USER_PREFIX}{idx:05d}"
        email = f"{uname}@{TEST_USER_DOMAIN}"
        self.chosen_username = uname
        self.chosen_email = email

    def _login_once(self, login_url: str, referer: str) -> bool:
        csrftoken = self.client.cookies.get(CSRF_COOKIE_NAME) or ""
        if not csrftoken:
            self._get(login_url, name="login page", page=True)
            csrftoken = self.client.cookies.get(CSRF_COOKIE_NAME) or ""

        assert self.chosen_username and self.chosen_email
        ident = self.chosen_username if random.random() < 0.5 else self.chosen_email

        wrong = random.random() < LOGIN_BAD_PASSWORD_PROB
        password = TEST_USER_PASSWORD if not wrong else TEST_USER_PASSWORD + "x"

        form = {
            "username": ident,
            "password": password,
            "csrfmiddlewaretoken": csrftoken,
            "next": "/",
        }

        self._post(
            login_url,
            data=form,
            headers={"X-CSRFToken": csrftoken, "Referer": referer},
            name="login POST",
        )

        has_session = bool(self.client.cookies.get(SESSION_COOKIE_NAME))
        if has_session:
            return True

        self._get("/", name="post-login home probe", page=True)
        has_session = bool(self.client.cookies.get(SESSION_COOKIE_NAME))
        return has_session

    def on_start(self):
        self._get(HOMEPAGE_PATH, page=True)

        self._pick_fixture_user()
        query = urlencode({"next": "/"})
        login_url = f"{LOGIN_PATH}?{query}"
        base = self.environment.host.rstrip("/")
        referer = urljoin(base + "/", LOGIN_PATH.lstrip("/"))

        self._get(login_url, name="login page", page=True)

        success = False
        for _ in range(LOGIN_MAX_ATTEMPTS):
            if self._login_once(login_url, referer):
                success = True
                break
            self._get(login_url, name="login page (retry)", page=True)

        if not success:
            logger.error(
                "AuthUser failed to authenticate after %d attempts (user=%s / %s)",
                LOGIN_MAX_ATTEMPTS,
                self.chosen_username,
                self.chosen_email,
            )

        self._load_homepage_and_resources(name_suffix="(authed)")
