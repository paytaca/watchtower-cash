FROM nikolaik/python-nodejs:python3.8-nodejs16-slim

# Root is used only while building the image.
USER root

RUN apt-key adv --refresh-keys --keyserver keyserver.ubuntu.com
RUN rm -f /etc/apt/sources.list.d/yarn.list
RUN apt-get update -y || true
RUN apt-get -y install build-essential postgresql libpq-dev postgresql-client curl \
    postgresql-client-common libncurses5-dev libjpeg-dev zlib1g-dev git wget redis-server && \
    wget -O /usr/local/bin/wait-for-it.sh https://raw.githubusercontent.com/vishnubob/wait-for-it/8ed92e8cab83cfed76ff012ed4a36cef74b28096/wait-for-it.sh && \
    chmod +x /usr/local/bin/wait-for-it.sh

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

ENV LC_ALL=C.UTF-8
ENV LANG=C.UTF-8
ENV HOME=/home/watchtower
ENV PYTHONDONTWRITEBYTECODE=1

# Keep source/dependencies root-owned; grant writes only to runtime data paths.
RUN groupadd --gid 10001 watchtower && \
    useradd --uid 10001 --gid 10001 --home-dir /home/watchtower \
      --no-create-home --shell /usr/sbin/nologin watchtower && \
    find /code -perm /022 -exec chmod go-w {} + && \
    install -d -o 10001 -g 10001 -m 0755 \
      /home/watchtower /run/watchtower /var/lib/watchtower \
      /code/static /code/media /code/private-p2p-proofs /images

USER 10001:10001

ENTRYPOINT [ "sh", "entrypoint.sh" ]
