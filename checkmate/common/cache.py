# Copyright (c) 2011-2013 Rackspace Hosting
# All Rights Reserved.
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
#
# pylint: disable=W0703

"""Return a real redis cache or fakeredis, in-memory cache."""

import logging

import fakeredis
import redis

from checkmate.common import config
from checkmate import utils

LOG = logging.getLogger(__name__)
CONFIG = config.current()

try:
    PING = redis.from_url(CONFIG.cache_connection_string, socket_timeout=0.2)
    # ping test
    PING.ping()
    CACHE = redis.from_url(CONFIG.cache_connection_string)
    # true test
    CACHE.set('test', 'value', ex=1)
    LOG.info("Found redis instance for CACHE.")
except Exception as exc:
    LOG.warn("No redis instance found at [%s], ERROR: %s | "
             "Using fakeredis. Limitations apply.",
             utils.hide_url_password(CONFIG.cache_connection_string), exc)
    CACHE = fakeredis.FakeStrictRedis()
