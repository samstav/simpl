FROM debian:jessie

RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y python python-dev python-pip git libssl-dev
RUN pip install -U pip
RUN pip install supervisor
RUN pip install superlance

ADD . /app
ADD docker/config/checkmate-supervisor.conf /etc/supervisor.d/checkmate.conf
ADD docker/config/supervisord.conf /etc/supervisord.conf
ADD docker/config/run.sh /app/run.sh

RUN (mkdir /var/log/supervisor; \
     useradd -m -u 8888 checkmate; \
     git config --global url."https://".insteadOf git://; \
     pip install -r /app/requirements.txt; \
     pip install -e /app/ui; \
     pip install -e /app; \
     chmod +x /app/run.sh; \
     apt-get clean; \
     rm -rf /var/cache/apt/* && rm -rf /var/lib/apt/lists/*;)

EXPOSE 8080
ENTRYPOINT ["/app/run.sh"]
