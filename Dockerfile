FROM google/python

ADD . /app
RUN apt-get update && apt-get install -y ca-certificates
RUN virtualenv /env
RUN (git config --global url."https://".insteadOf git://; \
  /env/bin/pip install -r /app/requirements.txt; \
  /env/bin/pip install -e /app/ui; \
  /env/bin/pip install -e /app; \
  apt-get clean; \
  rm -rf /var/cache/apt/* && rm -rf /var/lib/apt/lists/*;)

EXPOSE 8080
ENTRYPOINT ["/env/bin/python", "/app/checkmate/server.py"]
