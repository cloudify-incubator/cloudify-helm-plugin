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

from .exceptions import CloudifyHelmSDKError
from helm_sdk.utils import (
    run_subprocess,
    prepare_set_parameter,
    prepare_parameter)

# Helm cli flags names
HELM_KUBECONFIG_FLAG = 'kubeconfig'
HELM_KUBE_API_SERVER_FLAG = 'kube-apiserver'
HELM_KUBE_TOKEN_FLAG = 'kube-token'
HELM_VALUES_FLAG = 'values'
APPEND_FLAG_STRING = '--{name}={value}'


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
            command,
            self.logger,
            cwd=None,
            additional_env=self.env,
            additional_args=None,
            return_output=return_output)

    def _helm_command(self, args):
        cmd = [self.binary_path]
        cmd.extend(args)
        return cmd

    @staticmethod
    def handle_auth_params(cmd,
                           kubeconfig=None,
                           token=None,
                           apiserver=None):
        if token and apiserver:
            cmd.append(APPEND_FLAG_STRING.format(name=HELM_KUBE_TOKEN_FLAG,
                                                 value=token))
            cmd.append(
                APPEND_FLAG_STRING.format(name=HELM_KUBE_API_SERVER_FLAG,
                                          value=apiserver))
        elif kubeconfig:
            cmd.append(APPEND_FLAG_STRING.format(name=HELM_KUBECONFIG_FLAG,
                                                 value=kubeconfig))
        else:
            raise CloudifyHelmSDKError(
                'Must provide kubernetes token and kube_api_server or '
                'kube_config file path.')

    def install(self,
                name,
                chart,
                flags=None,
                set_values=None,
                values_file=None,
                kubeconfig=None,
                token=None,
                apiserver=None,
                **_):
        """
        Execute helm install command.
        :param name: name for the created release.
        :param chart: chart name to install.
        :param flags: list of flags to add to the install command.
        :param set_values: list of variables and their values for --set.
        :param kubeconfig: path to kubeconfig file.
        :param values_file: values file path.
        :param token: bearer token used for authentication.
        :param apiserver: the address and the port for the Kubernetes API
        server.
        :return output of install command.
        """
        cmd = ['install', name, chart, '--wait', '--output=json']
        self.handle_auth_params(cmd, kubeconfig, token, apiserver)
        if values_file:
            cmd.append(APPEND_FLAG_STRING.format(name=HELM_VALUES_FLAG,
                                                 value=values_file))
        flags = flags or []
        cmd.extend([prepare_parameter(flag) for flag in flags])
        set_arguments = set_values or []
        cmd.extend([prepare_set_parameter(param) for param in set_arguments])
        output = self.execute(self._helm_command(cmd), True)
        return json.loads(output)

    def uninstall(self,
                  name,
                  flags=None,
                  kubeconfig=None,
                  token=None,
                  apiserver=None,
                  **_):
        cmd = ['uninstall', name]
        self.handle_auth_params(cmd, kubeconfig, token, apiserver)
        flags = flags or []
        cmd.extend([prepare_parameter(flag) for flag in flags])
        self.execute(self._helm_command(cmd))

    def repo_add(self,
                 name,
                 repo_url,
                 flags=None,
                 **_):
        cmd = ['repo', 'add', name, repo_url]
        flags = flags or []
        cmd.extend([prepare_parameter(flag) for flag in flags])
        self.execute(self._helm_command(cmd))

    def repo_remove(self,
                    name,
                    flags=None,
                    **_):
        cmd = ['repo', 'remove', name]
        flags = flags or []
        cmd.extend([prepare_parameter(flag) for flag in flags])
        self.execute(self._helm_command(cmd))

    def repo_list(self):
        cmd = ['repo', 'list', '--output=json']
        output = self.execute(self._helm_command(cmd), True)
        return json.loads(output)
