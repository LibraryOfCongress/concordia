#!/usr/bin/env python
from setuptools import find_packages, setup

VERSION = __import__("importer").get_version()
INSTALL_REQUIREMENTS = ["boto3", "celery", "requests", "Django>=2.1.5", "Pillow"]
DESCRIPTION = "Download collections of images from loc.gov"
CLASSIFIERS = """
Environment :: Web Environment
Framework :: Django :: 2.0
Development Status :: 2 - Pre-Alpha
Programming Language :: Python
Programming Language :: Python :: 3.6
""".splitlines()

with open("README.rst", "r") as f:
    LONG_DESCRIPTION = f.read()


setup(
    name="importer",
    version=VERSION,
    description=DESCRIPTION,
    long_description=LONG_DESCRIPTION,
    packages=find_packages(),
    include_package_data=True,
    install_requires=INSTALL_REQUIREMENTS,
    classifiers=CLASSIFIERS,
)
