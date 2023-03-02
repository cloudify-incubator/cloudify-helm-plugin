########
# Copyright (c) 2019 - 2023 Cloudify Platform Ltd. All rights reserved
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

from cloudify_kubernetes_sdk.state import Resource
from cloudify_kubernetes_sdk import client_resolver
from cloudify_kubernetes_sdk.connection import decorators


class Kubernetes(object):

    def __init__(self,
                 logger,
                 host,
                 token,
                 kubeconfig):
        self.logger = logger
        self._host = host
        self._token = token
        self._kubeconfig = kubeconfig
        self._kubeconfig_obj = None

    @property
    def host(self):
        return self._host

    @property
    def token(self):
        return self._token

    @property
    def kubeconfig(self):
        if not self._kubeconfig_obj:
            self._kubeconfig_obj = decorators.setup_configuration(
                kubeconfig=self._kubeconfig,
                api_key=self.token,
                host=self.host)
        return self._kubeconfig_obj

    def status(self, resource, namespace):
        # TODO: This is more like "the entire object", not just status.
        api = client_resolver.get_kubernetes_api(resource['apiVersion'])
        fn_name = client_resolver.get_read_function_name(resource['kind'])
        callable = client_resolver.get_callable(fn_name, api(self.kubeconfig))
        try:
            resource_api_obj = callable(
                resource['metadata']['name'], namespace)
        except Exception as e:
            self.logger.error(
                'There was an error fetching {} in namespace {}: {}'.format(
                    resource['metadata']['name'], namespace, str(e)))
            resource_api_obj = {}
        state = Resource(resource_api_obj).state
        return state


    def check_status(self, resource, namespace):
        api = client_resolver.get_kubernetes_api(
        resource['apiVersion'])

        fn_name = client_resolver.get_read_function_name(resource['kind'])
        callable = client_resolver.get_callable(fn_name, api(self.kubeconfig))

        try:
            resource_api_obj = callable(resource['metadata']['name'], namespace)
        except Exception as e:
            self.logger.error(
                'There was an error fetching {} in namespace {}: {}'.format(
                    resource['metadata']['name'], namespace, str(e)))
            return

        state = Resource(resource_api_obj).check_status  # This is really just looking at status.
        return state


    def multiple_resource_status(self, helm_status):
        errors = []
        status = {}
        namespace = helm_status.get('namespace')
        for manifest, resource in helm_status['manifest'].items():
            self.logger.info('Looking for {}'.format(manifest))
            manifest = manifest.replace(
                '/', '_').replace('.yaml', '').replace('-', '__')
            error = self.validate_resource_metadata(resource, namespace)
            if error:
                errors.append(error)
            state = self.status(resource, namespace)
            status.update(
                {
                    manifest: state
                }
            )
        self.report_errors(errors)
        return status


    def multiple_resource_check_status(self, helm_status):
        errors = []
        status = {}
        namespace = helm_status.get('namespace')

        for manifest, resource in helm_status['manifest'].items():
            self.logger.info('Looking for {}'.format(manifest))
            manifest = manifest.replace(
                '/', '_').replace('.yaml', '').replace('-', '__')
            error = self.validate_resource_metadata(resource, namespace)
            if error:
                errors.append(error)
            state = self.check_status(resource, namespace)
            if not state:
                errors.append(
                    'Unable to retrieve state for {} in namespace {}.'
                        .format(resource, namespace))
            status.update(
                {
                    manifest: state
                }
            )
        self.report_errors(errors)
        return status ,errors


    def validate_resource_metadata(self, resource, namespace):
        api_version = resource.get('apiVersion')
        kind = resource.get('kind')
        namespace = resource['metadata'].get('namespace', namespace)
        name = resource['metadata'].get('name')
        if not all([api_version, kind, namespace, name]):
            error_message = 'Unable to check status for resource because'
            missing_pieces = []
            if not api_version:
                missing_pieces.append('apiVersion')
            if not kind:
                missing_pieces.append('kind')
            if not namespace:
                missing_pieces.append('metadata.namespace')
            if not name:
                missing_pieces.append('metadata.name')
            if len(missing_pieces) > 1:
                error_message += ', '.join(missing_pieces)
                error_message += ' are'
            else:
                error_message += ' ' + missing_pieces[0] + ' is'
            error_message += ' missing in the resource definition: {}.'.format(
                resource)
            self.logger.error(error_message)
            return error_message

    def report_errors(self, errors):
        if not errors:
            return
        self.logger.error(
            'The following errors were found in helm manifests: ')
        for error in errors:
            self.logger.error(error)
