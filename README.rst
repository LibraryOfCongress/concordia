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

Next, set up a Python virtual environment, install pipenv <https://docs.pipenv.org/>, and other Python prerequisites::

    $ python3 -m venv env
    $ source env/bin/activate
    $ pip3 install pipenv
    $ pipenv install --system --dev --deploy

Finally, configure the Django settings, run migrations, and launch the development server::

    $ export DJANGO_SETTINGS_MODULE = "concordia.settings_dev"
    $ ./manage.py migrate
    $ ./manage.py runserver


Misc
----

To generate a model graph, do::

    $ docker-compose up -d app
    $ docker-compose exec app bash
    # cd concordia/static/img
    # python3 ./manage.py graph_models concordia > tx.dot
    # dot -Tsvg tx.dot -o tx.svg