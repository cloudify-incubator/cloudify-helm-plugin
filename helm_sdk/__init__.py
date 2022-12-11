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

import re
import json

from .exceptions import CloudifyHelmSDKError
from helm_sdk.utils import (
    run_subprocess,
    prepare_parameter,
    prepare_set_parameters,
    validate_no_collisions_between_params_and_flags)
from cloudify_common_sdk.utils import v1_gteq_v2

# Helm cli flags names
HELM_KUBECONFIG_FLAG = 'kubeconfig'
HELM_KUBE_TOKEN_FLAG = 'kube-token'
HELM_KUBE_CA_FILE_FLAG = 'kube-ca-file'
HELM_KUBE_API_SERVER_FLAG = 'kube-apiserver'
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

    def execute(self, command, additional_args=None, return_output=False):
        return run_subprocess(
            command,
            self.logger,
            cwd=None,
            additional_env=self.env,
            additional_args=additional_args,
            return_output=return_output)

    def _helm_command(self, args):
        cmd = [self.binary_path]
        cmd.extend(args)
        return cmd

    def handle_auth_params(self,
                           cmd,
                           kubeconfig=None,
                           token=None,
                           apiserver=None,
                           ca_file=None,
                           ca_file_key=None):
        """
            Validation of authentication params.
            Until helm will support --insecure, kubeconfig must be provided.
            :param kubeconfig: Kubeconfig file path
            :param: token: bearer token used for authentication.
            :param: apiserver: the address and the port for the Kubernetes API
            server.
        """

        if not kubeconfig and not (token and apiserver and ca_file):
            raise CloudifyHelmSDKError(
                'Must provide kubeconfig file path or token, apiserver and'
                ' ca_file in order to authenticate with the cluster.')

        if kubeconfig:
            cmd.append(APPEND_FLAG_STRING.format(name=HELM_KUBECONFIG_FLAG,
                                                 value=kubeconfig))

        if token:
            cmd.append(APPEND_FLAG_STRING.format(name=HELM_KUBE_TOKEN_FLAG,
                                                 value=token))

        if apiserver:
            cmd.append(
                APPEND_FLAG_STRING.format(name=HELM_KUBE_API_SERVER_FLAG,
                                          value=apiserver))
        if ca_file:
            self.check_flag_kube_ca_cert_is_supported()
            cmd.append(
                APPEND_FLAG_STRING.format(
                    name=ca_file_key or HELM_KUBE_CA_FILE_FLAG, value=ca_file))

    def install(self,
                name,
                chart,
                flags=None,
                set_values=None,
                values_file=None,
                kubeconfig=None,
                token=None,
                apiserver=None,
                ca_file=None,
                additional_env=None,
                additional_args=None,
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
        self.handle_auth_params(
            cmd, kubeconfig, token, apiserver, ca_file)
        if values_file:
            cmd.append(APPEND_FLAG_STRING.format(name=HELM_VALUES_FLAG,
                                                 value=values_file))
        flags = flags or []
        validate_no_collisions_between_params_and_flags(flags)
        cmd.extend([prepare_parameter(flag) for flag in flags])
        set_arguments = set_values or []
        cmd.extend(prepare_set_parameters(set_arguments))
        if additional_env:
            self.env.update(additional_env)
        output = self.execute(
            self._helm_command(cmd),
            additional_args=additional_args,
            return_output=True)
        return self.load_json(output)

    def uninstall(self,
                  name,
                  flags=None,
                  kubeconfig=None,
                  token=None,
                  apiserver=None,
                  ca_file=None,
                  additional_env=None,
                  additional_args=None,
                  **_):

        if self.check_flag_wait_is_supported():
            cmd = ['uninstall', name, '--wait']
        else:
            cmd = ['uninstall', name]
        self.handle_auth_params(
            cmd, kubeconfig,
            token,
            apiserver,
            ca_file)
        flags = flags or []
        validate_no_collisions_between_params_and_flags(flags)
        cmd.extend([prepare_parameter(flag) for flag in flags])
        if additional_env:
            self.env.update(additional_env)
        self.execute(self._helm_command(cmd), additional_args=additional_args)

    def repo_add(self,
                 name,
                 repo_url,
                 flags=None,
                 additional_args=None,
                 **_):
        cmd = ['repo', 'add', name, repo_url]
        flags = flags or []
        cmd.extend([prepare_parameter(flag) for flag in flags])
        self.execute(self._helm_command(cmd), additional_args=additional_args)

    def repo_remove(self,
                    name,
                    flags=None,
                    additional_args=None,
                    **_):
        cmd = ['repo', 'remove', name]
        flags = flags or []
        cmd.extend([prepare_parameter(flag) for flag in flags])
        self.execute(self._helm_command(cmd), additional_args=additional_args)

    def show_chart(self, chart_name, repo_url):
        cmd = ['show', 'chart', chart_name, '--repo', repo_url]
        output = self.execute(self._helm_command(cmd), return_output=True)
        return self.load_json(output)

    def repo_list(self):
        cmd = ['repo', 'list', '--output=json']
        output = self.execute(self._helm_command(cmd), return_output=True)
        return self.load_json(output)

    def repo_update(self, flags, additional_args=None, **_):
        cmd = ['repo', 'update']
        flags = flags or []
        cmd.extend([prepare_parameter(flag) for flag in flags])
        self.execute(self._helm_command(cmd), additional_args=additional_args)

    def upgrade(self,
                release_name,
                chart=None,
                flags=None,
                set_values=None,
                values_file=None,
                kubeconfig=None,
                token=None,
                apiserver=None,
                ca_file=None,
                additional_env=None,
                additional_args=None,
                **_):
        """
        Execute helm upgrade command.
        :param release_name: name of the release to upgrade.
        :param chart: The chart to upgrade the release with.
        The chart argument can be either: a chart reference('example/mariadb'),
        a packaged chart, or a fully qualified URL.
        :param flags: list of flags to add to the upgrade command.
        :param set_values: list of variables and their values for --set.
        :param kubeconfig: path to kubeconfig file.
        :param values_file: values file path.
        :param token: bearer token used for authentication.
        :param apiserver: the address and the port for the Kubernetes API
        server.
        :return output of helm upgrade command.
        """
        if not chart:
            raise CloudifyHelmSDKError(
                'Must provide chart for upgrade release.')
        cmd = ['upgrade', release_name, chart, '--atomic', '-o=json']
        self.handle_auth_params(cmd, kubeconfig, token, apiserver, ca_file)
        if values_file:
            cmd.append(APPEND_FLAG_STRING.format(name=HELM_VALUES_FLAG,
                                                 value=values_file))
        flags = flags or []
        validate_no_collisions_between_params_and_flags(flags)
        cmd.extend([prepare_parameter(flag) for flag in flags])
        set_arguments = set_values or []
        cmd.extend(prepare_set_parameters(set_arguments))
        if additional_env:
            self.env.update(additional_env)
        output = self.execute(
            self._helm_command(cmd),
            additional_args=additional_args,
            return_output=True)
        return self.load_json(output)

    def get_helm_version(self):
        cmd = ['version', '--short']
        output = self.execute(self._helm_command(cmd))
        version = re.search(r'([\d.]+)', output)
        if version:
            return version.group(1)

    def check_flag_wait_is_supported(self):
        return v1_gteq_v2(self.get_helm_version(), '3.9.0')

    def check_flag_kube_ca_cert_is_supported(self):
        if not v1_gteq_v2(self.get_helm_version(), '3.9.0'):
            raise CloudifyHelmSDKError(
                'Unable to authenticate with CA Cert, '
                'the {} flag is not supported with helm version {}. '
                'Please upgrade to 3.9.0 or later.'.format(
                    HELM_KUBE_CA_FILE_FLAG, self.get_helm_version()))

    def list(self,
             release_name,
             kubeconfig=None,
             token=None,
             apiserver=None,
             additional_env=None,
             ca_file=None):

        cmd = ['list', '--filter', r"^{0}$".format(release_name), '-o json']
        self.handle_auth_params(cmd, kubeconfig, token, apiserver, ca_file)
        if additional_env:
            self.env.update(additional_env)
        output = self.execute(self._helm_command(cmd), return_output=True)
        return json.loads(output)

    def status(self,
               release_name,
               flags=None,
               set_values=None,
               kubeconfig=None,
               token=None,
               apiserver=None,
               ca_file=None,
               additional_env=None,
               additional_args=None,
               **_):
        """
        Execute helm status command.
        :param release_name: name of the release to upgrade.
        :param flags: list of flags to add to the upgrade command.
        :param set_values: list of variables and their values for --set.
        :param kubeconfig: path to kubeconfig file.
        :param token: bearer token used for authentication.
        :param apiserver: the address and the port for the Kubernetes API
        server.
        :return status of helm upgrade command.
        """
        cmd = ['status', release_name, '-o=json']
        self.handle_auth_params(cmd, kubeconfig, token, apiserver, ca_file)
        flags = flags or []
        validate_no_collisions_between_params_and_flags(flags)
        cmd.extend([prepare_parameter(flag) for flag in flags])
        set_arguments = set_values or []
        cmd.extend(prepare_set_parameters(set_arguments))
        if additional_env:
            self.env.update(additional_env)
        output = self.execute(
            self._helm_command(cmd),
            additional_args=additional_args,
            return_output=True)
        return json.loads(output)

    def load_json(self, output):
        if output:
            try:
                output = json.loads(output)
            except json.decoder.JSONDecodeError:
                self.logger.error('Failed to load output as JSON.')
        return output
