FROM debian:wheezy

# Base packages and Python install
ADD docker/config/sources.list /etc/apt/
# add wheezy-backport to sources for git 1.9.1
RUN echo "deb http://http.debian.net/debian wheezy-backports main" \
    | tee -a /etc/apt/sources.list
RUN apt-get update && DEBIAN_FRONTEND=noninteractive \
    apt-get install -y \
    procps \
    autoconf \
    build-essential \
    python \
    python-dev \
    libssl-dev \
    wget \
    libreadline-dev \
    locales
RUN apt-get -t wheezy-backports install -y git

RUN echo "en_US.UTF-8 UTF-8" >> /etc/locale.gen && locale-gen
ENV LANG en_US.UTF-8

# Install pip from get-pip in order to avoid issues with the Ubuntu pip
# package and issues with using easy_install to install pip. This is
# ridiculous, but the only way I could get everything to work...
RUN wget -O /tmp/get-pip.py https://raw.githubusercontent.com/pypa/pip/1.5.6/contrib/get-pip.py
RUN python /tmp/get-pip.py

RUN pip install -U distribute
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

ADD Gemfile /opt/rubysetup/Gemfile
ADD Gemfile.lock /opt/rubysetup/Gemfile.lock
ENV GEM_HOME /usr/local/bundle
RUN echo 'gem: --no-rdoc --no-ri' >> "$HOME/.gemrc"
ENV PATH $GEM_HOME/bin:$PATH
RUN gem install bundler \
  && bundle config --global path "$GEM_HOME" \
  && bundle config --global bin "$GEM_HOME/bin"
RUN cd /opt/rubysetup && bundle install

# Install dependencies
ADD ./requirements.txt /app/requirements.txt
RUN git config --global url."https://".insteadOf git://
RUN pip install -r /app/requirements.txt

# Put Checkmate in there
ADD . /app
ADD docker/config/checkmate-supervisor.conf /etc/supervisord.conf
ADD docker/config/run.sh /app/run.sh

# Put crypt in there
ADD https://github.com/xordataexchange/crypt/releases/download/v0.0.1/crypt-0.0.1-linux-amd64 /usr/local/bin/crypt
RUN chmod +x /usr/local/bin/crypt

# Setup Checkmate
RUN (mkdir /var/log/supervisor &&\
     useradd -m -u 8888 checkmate &&\
     mkdir /home/checkmate/.ssh &&\
     mkdir -p /var/local/checkmate &&\
     chown checkmate /var/local/checkmate &&\
     pip install -e /app/ui &&\
     pip install -e /app &&\
     chmod +x /app/run.sh;)

# Cleanup
RUN (apt-get clean; \
     rm -rf /var/cache/apt/* && rm -rf /var/lib/apt/lists/*;)

EXPOSE 8080

ENV BUNDLE_APP_CONFIG $GEM_HOME
ENTRYPOINT ["/app/run.sh"]
