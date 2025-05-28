#!/bin/sh

wait-for-it.sh $POSTGRES_HOST:$POSTGRES_PORT
python /code/manage.py migrate contenttypes
python /code/manage.py migrate sessions
python /code/manage.py migrate
python /code/manage.py collectstatic --noinput

python /code/manage.py subscribe_stablehedge_auth_key

exec "$@"
