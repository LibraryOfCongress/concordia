# For Developers

## Prerequisites

This application can run on a single Docker host using docker-compose.
(recommended for development environments). See the [development Readme](../development/README.md) for more information. Note that the instructions below assume you'll be developing on your host rather than in a container. The development Readme provides instructions on performing development in a purely containerized environment, without installing any dependencies (outside of git and your container tool of choice) on the host.

For production, see the
[cloudformation](https://github.com/LibraryOfCongress/concordia/tree/master/cloudformation) directory for AWS Elastic Container Service
stack templates.

## Running Concordia

### Docker Compose

```bash
git clone https://github.com/LibraryOfCongress/concordia.git
```

If you're intending to edit static resources, templates, etc. and would like to
enable Django's DEBUG mode ensure that your environment has `DEBUG=true` set
before you run `docker-compose up` for the `app` container. The easiest way to
do this permanently is to add it to the `.env` file:

```bash
echo DEBUG=true >> .env
```

##### Install the application virtual environment

These steps only need to be performed the first time you setup a fresh
virtualenv environment:

1. Ensure that you have the necessary C library dependencies available:

    - `libmemcached`
    - `postgresql`
    - `node` & `npm` for the front-end tools

1. Ensure that you have Python 3.8 or later installed

1. Install [pipenv](https://docs.pipenv.org/) either using a tool like
   [Homebrew](https://brew.sh) (`brew install pipenv`) or using `pip`:

    ```bash
    pip3 install pipenv
    ```

1. If you encounter errors installing psycopg, you may need to set LDFLAGS in your environment variables.

1. Let Pipenv create the virtual environment and install all of the packages,
   including our developer tools:

    ```bash
    pipenv install --dev
    ```

    n.b. if `libmemcached` is installed using Homebrew you will need to [set the CFLAGS long enough to build it](https://stackoverflow.com/questions/14803310/error-when-install-pylibmc-using-pip#comment94853072_19432949):

    ```bash
    CFLAGS=$(pkg-config --cflags libmemcached) LDFLAGS=$(pkg-config --libs libmemcached) pipenv install --dev
    ```

    Once it has been installed you will not need to repeat this process unless
    you upgrade the version of libmemcached or Python installed on your system.

1. Configure the Django settings module in the `.env` file which Pipenv will use
   to automatically populate the environment for every command it runs:

    ```bash
    echo DJANGO_SETTINGS_MODULE="concordia.settings_dev" >> .env
    ```

    You can use this to set any other values you want to customize, such as
    `POSTGRESQL_PW` or `POSTGRESQL_HOST`.

    n.b to allow a local server to connect to the dockerized db set `POSTGRESQL_PORT=54323` - the db containers external postgres port.

1. Make sure that [redis](https://redis.io/docs/getting-started/) is installed and
   running.

1. Configure Turnstile in your `.env` file. Unless specifically testing Turnstile,
   you'll probably want the following settings:

    ```bash
    echo TURNSTILE_SITEKEY=1x00000000000000000000BB >> .env
    echo TURNSTILE_SECRET=1x0000000000000000000000000000000AA >> .env
    ```

    Those two settings ensure all Turnstile tests pass. See [Turnstile Testing](https://developers.cloudflare.com/turnstile/troubleshooting/testing/) for other options.

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
pipenv install <package>
```

If the dependency you are installing is only of use for developers, mark it as
such using `--dev` so it will not be deployed to servers — for example:

```bash
pipenv install --dev django-debug-toolbar
```

Both the `Pipfile` and the `Pipfile.lock` files must be committed to the source
code repository any time you change them to ensure that all testing uses the
same package versions which you used during development.

#### Launching the environnment

In order to successfully launch the environment, the environment variables
`POSTGRESQL_PW` and `DJANGO_SETTINGS_MODULE` must be set. `POSTGRESQL_PW`
may be set to any value (which will become the database password for the
environment), but `DJANGO_SETTINGS_MODULE` should be set to
`concordia.settings_dev` to use the development settings file.

```bash
export POSTGRESQL_PW=password
export DJANGO_SETTINGS_MODULE=concordia.settings_dev
```

```bash
cd concordia
docker-compose up
```

Browse to [localhost](http://localhost)

#### Setting up a local development server

##### See section - [Ensuring your work follows the Library's coding standards](https://github.com/LibraryOfCongress/concordia/blob/master/docs/how-we-work.md#ensuring-your-work-follows-the-librarys-coding-standards) in How We Work

##### Start the support services

Instead of doing `docker-compose up` as above, instead start everything except the app:

```bash
docker-compose up -d db redis importer celerybeat
```

This will run the database in a container to ensure that it always matches the
expected version and configuration. If you want to reset the database, simply
delete the local container so it will be rebuilt the next time you run
`docker-compose up`: `docker-compose rm --stop db`.

##### Install front end

1. Install Node 20. If you're on MacOS, you can install it using brew:

    ```bash
    brew install node@12
    ```

1. Use NPM to install our development tools:

    ```bash
    npm install
    ```

1. In another terminal, start Gulp to watch for changes to the SCSS files and
   compile them to CSS:

    ```bash
    npx gulp
    ```

    If you only want to compile them a single time without live updates:

    ```bash
    npx gulp build
    ```

1. We also need to bundle the js files with vite. Similar to Gulp, you can use another terminal, start Vite to watch for issues when making changes to the bundled files:

    ```bash
    npx vite
    ```

    If you only want to bundle them a single time without live updates:

    ```bash
    npx vite build
    ```

1) You may need to manually create a logs directory.

    ```bash
    mkdir logs
    ```

1) Collect Django static files:

    ```bash
    pipenv run ./manage.py collectstatic
    ```

##### Start the application server

1. Apply any database migrations:

    ```bash
    pipenv run ./manage.py migrate
    ```

1. Start the development server:

    ```bash
    pipenv run ./manage.py runserver
    ```

#### Running the unit tests

Use the `settings_local_test` Django settings in your environment. Your `.env` file should look something like:

```bash
POSTGRESQL_PW=password
DJANGO_SETTINGS_MODULE=concordia.settings_local_test
```

Bring up the docker database and redis servers:

```bash
docker-compose up -d db redis
```

Then execute the tests:

```bash
pipenv run ./manage.py test
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

To generate a model graph, make sure that you have [GraphViz](https://graphviz.org/doc/info/command.html) installed (e.g.
`brew install graphviz` or `apt-get install graphviz`) and use the
[django-extensions `graph_models`](https://django-extensions.readthedocs.io/en/latest/graph_models.html) command:

```bash
dot -Tsvg <(pipenv run ./manage.py graph_models concordia importer) -o concordia.svg
```

## Other Front-End Tools

### Public-facing URLs

1. If you need a list of public-facing URLs for testing, there's a management
   command which may be helpful:

    ```bash
    pipenv run ./manage.py print_frontend_test_urls
    ```

### Accessibility testing using aXe

Automated tools such as [aXe](https://www.deque.com/axe/) are useful for
catching low-hanging fruit and regressions. You run aXe against a development
server by giving it one or more URLs:

```bash
npx axe-cli --show-errors http://localhost:8000/
pipenv run ./manage.py print_frontend_test_urls | xargs npx axe-cli --show-errors
```

### Static Image Compression

When you update any of the files under `concordia/static/img`, please use an
optimizer such as [ImageOptim](https://imageoptim.com) or [Caesium](https://caesium.app/)
to **losslessly** compress JPEG, PNG, SVG, etc. files.

```bash
brew cask install imageoptim
open -a ImageOptim concordia/static/img/
```
