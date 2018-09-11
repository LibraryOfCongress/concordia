===============
Importer Tests
===============

This directory contains tests for the importer application. It has a combination of Django TestCases (which will create a
test database before running each test), and pyunit tests.

Pre-requisites
==============

Regarding Django TestCases, since these tests create a test database, the docker container with the db must be running.
    $ docker-compose up -d db


Set the project settings for unit tests:
    $ export DJANGO_SETTINGS_MODULE=concordia.settings_test


Running the tests
=================

To run all tests:
    $ python manage.py test importer


To run a single unittest module:
    $ python manage.py test importer.tests.test_importer


To run a single unittest in a django unittest module:
    $ python manage.py test importer.tests.test_importer.CreateCampaignViewTest.test_create_item_campaign

