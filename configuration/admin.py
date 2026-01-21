from typing import Any

from django.contrib import admin, messages
from django.http import HttpRequest, HttpResponse
from django.template.response import TemplateResponse
from django.utils.html import format_html

from configuration.models import Configuration


@admin.register(Configuration)
class ConfigurationAdmin(admin.ModelAdmin):
    """
    Admin configuration for the `Configuration` model.

    Behavior:
        - Displays the key, raw value, and description in the changelist.
        - Provides a read-only `validated_value` field on the change form that
          shows the interpreted value as returned by `Configuration.get_value`.
        - Overrides `changeform_view` to add a two-step confirmation flow when
          saving changes, including a preview of the parsed value. Also handles
          an explicit cancel action by rebuilding the normal change form
          context rather than delegating to the base implementation.
    """

    list_display = ("key", "value", "description")
    readonly_fields = ("validated_value",)

    def validated_value(self, obj: Configuration) -> str:
        """
        Render the parsed configuration value and explanatory text.

        Notes:
            This method does not alter the base `ModelAdmin` behavior. It is a
            helper used by the change form to display both the interpreted
            value from `Configuration.get_value()` and a short explanation
            that this parsed value is what application code will consume.

        Args:
            obj (Configuration): The instance being edited.

        Returns:
            str: HTML-safe string produced by `format_html` containing the
                parsed value and explanatory note.
        """
        return format_html(
            "<div>{}</div><div style='color: #777; font-size: 0.9em;'>{}</div>",
            obj.get_value(),
            "This is the interpreted value based on the selected data type. "
            "This value is what will be seen by the code that uses this "
            "configuration.",
        )

    def changeform_view(
        self,
        request: HttpRequest,
        object_id: str | None = None,
        form_url: str = "",
        extra_context: dict[str, Any] | None = None,
    ) -> HttpResponse:
        """
        Override the base change form view to add a confirmation step.

        Differences from the base implementation:
            - On initial POST, validate the form and, if valid, render a
              confirmation template that previews the parsed value produced by
              `Configuration.get_value()`.
            - On confirmation POST (`_confirm_update`), save the instance and
              show a success message.
            - On cancel POST (`cancel_update`), rebuild the standard change
              form context manually and re-render the change form instead of
              delegating to the base method (which would otherwise proceed with
              the change because it is a POST).
            - For all other flows, fall back to the base implementation.

        Args:
            request (HttpRequest): The current request.
            object_id (str | None): Primary key of the object being edited.
            form_url (str): Form action URL.
            extra_context (dict[str, Any] | None): Extra template context.

        Returns:
            HttpResponse: Either the confirmation screen, the re-rendered
                change form, or the default response from the base view.
        """
        obj = self.get_object(request, object_id)

        if request.method == "POST":
            if "_confirm_update" in request.POST:
                # Second POST: confirmation of update
                form = self.get_form(request, obj)(request.POST, instance=obj)
                if form.is_valid():
                    form.save()
                    self.message_user(request, "Configuration updated and cached.")
                    return self.response_post_save_change(request, form.instance)
                else:
                    self.message_user(
                        request, "Invalid data on confirmation.", level=messages.ERROR
                    )
            elif "cancel_update" in request.POST:
                form = self.get_form(request, obj)(request.POST, instance=obj)

                admin_form = admin.helpers.AdminForm(
                    form,
                    list(self.get_fieldsets(request, obj)),
                    self.get_prepopulated_fields(request, obj),
                    self.get_readonly_fields(request, obj),
                    model_admin=self,
                )
                # We unfortunately have to manually construct this context, since using
                # super causes it to just perform the cancelled change, because this is
                # a POST request
                context = {
                    **self.admin_site.each_context(request),
                    "title": f"Edit Configuration: {obj.key}",
                    "adminform": admin_form,
                    "inline_admin_formsets": [],
                    "media": self.media + form.media,
                    "object_id": object_id,
                    "original": obj,
                    "opts": self.model._meta,
                    "add": False,
                    "change": True,
                    "is_popup": False,
                    "save_as": self.save_as,
                    "has_view_permission": self.has_view_permission(request, obj),
                    "has_add_permission": self.has_add_permission(request),
                    "has_change_permission": self.has_change_permission(request, obj),
                    "has_delete_permission": self.has_delete_permission(request, obj),
                    "form_url": form_url,
                    "to_field": None,
                    "has_editable_inline_admin_formsets": False,
                }
                return self.render_change_form(
                    request,
                    context=context,
                    add=False,
                    change=True,
                    form_url=form_url,
                    obj=obj,
                )

            else:
                # First POST: validate and show confirmation screen
                form = self.get_form(request, obj)(request.POST, instance=obj)
                if form.is_valid():
                    new_instance = form.save(commit=False)
                    try:
                        parsed_value = new_instance.get_value()
                    except Exception as e:
                        self.message_user(
                            request, f"Validation failed: {e}", level=messages.ERROR
                        )
                        return super().changeform_view(
                            request, object_id, form_url, extra_context=extra_context
                        )

                    context = {
                        "title": (
                            f"Confirm Update of Configuration '{new_instance.key}'"
                        ),
                        "original": self.model._default_manager.get(pk=obj.pk),
                        "new_instance": new_instance,
                        "parsed_value": parsed_value,
                        "opts": self.model._meta,
                        "object_id": object_id,
                        "form_url": form_url,
                        "request": request,
                    }
                    return TemplateResponse(
                        request, "admin/configuration_confirm_update.html", context
                    )

        return super().changeform_view(request, object_id, form_url, extra_context)
