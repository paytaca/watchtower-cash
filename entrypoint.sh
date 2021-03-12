#!/bin/sh
python /code/manage.py migrate sessions
python /code/manage.py migrate
python /code/manage.py collectstatic --noinput
python /code/manage.py cleanup
exec "$@"