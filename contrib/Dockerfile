FROM dockerfile/python
ADD requirements.txt /app/
RUN /usr/bin/pip install -r /app/requirements.txt
ADD https://github.com/xordataexchange/crypt/releases/download/v0.0.1/crypt-0.0.1-linux-amd64 /bin/crypt
RUN chmod +x /bin/crypt
ADD . /app
RUN chmod +x /app/bootstrap.py

WORKDIR /app
CMD ["/bin/bash", "/app/run.sh"]
