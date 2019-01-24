# Concordia Tests

This directory contains tests for the concordia app. It has a
combination of Django TestCases (which will create a test database
before running each test), and pyunit tests.

## Pre-requisites

-   Regarding Django TestCases, since these tests create a test database, the docker container with the db must be running — for example:

    ```console
    $ docker-compose up -d db
    ```

-   Use the settings module with defaults appropriate for testing:

    ```console
    $ export DJANGO_SETTINGS_MODULE=concordia.settings_test
    ```

    or

    ```console
    $ pipenv run manage.py test --settings=concordia.settings_test
    ```

## Running the tests

-   To run all tests:

    ```console
    $ python manage.py test concordia
    ```

*   To run a single unittest module:

    ```console
    $ python manage.py test concordia.tests.test_view
    ```

*   To run a single unittest in a django unittest module:
    ```console
    $ python manage.py test
    concordia.tests.test_view.ViewTest1.test_addition
    ```
