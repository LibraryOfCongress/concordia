=========
concordia
=========


Basic Setup and Deploy
======================

::

    $ git clone https://bitbucket.org/rohgupta/concordia.git
    $ cd concordia
    $ cp env.ini_template env.ini
    $ docker-compose up

Browse to `0.0.0.0:8001 <http://0.0.0.0:8001/>`_


Development
===========

You may wish to run the Django development server on your local host instead of
within a Docker container. It is easy to set up a Python virtual environment to
work in.

Configuration
-------------

Edit your env.ini and set the following under ``[django]`` (you should comment
out the originals so that it is easy to switch between running the app 
containerized or on your "local host")::

    DB_HOST = 0.0.0.0
    DB_PORT = 54321

Conversely, if you export a shell variable named ``CONCORDIA_ENV`` to point to a
local file, you won't need to edit the container's ``env.ini`` file. For example,
copy ``env.ini`` to ``env-dev.ini`` and add the following to your ``~/.bashrc``
file::

    export CONCORDIA_ENV=env-dev.ini

Save and re-source: ``source ~/.bashrc``

Serve
-----

Instead of doing ``docker-compose up`` as above, instead do the following::

    $ docker-compose up -d db

This will keep our database in its container for convenience.

Next, set up a Python virtual environment::

    $ python3 -m venv .venv
    $ source .venv/bin/activate
    $ pip install -e .
    $ pip install -r requirements/devel.pip

Finally, run migrations and launch the development server::

    $ ./manage.py migrate
    $ ./manage.py runserver


Misc
----

To generate a model graph, do::

    $ docker-compose up -d app
    $ docker-compose exec app bash
    # manage.py graph_models transcribr > tx.dot
    # dot -Tsvg tx.dot -o tx.svg
