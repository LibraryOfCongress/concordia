=========
concordia
=========


Basic Setup and Deploy
======================

::

    $ git clone https://bitbucket.org/rohgupta/concordia.git
    $ cd concordia
    $ virtualenv env
    $ source env/bin/activate
    $ pip install -r requirements.txt
    $ docker-compose up

Browse to `localhost <http://localhost>`_


Development
===========

You may wish to run the Django development server on your local host instead of
within a Docker container. It is easy to set up a Python virtual environment to
work in.

Configuration
-------------

See the section below for config.json.

Serve
-----

Instead of doing ``docker-compose up`` as above, instead do the following::

    $ docker-compose up -d db

This will keep our database in its container for convenience.

Next, set up a Python virtual environment::

    $ python3 -m venv env
    $ source env/bin/activate
    $ pip install -r requirements.txt

Edit, or create the config/config-optional-override.json and set the file content to: {"mode":"mac"}


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



config.json
-----
Settings for the concordia app reside in config/config.json.

The config.json file is composed of top level stanzas, with a minimum stanza name of "production".

Values in the config.json are accessed using the Config class with "from config import Config". (You may need to set
the python sys.path value to import Config).

Once Config has been imported, values are accessed with Config.Get("<config key>") (replace <config key> with the
actual key value.

By default, the "production" stanza is used. To override the stanza, create the file config-optional-override.json
in the config dir. This json file will have a single json key/value with the key name as "mode". For example,
to use the "unittest" stanza, set the config-optional-override.json to: {"mode":"unittest"}

For development on a mac, set the config-optional-override.json file to: {"mode":"mac"}. This stanza has a setting for
database connections to 0.0.0.0 on port 54321.

If a key/value is added to config.json, it must added to all stanzas. A new stanza can be created by copying the
"production" stanza and adding it to end of the config.json file. Remember to set the config-optional-override.json
value to match the new stanza name.