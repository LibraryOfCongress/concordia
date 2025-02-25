from configuration.models import Configuration


def configuration_value(key):
    config = Configuration.objects.get(key=key)
    return config.get_value()
