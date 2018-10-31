
#!/bin/bash

# Before running the restore, you'll have to stop the ECS task to close any open connections.
# Then, run the following to drop the database.
# psql -U concordia -h $POSTGRES_HOST
# \c postgres
# drop database concordia

pg_restore --create --clean -U concordia -h $POSTGRES_HOST -Fc -n --dbname=postgres --no-owner --no-acl $DUMP_FILE