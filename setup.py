#!/usr/bin/env python
from setuptools import find_packages, setup

VERSION = __import__("concordia").get_version()
INSTALL_REQUIREMENTS = ["boto3", "Django>=2.1.7"]
SCRIPTS = ["manage.py"]
DESCRIPTION = "Transcription crowdsourcing"
CLASSIFIERS = """\
Environment :: Web Environment
Framework :: Django
Programming Language :: Python
Programming Language :: Python :: 3.6
""".splitlines()

with open("README.md", "r") as f:
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
    use_scm_version={
        "write_to": "version.txt",
        "tag_regex": r"^(?P<prefix>v)?(?P<version>[^\+]+)(?P<suffix>.*)?$",
    },
    setup_requires=["setuptools_scm"],
)
