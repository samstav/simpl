FROM python:2.7.9
RUN mkdir -p /app
ADD . /app
RUN pip install -r /app/requirements.txt
ADD https://github.com/xordataexchange/crypt/releases/download/v0.0.1/crypt-0.0.1-linux-amd64 /bin/crypt
RUN chmod +x /bin/crypt
RUN chmod +x /app/bootstrap.py

WORKDIR /app
CMD ["/bin/bash", "/app/run.sh"]
