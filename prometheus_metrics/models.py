from prometheus_client import Counter

model_inserts_total = Counter(
    "django_model_inserts_total", "Number of inserts on a certain model", ["model"]
)
model_updates_total = Counter(
    "django_model_updates_total", "Number of updates on a certain model", ["model"]
)
model_deletes_total = Counter(
    "django_model_deletes_total", "Number of deletes on a certain model", ["model"]
)


def MetricsModelMixin(name):
    class Mixin(object):
        def _do_insert(self, *args, **kwargs):
            model_inserts_total.labels(name).inc()
            return super(Mixin, self)._do_insert(*args, **kwargs)

        def _do_update(self, *args, **kwargs):
            model_updates_total.labels(name).inc()
            return super(Mixin, self)._do_update(*args, **kwargs)

        def _do_delete(self, *args, **kwargs):
            model_deletes_total.labels(name).inc()
            return super(Mixin, self).delete(*args, **kwargs)

    return Mixin
