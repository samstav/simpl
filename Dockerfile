FROM debian:wheezy

# Base packages and Python install
ADD docker/config/sources.list /etc/apt/
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y procps autoconf build-essential python python-dev python-pip git libssl-dev
RUN pip install -U pip
RUN pip install supervisor
RUN pip install superlance

# Ruby 2.1 install, purging things to keep our image small
RUN apt-get install -y curl bison ruby \
  && rm -rf /var/lib/apt/lists/* \
  && mkdir -p /usr/src/ruby \
  && curl -SL "http://cache.ruby-lang.org/pub/ruby/2.1/ruby-2.1.3.tar.bz2" \
    | tar -xjC /usr/src/ruby --strip-components=1 \
  && cd /usr/src/ruby \
  && autoconf \
  && ./configure --disable-install-doc \
  && make -j"$(nproc)" \
  && apt-get purge -y --auto-remove bison ruby \
  && make install \
  && rm -r /usr/src/ruby

ENV GEM_HOME /usr/local/bundle
RUN echo 'gem: --no-rdoc --no-ri' >> "$HOME/.gemrc"
ENV PATH $GEM_HOME/bin:$PATH
RUN gem install bundler \
  && bundle config --global path "$GEM_HOME" \
  && bundle config --global bin "$GEM_HOME/bin"

# Put Checkmate in there
ADD . /app
ADD docker/config/checkmate-supervisor.conf /etc/supervisor.d/checkmate.conf
ADD docker/config/supervisord.conf /etc/supervisord.conf
ADD docker/config/run.sh /app/run.sh

# Setup Checkmate
RUN (mkdir /var/log/supervisor; \
     useradd -m -u 8888 checkmate; \
     mkdir -p /var/local/checkmate; \
     chown checkmate /var/local/checkmate; \
     cd /app && bundle install; \
     git config --global url."https://".insteadOf git://; \
     pip install -r /app/requirements.txt; \
     pip install -e /app/ui; \
     pip install -e /app; \
     chmod +x /app/run.sh; \
     apt-get clean; \
     rm -rf /var/cache/apt/* && rm -rf /var/lib/apt/lists/*;)

EXPOSE 8080

ENV BUNDLE_APP_CONFIG $GEM_HOME
ENTRYPOINT ["/app/run.sh"]
