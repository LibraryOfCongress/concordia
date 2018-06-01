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
    $ cp env.ini_template env.ini
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
    $ cp env-devel.ini_template env.ini

This will keep our database in its container for convenience.

Next, set up a Python virtual environment::

    $ python3 -m venv env
    $ source env/bin/activate
    $ pip install -r requirements_devel.txt


Finally, run migrations and launch the development server::

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

