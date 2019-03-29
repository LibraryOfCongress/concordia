# For Developers

## Prerequisites

This application can run on a single Docker host using docker-compose.
(recommended for development environments). For production, see the
[cloudformation](cloudformation/) directory for AWS Elastic Container Service
stack templates.

## Running Concordia

### Docker Compose

```bash
$ git clone https://github.com/LibraryOfCongress/concordia.git
$ cd concordia
$ docker-compose up
```

Browse to [localhost](http://localhost)

If you're intending to edit static resources, templates, etc. and would like to
enable Django's DEBUG mode ensure that your environment has `DEBUG=true` set
before you run `docker-compose up` for the `app` container. The easiest way to
do this permanently is to add it to the `.env` file:

```bash
$ echo DEBUG=true >> .env
```

### Local Development Environment

You will likely want to run the Django development server on your localhost
instead of within a Docker container if you are working on the backend. This is
best done using the same `pipenv`-based toolchain as the Docker deployments:

#### Python Dependencies

Python dependencies and virtual environment creation are handled by
[pipenv](https://docs.pipenv.org/).

If you want to add a new Python package requirement to the application
environment, it must be added to the Pipfile and the Pipfile.lock file.
This can be done with the command:

```bash
$ pipenv install <package>
```

If the dependency you are installing is only of use for developers, mark it as
such using `--dev` so it will not be deployed to servers — for example:

```bash
$ pipenv install --dev django-debug-toolbar
```

Both the `Pipfile` and the `Pipfile.lock` files must be committed to the source
code repository any time you change them to ensure that all testing uses the
same package versions which you used during development.

#### Setting up a local development server

##### Start the support services

Instead of doing `docker-compose up` as above, instead start everything except the app:

```bash
$ docker-compose up -d db redis importer
```

This will run the database in a container to ensure that it always matches the
expected version and configuration. If you want to reset the database, simply
delete the local container so it will be rebuilt the next time you run
`docker-compose up`: `docker-compose rm --stop db`.

##### Install the application virtual environment

These steps only need to be performed the first time you setup a fresh
virtualenv environment:

1.  Ensure that you have the necessary C library dependencies available:

    -   `libmemcached`
    -   `postgresql`
    -   `node` & `npm` for the front-end tools

1.  Ensure that you have Python 3.7 or later installed

1.  Install [pipenv](https://docs.pipenv.org/) either using a tool like
    [Homebrew](https://brew.sh) (`brew install pipenv`) or using `pip`:

    ```bash
    $ pip3 install pipenv
    ```

1.  Let Pipenv create the virtual environment and install all of the packages,
    including our developer tools:

    ```bash
    $ pipenv install --dev
    ```

    n.b. if `libmemcached` is installed using Homebrew you will need to [set the CFLAGS long enough to build it](https://stackoverflow.com/questions/14803310/error-when-install-pylibmc-using-pip#comment94853072_19432949):

    ```bash
    $ CFLAGS=$(pkg-config --cflags libmemcached) LDFLAGS=$(pkg-config --libs libmemcached) pipenv install --dev
    ```

    Once it has been installed you will not need to repeat this process unless
    you upgrade the version of libmemcached or Python installed on your system.

1.  Configure the Django settings module in the `.env` file which Pipenv will use
    to automatically populate the environment for every command it runs:

    ```bash
    $ echo DJANGO_SETTINGS_MODULE="concordia.settings_dev" >> .env
    ```

    You can use this to set any other values you want to customize, such as
    `POSTGRESQL_PW` or `POSTGRESQL_HOST`.

##### Start the application server

1.  Apply any database migrations:

    ```bash
    $ pipenv run ./manage.py migrate
    ```

1.  Build the CSS:

    ```bash
    $ npx gulp build
    ```

1.  Start the development server:

    ```bash
    $ pipenv run ./manage.py runserver
    ```

#### Import Data

Once the database, redis service, importer and the application
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

```bash
$ dot -Tsvg <(pipenv run ./manage.py graph_models concordia importer) -o concordia.svg
```

## Front-End Tools

### Installing front-end tools

1. Use a package manager such as Yarn or NPM to install our development tools:

    ```bash
    $ yarn install --dev
    $ npm install
    ```

1. If you need a list of public-facing URLs for testing, there's a management
   command which may be helpful:

    ```bash
    $ pipenv run ./manage.py print_frontend_test_urls
    ```

### Accessibility testing using aXe

Automated tools such as [aXe](https://www.deque.com/axe/) are useful for
catching low-hanging fruit and regressions. You run aXe against a development
server by giving it one or more URLs:

```bash
$ yarn run axe --show-errors http://localhost:8000/
$ pipenv run ./manage.py print_frontend_test_urls | xargs yarn run axe --show-errors
```

### Static Image Compression

The `concordia/static/img` directory has a Makefile which will run an
[imagemin](http://github.com/imagemin/imagemin)-based toolchain. Use of other
tools such as [ImageOptim](https://github.com/ImageOptim/ImageOptim) may yield
better results at the expensive of portability and is encouraged at least for
comparison purposes.

```bash
$ make -C concordia/static/img/
```
