#!/usr/bin/env python
from setuptools import setup, find_packages

version=__import__('concordia').get_version()

with open('README.rst', 'r') as f:
    long_description = f.read()


setup(
    name='concordia',
    version=version,
    description='Transcription crowdsourcing',
    long_description=long_description,
    packages=find_packages(),
    include_package_data=True,
    scripts=['manage.py'],
    install_requires=['Django<2.1', 'Pillow', 'psycopg2'],
    classifiers=[
        'Environment :: Web Environment',
        'Framework :: Django',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3.6',
    ],
)
