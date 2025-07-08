from ninja import NinjaAPI


class CamelCaseAPI(NinjaAPI):
    def add_api_operation(self, path, methods, view_func, **kwargs):
        # Ensure by_alias=True is always set unless explicitly overridden
        if "by_alias" not in kwargs:
            kwargs["by_alias"] = True
        return super().add_api_operation(path, methods, view_func, **kwargs)
