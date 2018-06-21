=========
concordia
=========

=============
Prerequisites
=============
Docker


Running Concordia
=================

::

    $ git clone https://github.com/LibraryOfCongress/concordia.git
    $ cd concordia
    $ docker-compose up

Browse to `localhost <http://localhost>`_


Development Environment
=======================

You may wish to run the Django development server on your localhost instead of
within a Docker container. It is easy to set up a Python virtual environment to
work in.


Serve
-----

Instead of doing ``docker-compose up`` as above, instead do the following::

    $ docker-compose up -d db
    $ docker-compose up -d rabbit

This will keep the database in its container for convenience.

Next, set up a Python virtual environment::

    $ python3 -m venv .venv
    $ source .venv/bin/activate
    $ pip install -r requirements_devel.txt

Finally, configure the Django settings, run migrations, and launch the development server::

    $ export DJANGO_SETTINGS_MODULE = "concordia.settings_dev"
    $ ./manage.py migrate
    $ ./manage.py runserver


Code Quality
------------

Install black <https://pypi.org/project/black/> and integrate it with your editor of choice.
Run flake8 <http://flake8.pycqa.org/en/latest/> to ensure you don't increase the warning count or introduce errors with your commits.
This project uses EditorConfig <https://editorconfig.org> for code consistency.

Django projects should extend the standard Django settings model for project configuration. Django projects should also make use of the Django test framework for unit tests.

setup.cfg contains configuration for pycodestyle, isort <https://pypi.org/project/isort/> and flake8.

Unify – modifies strings to use consistent quote style
https://pypi.org/project/unify/

The virtual env directory should be named .venv and it's preferred to use Pipenv to manage the virtual environment.

Configure your editor to run black, isort, and unify on each file at save time. 
If you can't modify your editor, here is how to run the code quality tools manually:

    $ black .
    $ isort --recursive .
    $ unify --in-place *.py && unify --in-place **/*.py

Misc
----

To generate a model graph, do::

    $ docker-compose up -d app
    $ docker-compose exec app bash
    # cd concordia/static/img
    # python3 ./manage.py graph_models concordia > tx.dot
    # dot -Tsvg tx.dot -o tx.svg