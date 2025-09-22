import logging
import random
import string
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlencode, urljoin, urlparse

from gevent import sleep
from gevent.event import Event
from locust import HttpUser, between, events, runners, task
from locust.exception import StopUser

ABORT_WHEN_NO_WORK = True  # stop the run if a next-* page has no work
NO_WORK_DUMP_HTML = False  # set True to write an HTML dump for debugging

HOMEPAGE_PATH = "/"
NEXT_ASSET_PATH = "/next-transcribable-asset/"
NEXT_REVIEWABLE_ASSET_PATH = "/next-reviewable-asset/"
AJAX_STATUS_PATH = "/account/ajax-status/"
AJAX_MSG_PATH = "/account/ajax-messages/"
LOGIN_PATH = "/account/login/"
CSRF_COOKIE_NAME = "csrftoken"
SESSION_COOKIE_NAME = "sessionid"
CSRF_SEED_PATH = HOMEPAGE_PATH
POST_FIELD_NAME = "text"
POST_MIN_CHARS = 10
POST_MAX_CHARS = 200
SAME_PAGE_REPEAT_PROB = 0.75
REDIRECT_RETRIES = 3
REDIRECT_BACKOFF = 0.25

TEST_USER_PREFIX = "locusttest"
TEST_USER_DOMAIN = "example.test"
TEST_USER_COUNT = 10_000
TEST_USER_PASSWORD = "locustpass123"  # nosec B105
LOGIN_BAD_PASSWORD_PROB = 0.10
LOGIN_MAX_ATTEMPTS = 5

REVIEWER_SHARE = 0.20
REVIEW_EDIT_PROB = 0.50

NO_WORK_ERROR_MESSAGE = (
    "Did you need to refresh the load test database? "
    "Try running the 'prepare_load_test_db' command or "
    "'create_load_test_fixtures' if you need fixtures first."
)

logger = logging.getLogger(__name__)

# ---------- global abort plumbing ----------

GLOBAL_ABORT_EVENT: Event = Event()
GLOBAL_ABORT_REASON: str | None = None


@events.init.add_listener
def _on_locust_init(environment, **_):
    # stop immediately; don’t wait for graceful wind down
    environment.stop_timeout = 0

    # Register a message handler so both master and workers react to global abort
    runner = getattr(environment, "runner", None)
    if not runner:
        return

    def _handle_global_abort(env, msg, **kwargs):
        reason = ""
        try:
            data = getattr(msg, "data", {}) or {}
            reason = data.get("reason") or ""
        except Exception:
            pass
        _trigger_global_abort(
            env, f"Global abort requested. {reason}", dump_html=None, broadcast=True
        )

    try:
        runner.register_message("global-abort", _handle_global_abort)
    except Exception as e:
        logger.debug("register_message failed (non-distributed run is fine): %s", e)


@events.quitting.add_listener
def _on_quitting(environment, **_):
    """Print a final, unmissable banner at shutdown."""
    if not (GLOBAL_ABORT_EVENT.is_set() or GLOBAL_ABORT_REASON):
        return
    reason = GLOBAL_ABORT_REASON or "Aborted"
    banner = (
        "\n" + "=" * 80 + "\n"
        " LOAD TEST ABORTED\n" + "-" * 80 + "\n"
        f"{reason}\n\n{NO_WORK_ERROR_MESSAGE}\n" + "=" * 80 + "\n"
    )
    # Print to stdout and log as error so it's visible in any context
    try:
        print(banner, flush=True)
    except Exception:
        pass
    logger.error(banner)


def _trigger_global_abort(
    environment, reason: str, dump_html: str | None = None, *, broadcast: bool = True
) -> None:
    """
    Set a global flag so all users bail, set a failing exit code,
    and in distributed mode coordinate master<->workers via custom messages.
    """
    global GLOBAL_ABORT_REASON
    if GLOBAL_ABORT_EVENT.is_set():
        return

    GLOBAL_ABORT_REASON = reason
    GLOBAL_ABORT_EVENT.set()

    logger.error("Aborting load test: %s", reason)
    logger.error(NO_WORK_ERROR_MESSAGE)

    if dump_html:
        try:
            ts = int(time.time())
            out = Path(f"no_work_{ts}.html").resolve()
            out.write_text(dump_html, encoding="utf-8")
            logger.error("No-work HTML dumped to %s", out)
        except Exception as e:
            logger.error("Failed to dump no-work HTML (%s)", e)

    try:
        if hasattr(environment, "process_exit_code"):
            environment.process_exit_code = 2
    except Exception:
        pass

    runner = getattr(environment, "runner", None)
    if not runner:
        return

    try:
        # Worker that discovers the problem -> tell master
        if isinstance(runner, runners.WorkerRunner):
            runner.send_message("global-abort", {"reason": reason})

        # Master -> broadcast to all workers
        if broadcast and isinstance(runner, runners.MasterRunner):
            runner.send_message("global-abort", {"reason": reason})

        runner.quit()
    except Exception as e:
        logger.error("Error quitting runner: %s", e)


# ---------- helpers ----------


def _is_local(path_or_url: str, base: str) -> bool:
    if not path_or_url:
        return False
    if path_or_url.startswith("/"):
        return True
    parsed = urlparse(path_or_url)
    if not parsed.scheme:
        return True
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
    """
    Extract form action, supersedes, reserve URL
    and review endpoints from an asset page.
    """

    def __init__(self, base_url: str):
        super().__init__()
        self.base_url = base_url
        self.in_transcription_form = False
        self.form_action = None
        self.supersedes = None
        self.reserve_url = None
        self.review_url = None
        self.submit_url = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "form":
            if a.get("id") == "transcription-editor":
                self.in_transcription_form = True
                action = a.get("action")
                if action is not None:
                    resolved = (
                        self.base_url
                        if action.strip() == ""
                        else urljoin(self.base_url, action)
                    )
                    self.form_action = resolved
                review_attr = a.get("data-review-url")
                if review_attr:
                    self.review_url = urljoin(self.base_url, review_attr)
                submit_attr = a.get("data-submit-url")
                if submit_attr:
                    self.submit_url = urljoin(self.base_url, submit_attr)
        elif tag == "input":
            if a.get("name") == "supersedes" and a.get("value"):
                self.supersedes = a["value"]
        elif tag == "script":
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


# ---------- users ----------


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
    current_review_url_path: str | None = None
    current_submit_url_path: str | None = None

    next_redirect_path: str = NEXT_ASSET_PATH
    next_redirect_label: str = "next asset (redirect)"

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
        # simulate normal page load
        self.client.get(AJAX_STATUS_PATH, name="AJAX status")
        self.client.get(AJAX_MSG_PATH, name="AJAX messaging")

    def _get(self, path_or_url: str, *, page: bool = True, **kwargs):
        r = self.client.get(path_or_url, **kwargs)
        if page:
            self._after_request_ajax()
        return r

    def _post(self, path_or_url: str, **kwargs):
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

        if parser.review_url:
            rvu = urlparse(parser.review_url)
            self.current_review_url_path = rvu.path + (
                ("?" + rvu.query) if rvu.query else ""
            )
        else:
            self.current_review_url_path = None

        if parser.submit_url:
            su = urlparse(parser.submit_url)
            self.current_submit_url_path = su.path + (
                ("?" + su.query) if su.query else ""
            )
        else:
            self.current_submit_url_path = None

        if not self.current_form_action_path:
            if ABORT_WHEN_NO_WORK:
                _trigger_global_abort(
                    self.environment,
                    f"No work available (no transcription form) on {r.url}",
                    (r.text or "") if NO_WORK_DUMP_HTML else None,
                    broadcast=True,
                )
            else:
                logger.info("No transcription form on %s; treating as no work", r.url)
                self.current_target_path = None
                self.current_review_url_path = None
                self.current_submit_url_path = None
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

        if (
            self.current_form_action_path is None
            and self.current_review_url_path is None
        ):
            self._parse_asset_page_and_reserve(target_path)

        csrftoken = self.client.cookies.get(CSRF_COOKIE_NAME)

        if not csrftoken and CSRF_SEED_PATH:
            self._get(CSRF_SEED_PATH, name="csrf seed", page=True)
            self._parse_asset_page_and_reserve(target_path)
            csrftoken = self.client.cookies.get(CSRF_COOKIE_NAME)

        return csrftoken

    def _follow_next(self, redirect_path: str, label: str) -> str | None:
        """
        Follow the next-* redirect. If it lands on the homepage, treat that as no work.
        """
        last_body = None
        for attempt in range(1, REDIRECT_RETRIES + 1):
            with self.client.get(
                redirect_path,
                name=label,
                allow_redirects=True,
                catch_response=True,
            ) as resp:
                try:
                    last_body = (resp.text or "")[:10000]
                except Exception:
                    last_body = None

                if 200 <= resp.status_code < 400:
                    final_path = urlparse(resp.url).path or "/"
                    if final_path == HOMEPAGE_PATH:
                        msg = f"{label} landed on homepage -> no work"
                        resp.failure(msg)
                        logger.error(msg)
                        if ABORT_WHEN_NO_WORK:
                            _trigger_global_abort(
                                self.environment,
                                f"No work available from {label} ({redirect_path})",
                                last_body if NO_WORK_DUMP_HTML else None,
                                broadcast=True,
                            )
                        return None
                    return final_path

                msg = (
                    f"redirect failed (status={resp.status_code}) "
                    f"attempt={attempt}/{REDIRECT_RETRIES}"
                )
                resp.failure(msg)
                logger.warning("%s retry: %s", label, msg)

            sleep(REDIRECT_BACKOFF * attempt)

        logger.error("%s: all %d retries failed", label, REDIRECT_RETRIES)
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
            logger.warning("No form action parsed for %s; skipping POST", target_path)
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

    def _review_decision(self, target_path: str, decision: str) -> None:
        if not self.current_review_url_path:
            return
        base = self.environment.host.rstrip("/")
        referer = urljoin(base + "/", target_path.lstrip("/"))
        csrftoken = self.client.cookies.get(CSRF_COOKIE_NAME) or ""

        form = {"csrfmiddlewaretoken": csrftoken, "decision": decision}
        name = "review accept" if decision == "accept" else "review reject"
        self._post(
            self.current_review_url_path,
            data=form,
            headers={"X-CSRFToken": csrftoken, "Referer": referer},
            name=name,
        )

    @task
    def browse_and_submit(self):
        # if someone already pulled the plug, stop this user
        if GLOBAL_ABORT_EVENT.is_set():
            raise StopUser()

        if not self.current_target_path:
            new_path = self._follow_next(
                self.next_redirect_path, self.next_redirect_label
            )
            if new_path is None:
                return
            self.current_target_path = new_path
            self.current_form_action_path = None
            self.current_supersedes = None
            self.current_reserve_path = None
            self.current_review_url_path = None
            self.current_submit_url_path = None
        else:
            maybe_switch = getattr(self, "is_reviewer", False) is False
            if maybe_switch and random.random() >= SAME_PAGE_REPEAT_PROB:
                new_path = self._follow_next(
                    self.next_redirect_path, self.next_redirect_label
                )
                if new_path is None:
                    return
                self.current_target_path = new_path
                self.current_form_action_path = None
                self.current_supersedes = None
                self.current_reserve_path = None
                self.current_review_url_path = None
                self.current_submit_url_path = None

        csrftoken = self._ensure_csrf(self.current_target_path)
        if not csrftoken:
            if self.current_target_path:
                self._get(
                    self.current_target_path, name="target page (no CSRF)", page=True
                )
            return

        if getattr(self, "is_reviewer", False):
            do_edit = random.random() < REVIEW_EDIT_PROB
            if do_edit:
                self._review_decision(self.current_target_path, "reject")
                self._parse_asset_page_and_reserve(self.current_target_path)
                csrftoken = self._ensure_csrf(self.current_target_path) or ""
                if csrftoken:
                    self._post_then_get_same_page(
                        self.current_target_path, csrftoken, "review edit save"
                    )
            else:
                self._review_decision(self.current_target_path, "accept")

            self.current_target_path = None
            self.current_form_action_path = None
            self.current_supersedes = None
            self.current_reserve_path = None
            self.current_review_url_path = None
            self.current_submit_url_path = None
            return

        # Transcriber branch
        self._post_then_get_same_page(self.current_target_path, csrftoken, "target")

        if random.random() < SAME_PAGE_REPEAT_PROB:
            csrftoken = self.client.cookies.get(CSRF_COOKIE_NAME) or self._ensure_csrf(
                self.current_target_path
            )
            if csrftoken:
                self._post_then_get_same_page(
                    self.current_target_path, csrftoken, "target (repeat)"
                )


class AnonUser(BaseBrowsingUser):
    """Anonymous user flow."""

    def on_start(self):
        self._load_homepage_and_resources()


class AuthUser(BaseBrowsingUser):
    """Authenticated user flow."""

    chosen_username: str | None = None
    chosen_email: str | None = None
    is_reviewer: bool = False

    def _pick_fixture_user(self):
        index = random.randint(1, TEST_USER_COUNT)
        username = f"{TEST_USER_PREFIX}{index:05d}"
        email = f"{username}@{TEST_USER_DOMAIN}"
        self.chosen_username = username
        self.chosen_email = email

    def _login_once(self, login_url: str, referer: str) -> bool:
        csrftoken = self.client.cookies.get(CSRF_COOKIE_NAME) or ""
        if not csrftoken:
            self._get(login_url, name="login page", page=True)
            csrftoken = self.client.cookies.get(CSRF_COOKIE_NAME) or ""

        assert self.chosen_username and self.chosen_email
        identifier = (
            self.chosen_username if random.random() < 0.5 else self.chosen_email
        )

        wrong = random.random() < LOGIN_BAD_PASSWORD_PROB
        password = TEST_USER_PASSWORD if not wrong else TEST_USER_PASSWORD + "x"

        form = {
            "username": identifier,
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

        self.is_reviewer = random.random() < REVIEWER_SHARE
        if self.is_reviewer:
            self.next_redirect_path = NEXT_REVIEWABLE_ASSET_PATH
            self.next_redirect_label = "next reviewable (redirect)"
        else:
            self.next_redirect_path = NEXT_ASSET_PATH
            self.next_redirect_label = "next asset (redirect)"

        self._load_homepage_and_resources(name_suffix="(authed)")
