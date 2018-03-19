concordia
=========


Setup and Deploy
----------------

::

    $ git clone https://bitbucket.org/rohgupta/concordia.git
    $ cd concordia
    $ cp env.ini_template env.ini
    $ docker-compose up

Browse to `0.0.0.0:8001 <http://0.0.0.0:8001/>`_


Devlop
------

You may wish to run the Django development server on your local host instead of
within a Docker container. It is easy to set up a Python virtual environment to
work in.

Edit your env.ini and set the following under ``[django]`` (you should comment
out the originals so that it is easy to switch between running the app 
containerized or on your "local host")::

    DB_HOST = 0.0.0.0
    DB_PORT = 54321


Instead of doing ``docker-compose up`` as above, instead do::

    $ docker-compose up -d db
    $ python3 -m venv .venv
    $ source .venv/bin/activate
    $ pip install -e .
    $ pip install -r requirements/devel.pip
    $ manage.py migrate
    $ manage.py runserver
