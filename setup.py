#!/usr/bin/env python
from setuptools import setup, find_packages

VERSION = __import__("concordia").get_version()
INSTALL_REQUIREMENTS = ["Django<2.1"]
SCRIPTS = ["manage.py"]
DESCRIPTION = "Transcription crowdsourcing"
CLASSIFIERS = """\
Environment :: Web Environment
Framework :: Django
Programming Language :: Python
Programming Language :: Python :: 3.6
""".splitlines()

with open("README.rst", "r") as f:
    LONG_DESCRIPTION = f.read()


setup(
    name="concordia",
    version=VERSION,
    description=DESCRIPTION,
    long_description=LONG_DESCRIPTION,
    packages=find_packages(),
    include_package_data=True,
    scripts=SCRIPTS,
    install_requires=INSTALL_REQUIREMENTS,
    classifiers=CLASSIFIERS,
)
