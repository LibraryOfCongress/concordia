from setuptools_scm import get_version
import functools


@functools.lru_cache(maxsize=None)
def get_concordia_version():
    return get_version()
