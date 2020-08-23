########
# Copyright (c) 2019 Cloudify Platform Ltd. All rights reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
#    * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    * See the License for the specific language governing permissions and
#    * limitations under the License.

import json

from helm_sdk.utils import (run_subprocess, prepare_set_parameter,
                            prepare_parameter)


class Helm(object):

    def __init__(self,
                 logger,
                 binary_path,
                 environment_variables
                 ):
        self.binary_path = binary_path
        self.logger = logger
        if not isinstance(environment_variables, dict):
            raise Exception(
                "Unexpected type for environment variables (should be a "
                "dict): {0}".format(type(
                    environment_variables)))

        self.env = environment_variables

    def execute(self, command, return_output=False):
        return run_subprocess(
            command, self.logger,
            cwd=None,
            additional_env=self.env,
            additional_args=None,
            return_output=return_output)

    def _helm_command(self, args):
        cmd = [self.binary_path]
        cmd.extend(args)
        return cmd

    def install(self, release_name, chart, flags, set_arguments=None):
        cmd = ['install', release_name, chart, '--wait', '--output=json']
        cmd.extend(map(prepare_parameter, flags))
        set_arguments = set_arguments or []
        cmd.extend(map(prepare_set_parameter, set_arguments))
        output = self.execute(self._helm_command(cmd), True)
        return json.loads(output)

    def uninstall(self, release_name, flags=None):
        cmd = ['uninstall', release_name]
        flags = flags or []
        cmd.extend(map(prepare_parameter, flags))
        self.execute(self._helm_command(cmd))

    def repo_add(self, repo_name, repo_url, flags=None):
        cmd = ['repo', 'add', repo_name, repo_url]
        flags = flags or []
        cmd.extend(map(prepare_parameter, flags))
        self.execute(self._helm_command(cmd))

    def repo_remove(self, repo_name, flags=None):
        cmd = ['repo', 'remove', repo_name]
        flags = flags or []
        cmd.extend(map(prepare_parameter, flags))
        self.execute(self._helm_command(cmd))
