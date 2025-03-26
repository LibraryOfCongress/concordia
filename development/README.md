# Concordia Development Containers

The files in this directory, `compose.yml` and `Containerfile`, have been created to better facilitate developing Concordia in a containerized environment. The files are compatible with both Docker and Podman, using docker-compose or podman-compose.

Though newer versions of docker-compose and podman-compose support combining compose files and compose file overriding, the versions of these tools available on some current distributions (such as Red Hat Enterprise Linux 9) do not, so a singular compose file (`compose.yml`) with all the necessary settings is provided here.

## Purpose

The intention of these files is to provide a usable development environment purely in containers.

The default configuration (`../docker-compose.yml`) creates a container environment that's not suitable for development. Primarily, it creates an container for Elasticsearch, which is often used except in production, and the `app` container is not configured well for development. It runs as root, which causes file permission issues, and runs the daphne asgi server, which can't be restarted without restarting the entire container (manually killing and starting daphne does not work, either, because that causes the container to shutdown).

In addition, the default container file for the `app` container (`../Dockerfile`) runs `../entrypoint.sh`, which does several things that are undesirable in a development environment that involves restarting containers regularly. It automatically generates and applies migrations, runs collectstatic and launches daphne. The development Containerfile instead simply launches a bash shell.

## Configuration

In order to use `compose.yml` with your compose CLI tool of choice, you'll need to pass in the path, either through an environment variable or a command-line switch.

```bash
podman-compose -f development/compose.yml
```

```dotenv
COMPOSE_FILE=development/compose.yml
```

Your CLI tool should be executed in the concordia directory (`..`).

### .env caveat

Note that some versions of the tools (notably, podman-compose<=1.0.6) do not use .env files. If you wish to use environment variables, you'll need to inject those variables manually, such as by using a script that sources your .env file before executing podman-compose.

## Development

Configuring for your environment when using containers follows the process in the [For Developers](../docs/for-developers.md) page, except that most of the work is done for you by `compose.yml` and `Containerfile`. Notably, you do not need to install any dependencies (except git and your compose CLI) on your host. You will still need to configure your .env file, but otherwise simply running `podman-compose up -d` or `docker-compose up -d`, with the proper COMPOSE_FILE configuration (and other additions to .env, see below), will create an app container with everything you need for development.

### Additions to .env

There are a few additions to your .env file required to properly use the provided `compose.yml` and `Containerfile`:

```dotenv
COMPOSE_FILE=development/compose.yml
HOME_DIR=/home/<username>/
AWS_SHARED_CREDENTIALS_FILE=/home/<username>/.aws/credentials
CONTAINER_UID=<uid>
CONTAINER_GID=<guid>
CONTAINER_USERNAME=<username>
```

These values should be for the user account that you'll be doing development with, the same one that owns your local repository. This information is used to mount various necessary directories in the container, as well as configure the user account inside the container (to avoid running as root).

The last three settings can automatically be added to your .env file with the following scripts (executed in the directory with the .env):

```bash
#!/bin/bash

ENV_FILE=".env"
BACKUP_FILE=".env.bak"

# Create the .env file if it doesn't exist
touch "$ENV_FILE"

# Backup the original .env once
cp "$ENV_FILE" "$BACKUP_FILE"

# Set the values
NEW_UID=$(id -u)
NEW_GID=$(id -g)
NEW_USERNAME=$(whoami)

# Function to add or update a key in the .env file
update_env_var() {
    local key="$1"
    local value="$2"
    if grep -qE "^${key}=" "$ENV_FILE"; then
        sed -i "s/^${key}=.*/${key}=${value}/" "$ENV_FILE"
    else
        echo "${key}=${value}" >> "$ENV_FILE"
    fi
}

# Update the values
update_env_var "CONTAINER_UID" "$NEW_UID"
update_env_var "CONTAINER_GID" "$NEW_GID"
update_env_var "CONTAINER_USERNAME" "$NEW_USERNAME"

echo "Backup saved as $BACKUP_FILE"
echo ".env updated with CONTAINER_UID=$NEW_UID, CONTAINER_GID=$NEW_GID, CONTAINER_USERNAME=$NEW_USERNAME"
```

### Attaching to the app container

Once you've launched your containers, you can attach to a shell in the app container to perform development. Your compose CLI tool should provide a method for doing this.

```bash
sudo docker-compose exec -it app bash
```

Note that older versions of podman-compose do not properly pass switches to the underlying command, meaning the above won't work with those versions of podmon-compose. You can instead run it without the switches:

```bash
sudo podman-compose exec app bash
```

However, this has the disadvantage of not creating an interactive shell shell, which can cause issues with bash functionality. If you have a version of podman-compose with this limitation, the workaround is to use podman directly instead:

```bash
sudo podman exec -it concordia_app bash
```

You have to use the full container name because compose.yml is not referenced when using podman directly.

### Configuring for development

You will need to manually collect the static files before running the development server. This only needs to be done once after building the app container (and when changing static files in the future).

```bash
npx gulp build
python manage.py collectstatic
```

### Launch the development server

Launching the development server is identical to launching it outside a container. The app container is configured to map port 8000 in the container to port 80 on the host:

```bash
python manage.py runserver 0.0.0.0:8000
```

### Committing changes

Git and the Concordia precommit hooks are included in the app container. You can simply use git commands as normal inside /workspace in the container.
