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

from checkmate import utils

LOG = logging.getLogger(__name__)


class Transforms(object):
    """Class to hold transform functions.

    We put them in a separate class to:
    - access them from tests
    - possible, in the future, use them as a library instead of passing the
      actual code in to Spiff for better security
    TODO(zns): Should separate them out into their own module (not class)
    """
    @staticmethod  # self will actually be a SpiffWorkflow.TaskSpec
    def collect_options(self, my_task):  # pylint: disable=W0211
        """Collect and write run-time options."""
        try:
            import copy  # pylint: disable=W0404,W0621
            # pylint: disable=W0621
            from checkmate.providers.opscode.solo import (ChefMap,
                                                          SoloProviderNotReady)
            # pylint: disable=W0621
            from checkmate.deployments import resource_postback as postback
            maps = self.get_property('chef_maps', [])
            data = my_task.attributes

            # Evaluate all maps and exit if any of them are not ready

            queue = []
            for mapping in maps:
                try:
                    result = ChefMap.evaluate_mapping_source(mapping, data)
                    if ChefMap.is_writable_val(result):
                        queue.append((mapping, result))
                except SoloProviderNotReady:
                    return False  # false means not done/not ready

            # All maps are resolved, so combine them with the ones resolved at
            # planning-time

            results = self.get_property('chef_options', {})
            for mapping, result in queue:
                ChefMap.apply_mapping(mapping, result, results)

            # Write to the task attributes and postback the desired output

            output_template = self.get_property('chef_output')
            if output_template:
                output_template = copy.copy(output_template)
            else:
                output_template = {}
            if results:

                # outputs do not go into chef_options
                outputs = results.pop('outputs', {})
                # Use output_template as a template for outputs
                if output_template:
                    outputs = utils.merge_dictionary(
                        copy.copy(output_template), outputs)

                # Write chef_options for databag and role tasks
                if results:
                    if 'chef_options' not in my_task.attributes:
                        my_task.attributes['chef_options'] = {}
                    utils.merge_dictionary(my_task.attributes['chef_options'],
                                           results, True)

                # write outputs (into attributes and output_template)
                if outputs:
                    # Write results into attributes
                    utils.merge_dictionary(my_task.attributes, outputs)
                    # Be compatible and write without 'instance'
                    compat = {}
                    for key, value in outputs.iteritems():
                        if isinstance(value, dict) and 'instance' in value:
                            compat[key] = value['instance']
                    if compat:
                        utils.merge_dictionary(my_task.attributes, compat)

                    # Write outputs into output template
                    utils.merge_dictionary(output_template, outputs)
            else:
                if output_template:
                    utils.merge_dictionary(my_task.attributes, output_template)

            # postback output into deployment resource

            if output_template:
                dep = self.get_property('deployment')
                if dep:
                    LOG.debug("Writing task outputs: %s", output_template)
                    postback.delay(dep, output_template)
                else:
                    LOG.warn("Deployment id not in task properties, "
                             "cannot update deployment from chef-solo")

            return True
        except StandardError as exc:
            import sys
            import traceback
            LOG.error("Error in transform: %s", exc)
            tback = sys.exc_info()[2]
            tb_info = traceback.extract_tb(tback)
            mod, line = tb_info[-1][-2:]
            raise Exception("%s %s in %s executing: %s" % (type(exc).__name__,
                                                           exc, mod, line))
