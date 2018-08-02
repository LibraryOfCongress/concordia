=========
concordia
=========

=============
Prerequisites
=============
Docker

=============
Passwords
=============


This project stores passwords in a file named .env. This file resides in the root directory of 
the concordia app and it is not included in the source code respository.

You must create this file in the concordia root directory.

This file contains seven values, which are:
::

    GRAFANA_ADMIN_PW=<grafana_admin_password_here>
    CONCORDIA_ADMIN_PW=<concordia_admin_password_here>
    POSTGRESQL_PW=<postgresql_concordia_user_password_here>
    EMAIL_HOST=<your_smtp_email_host_here>
    EMAIL_HOST_USER=<your_smtp_email_host_user_here>
    EMAIL_HOST_PASSWORD=<your_smtp_email_host_password_here>
    DEFAULT_FROM_EMAIL=<your_email_from_address_here>

Replace each <.._password_here> above with your actual password.
Add values for EMAIL_HOST,EMAIL_HOST_USER,EMAIL_HOST_PASSWORD,DEFAULT_FROM_EMAIL if you want
a functioning email capability.

The script to create the concordia admin user uses the value matching CONCORDIA_ADMIN_PW as 
the "admin" user password.

The postgresql concordia database is accessed using the username concordia and the password 
specified by POSTGRESQL_PW.
The django concordia app uses the POSTGRESQL_PW value to connect to the concordia database 
running in the db docker
container. 

The value for GRAFANA_ADMIN_PW is used to login to grafana using the admin user.

Setting the passwords in this file is the only location where user passwords are defined. 
All access to these passwords
is through the .env file. 

An example of a .env file is in the top level source directory, it is called "example_env_file".

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

Next, set up a Python virtual environment, install pipenv <https://docs.pipenv.org/>, and other 
Python prerequisites::


    $ python3 -m venv .venv
    $ source .venv/bin/activate
    $ pip3 install pipenv
    $ pipenv install --dev


Finally, configure the Django settings, run migrations, and launch the development server::

    $ export DJANGO_SETTINGS_MODULE="concordia.settings_dev"
    $ ./manage.py migrate
    $ ./manage.py runserver


Code Quality
------------

Install black <https://pypi.org/project/black/> and integrate it with your editor of choice.
Run flake8 <http://flake8.pycqa.org/en/latest/> to ensure you don't increase the warning count 
or introduce errors with your commits.
This project uses EditorConfig <https://editorconfig.org> for code consistency.

Django projects should extend the standard Django settings model for project configuration. 
Django projects should also make use of the Django test framework for unit tests.

setup.cfg contains configuration for pycodestyle, isort <https://pypi.org/project/isort/> and 
flake8.

The virtual env directory should be named .venv and it's preferred to use Pipenv to manage the 
virtual environment.


Configure your editor to run black and isort on each file at save time. 

If you can't modify your editor, here is how to run the code quality tools manually::

    $ black .
    $ isort --recursive .

Black should be run prior to isort. It's recommended to commit your code before running black, after running black, 
and after running isort so the changes from each step are visible.


Misc
----

To generate a model graph, do::

    $ docker-compose up -d app
    $ docker-compose exec app bash
    # cd concordia/static/img
    # python3 ./manage.py graph_models concordia > tx.dot
    # dot -Tsvg tx.dot -o tx.svg


Python Dependencies
-------------------

Python dependencies are managed using pipenv <https://docs.pipenv.org/>.

If you want to add a new Python package requirement to the application environment, 
it must be added to the Pipfile and the Pipfile.lock file. This can be done with the command:

    $ pipenv install <package>


If you manually add package names to Pipfile, then you need to update the Pipfile.lock file:

    $ pipenv lock


Both the Pipfile and the Pipfile.lock file must be committed to the source code repository.

