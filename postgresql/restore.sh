
#!/bin/bash

# For AMI: sudo yum install https://download.postgresql.org/pub/repos/yum/9.6/redhat/rhel-6-x86_64/pgdg-ami201503-96-9.6-2.noarch.rpm
#          sudo yum install postgresql96

# Before running the restore, you'll have to stop the ECS task to close any open connections.
# Then, run the following to drop the database.
# psql -U concordia -h $POSTGRES_HOST
# \c postgres
# drop database concordia

export POSTGRES_HOST=cpl1jbd411xj1t.cbvco2dnalbp.us-east-1.rds.amazonaws.com
export DUMP_FILE=concordia.dmp

pg_restore --create --clean -U concordia -h $POSTGRES_HOST -Fc -n --dbname=postgres --no-owner --no-acl -f $DUMP_FILE

# After this, change the Sites in django admin to match the host name
