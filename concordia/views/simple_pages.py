import datetime

import markdown
from django.core.cache import cache
from django.shortcuts import get_object_or_404, render
from django.template import Context, Template
from django.utils.http import http_date
from django.utils.timezone import now
from django.views.generic import RedirectView

from concordia.models import Guide, SimplePage, SiteReport
from concordia.parser import fetch_blog_posts

from .decorators import default_cache_control


@default_cache_control
def simple_page(
    request, path=None, slug=None, body_ctx=None, template="static-page.html"
):
    """
    Basic content management using Markdown managed in the SimplePage model

    This expects a pre-existing URL path matching the path specified in the database::

        path("about/", views.simple_page, name="about"),
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
def about_simple_page(request, path=None, slug=None):
    """
    Adds additional context to the "about" SimplePage
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
            "blog_posts": fetch_blog_posts(),
        }
        cache.set(context_cache_key, about_context, 60 * 60)

    return simple_page(request, path, slug, about_context, template="about.html")


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
