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

import logging

LOG = logging.getLogger(__name__)


class ExceptionHandler(object):
    def __init__(self, d_wf, task_id, context, driver):
        self.d_wf = d_wf
        self.task_id = task_id
        self.context = context
        self.driver = driver

    def handle(self):
        LOG.debug("%s.handle called, but was not implemented",
                  self.__class__.__name__)
