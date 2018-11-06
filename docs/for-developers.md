# For Developers

## Prerequisites

This application can run on a single Docker host using docker-compose.
(recommended for development environments). For production, see the
[cloudformation](cloudformation/) directory for AWS Elastic Container Service
stack templates.

## Running Concordia

    $ git clone https://github.com/LibraryOfCongress/concordia.git
    $ cd concordia
    $ docker-compose up

Browse to [localhost](http://localhost)

### Local Development Environment

You may wish to run the Django development server on your localhost
instead of within a Docker container. It is easy to set up a Python
virtual environment to work in.

#### Python Dependencies

Python dependencies are managed using [pipenv](https://docs.pipenv.org/).

If you want to add a new Python package requirement to the application
environment, it must be added to the Pipfile and the Pipfile.lock file.
This can be done with the command:

    $ pipenv install <package>

If the dependency you are installing is only of use for developers, mark it as
such using `--dev` so it will not be deployed to servers — for example:

    $ pipenv install --dev django-debug-toolbar

If you manually add package names to Pipfile, then you need to update
the Pipfile.lock file:

    $ pipenv lock

Both the Pipfile and the Pipfile.lock file must be committed to the
source code repository.

#### Setting up a local development server

Instead of doing `docker-compose up` as above, instead do the following:

    $ docker-compose up -d db rabbit importer

This will keep the database in its container for convenience.

Next, we need to setup a Python virtual environment and install our Python dependencies:

1. Install [pipenv](https://docs.pipenv.org/) either using a tool like
   [Homebrew](https://brew.sh) (`brew install pipenv`) or using `pip`:

    $ pip3 install pipenv

2. Let Pipenv create the virtual environment and install all of the packages,
   including our developer tools:

    $ pipenv install --dev

3. Configure the Django settings module in the `.env` file which Pipenv will use
   to automatically populate the environment for every command it runs:

    $ echo DJANGO_SETTINGS_MODULE="concordia.settings_dev" >> .env

    You can use this to set any other values you want to customize, such as
    `POSTGRESQL_PW` or `POSTGRESQL_HOST`.

4. Apply any database migrations:

    $ pipenv run ./manage.py migrate

5. Run the development server:

    $ pipenv run ./manage.py runserver

#### Import Data

Once the database, rabbitMQ service, importer and the application
are running, you're ready to import data.
First, [create a Django admin user](https://docs.djangoproject.com/en/2.1/intro/tutorial02/#creating-an-admin-user)
and log in as that user.
Then, go to the Admin area (under Account) and click "Bulk Import Items".
Upload a spreadsheet populated according to the instructions. Once all the import
jobs are complete, publish the Campaigns, Projects, Items and Assets that you
wish to make available.

#### Data Model Graph

To generate a model graph, make sure that you have GraphViz installed (e.g.
`brew install graphviz` or `apt-get install graphviz`) and use the
django-extensions `graph_models` command:

    $ dot -Tsvg <(pipenv run ./manage.py graph_models concordia importer) -o concordia.svg

## Front-End Testing

### Installing front-end tools

1. Use a package manager such as Yarn or NPM to install our development tools:

    $ yarn install --dev
    $ npm install

2. If you need a list of public-facing URLs for testing, there's a management
   command which may be helpful:

    $ pipenv run ./manage.py print_frontend_test_urls

### Accessibility testing using aXe

Automated tools such as [aXe](https://www.deque.com/axe/) are useful for
catching low-hanging fruit and regressions. You run aXe against a development
server by giving it one or more URLs:

    $ yarn run axe --show-errors http://localhost:8000/
    $ pipenv run ./manage.py print_frontend_test_urls | xargs yarn run axe --show-errors
