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


Configuration
-------------

See the section below for config.json.

Serve
-----

Instead of doing ``docker-compose up`` as above, instead do the following::

    $ docker-compose up -d db
    $ docker-compose up -d rabbit

This will keep our database in its container for convenience.

Next, set up a Python virtual environment::

    $ python3 -m venv .venv
    $ source .venv/bin/activate
    $ pip install -r requirements_devel.txt

Edit, or create the config/config-optional-override.json and set the file content to: {"mode":"mac"}


Finally, run migrations and launch the development server::

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

If your editor is properly configured, these manual steps shouldn't be necessary to run before committing to git:

    $ black .
    $ isort .
    $ unify .

Misc
----

To generate a model graph, do::

    $ docker-compose up -d app
    $ docker-compose exec app bash
    # cd concordia/static/img
    # python3 ./manage.py graph_models concordia > tx.dot
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