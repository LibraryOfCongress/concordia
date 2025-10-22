import datetime
from typing import Any

import markdown
from django.core.cache import cache
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.template import Context, Template
from django.utils.http import http_date
from django.utils.timezone import now
from django.views.generic import RedirectView

from concordia.models import Guide, SimplePage, SiteReport
from concordia.parser import paginate_blog_posts

from .decorators import default_cache_control


@default_cache_control
def simple_page(
    request: HttpRequest,
    path: str | None = None,
    slug: str | None = None,
    body_ctx: dict[str, Any] | None = None,
    template: str = "static-page.html",
) -> HttpResponse:
    """
    Renders a simple Markdown-based page stored in the `SimplePage` model.

    If no `path` is provided, defaults to the current request path. Markdown is
    rendered with optional associated guide content. Breadcrumbs and language
    detection are computed from the URL structure.

    Request Parameters:
        path (str, optional): The database path of the page. Defaults to the
            current request path.
        slug (str, optional): Unused in current logic; passed for route compatibility.
        body_ctx (dict[str, Any], optional): Additional context injected into the page
            body during rendering.
        template (str): Template used to render the page.

    Returns:
        HttpResponse: Rendered HTML of the simple page.
    """
    if not path:
        path = request.path

    if body_ctx is None:
        body_ctx = {}

    page = get_object_or_404(SimplePage, path=path)

    md = markdown.Markdown(extensions=["meta"])

    breadcrumbs = []
    path_components = request.path.strip("/").split("/")
    for i, segment in enumerate(path_components[:-1], start=1):
        breadcrumbs.append(
            ("/%s/" % "/".join(path_components[0:i]), segment.replace("-", " ").title())
        )
    breadcrumbs.append((request.path, page.title))

    language_code = "en"
    if request.path.replace("/", "").endswith("-esp"):
        language_code = "es"

    ctx = {
        "language_code": language_code,
        "title": page.title,
        "breadcrumbs": breadcrumbs,
    }

    guide = page.guide_set.all().first()
    if guide is not None:
        html = "".join((page.body, guide.body))
        ctx["add_navigation"] = True
    else:
        html = page.body
    if "add_navigation" in ctx:
        ctx["guides"] = Guide.objects.order_by("order")
    body = Template(md.convert(html))
    ctx["body"] = body.render(Context(body_ctx))
    ctx.update(body_ctx)

    resp = render(request, template, ctx)
    resp["Created"] = http_date(page.created_on.timestamp())
    return resp


@default_cache_control
def about_simple_page(
    request: HttpRequest, path: str | None = None, slug: str | None = None
) -> HttpResponse:
    """
    Renders the "about" simple page with additional cached campaign and blog stats.

    Adds the following keys to the context:
        - `report_date` (datetime): Yesterday’s date.
        - `campaigns_published` (int): Count from active SiteReport.
        - `assets_published` (int): Active + retired total.
        - `assets_completed` (int): Active + retired total.
        - `assets_waiting_review` (int): Active + retired total.
        - `users_activated` (int): From active SiteReport.
        - `blog_posts` (Callable): Reference to blog post fetcher.

    Returns:
        HttpResponse: Rendered HTML of the about page with campaign stats.
    """
    context_cache_key = "about_simple_page-about_context"
    about_context = cache.get(context_cache_key)
    if not about_context:
        try:
            active_campaigns = SiteReport.objects.filter(
                report_name=SiteReport.ReportName.TOTAL
            ).latest()
        except SiteReport.DoesNotExist:
            active_campaigns = SiteReport(
                campaigns_published=0,
                assets_published=0,
                assets_completed=0,
                assets_waiting_review=0,
                users_activated=0,
            )
        try:
            retired_campaigns = SiteReport.objects.filter(
                report_name=SiteReport.ReportName.RETIRED_TOTAL
            ).latest()
        except SiteReport.DoesNotExist:
            retired_campaigns = SiteReport(
                assets_published=0,
                assets_completed=0,
                assets_waiting_review=0,
            )
        about_context = {
            "report_date": now() - datetime.timedelta(days=1),
            "campaigns_published": active_campaigns.campaigns_published,
            "assets_published": active_campaigns.assets_published
            + retired_campaigns.assets_published,
            "assets_completed": active_campaigns.assets_completed
            + retired_campaigns.assets_completed,
            "assets_waiting_review": active_campaigns.assets_waiting_review
            + retired_campaigns.assets_waiting_review,
            "users_activated": active_campaigns.users_activated,
            "blog_posts": paginate_blog_posts(),
            "about_page": True,
        }
        cache.set(context_cache_key, about_context, 60 * 60)

    return simple_page(request, path, slug, about_context)


# These views are to make sure various links to help-center URLs don't break
# when the URLs are changed to not include help-center and can be removed after
# all links are updated.


class HelpCenterRedirectView(RedirectView):
    def get_redirect_url(self, *args, **kwargs):
        path = kwargs["page_slug"]
        return "/get-started/" + path + "/"


class HelpCenterSpanishRedirectView(RedirectView):
    def get_redirect_url(self, *args, **kwargs):
        path = kwargs["page_slug"]
        return "/get-started-esp/" + path + "-esp/"


# End of help-center views
