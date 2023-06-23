FROM nikolaik/python-nodejs:python3.7-nodejs15-slim

RUN apt-key adv --refresh-keys --keyserver keyserver.ubuntu.com
RUN apt-get update -y
RUN apt-get -y install build-essential sudo postgresql libpq-dev postgresql-client curl \
    postgresql-client-common libncurses5-dev libjpeg-dev zlib1g-dev git wget redis-server && \
    wget -O /usr/local/bin/wait-for-it.sh https://raw.githubusercontent.com/vishnubob/wait-for-it/8ed92e8cab83cfed76ff012ed4a36cef74b28096/wait-for-it.sh && \
    chmod +x /usr/local/bin/wait-for-it.sh

RUN pip install --upgrade pip
COPY ./requirements.txt requirements.txt
# RUN pip install --no-cache-dir -r requirements.txt
RUN pip install -r requirements.txt

# For running javascript
RUN sudo apt install -y curl
RUN sudo apt-get update --allow-releaseinfo-change
RUN curl -fsSL https://deb.nodesource.com/setup_16.x | sudo -E bash -
RUN sudo apt install nodejs -y --allow-change-held-packages
COPY ./anyhedge/js/package*.json /code/anyhedge/js/
RUN npm install --prefix /code/anyhedge/js --legacy-peer-deps

COPY . /code
WORKDIR /code

ENV LC_ALL=C.UTF-8
ENV LANG=C.UTF-8

ENTRYPOINT [ "sh", "entrypoint.sh" ]
