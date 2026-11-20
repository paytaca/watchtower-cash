FROM nikolaik/python-nodejs:python3.8-nodejs16-slim

RUN apt-key adv --refresh-keys --keyserver keyserver.ubuntu.com
RUN rm -f /etc/apt/sources.list.d/yarn.list
RUN apt-get update -y || true
RUN apt-get -y install build-essential sudo postgresql libpq-dev postgresql-client curl \
    postgresql-client-common libncurses5-dev libjpeg-dev zlib1g-dev git wget redis-server && \
    wget -O /usr/local/bin/wait-for-it.sh https://raw.githubusercontent.com/vishnubob/wait-for-it/8ed92e8cab83cfed76ff012ed4a36cef74b28096/wait-for-it.sh && \
    chmod +x /usr/local/bin/wait-for-it.sh

# Application processes run as an unprivileged, fixed UID/GID so host volumes
# and runtime credentials can be granted the minimum required permissions.
RUN groupadd --gid 10001 app && \
    useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin app

# Next command needed for grpcio==1.34.0 build
RUN apt-get install -y \
    build-essential \
    python3-dev \
    libssl-dev \
    libffi-dev \
    libc-dev \
    pkg-config

RUN pip install --upgrade pip
COPY ./requirements.txt requirements.txt
# RUN pip install --no-cache-dir -r requirements.txt
RUN pip install -r requirements.txt

COPY ./main/js/package*.json /code/main/js/
RUN npm install --prefix /code/main/js --legacy-peer-deps

COPY ./anyhedge/js/package*.json /code/anyhedge/js/
RUN npm install --prefix /code/anyhedge/js --legacy-peer-deps

COPY ./rampp2p/js/package*.json /code/rampp2p/js/
RUN npm install --prefix /code/rampp2p/js --legacy-peer-deps

COPY ./cts/js/package*.json /code/cts/js/
RUN npm install --prefix /code/cts/js 

COPY ./stablehedge/js/package*.json /code/stablehedge/js/
RUN npm install --prefix /code/stablehedge/js

COPY ./multisig/js/package*.json /code/multisig/js/
RUN npm install --prefix /code/multisig/js
 
COPY . /code
WORKDIR /code

# Only runtime data directories are writable by the application user. Source
# files, dependencies, and entrypoint stay owned by root and read-only.
RUN mkdir -p /code/static /code/media /code/private-p2p-proofs /var/run/watchtower /images && \
    chown -R app:app /code/static /code/media /code/private-p2p-proofs /var/run/watchtower /images /home/app

ENV LC_ALL=C.UTF-8
ENV LANG=C.UTF-8
ENV PYTHONDONTWRITEBYTECODE=1

USER 10001:10001

ENTRYPOINT [ "sh", "entrypoint.sh" ]
