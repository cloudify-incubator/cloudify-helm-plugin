# Copyright (c) 2017-2019 Cloudify Platform Ltd. All rights reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import json
from oauth2client.service_account import ServiceAccountCredentials

from helm_sdk._compat import text_type
from .exceptions import HelmKuberentesAuthenticationError


# Those classes are responsible for generate Bearer token for
# authentication(id_token)
# in each of the platforms supported(currently only gcp).

class KubernetesApiAuthentication(object):

    def __init__(self, logger, authentication_data):
        self.logger = logger
        self.authentication_data = authentication_data

    def _get_token(self):
        return None

    def get_token(self):
        token = self._get_token()

        if not token:
            raise HelmKuberentesAuthenticationError(
                'Cannot generate token use {0} for data: {1} '.format(
                    self.__class__.__name__,
                    self.authentication_data,
                )
            )

        return token


class GCPServiceAccountAuthentication(KubernetesApiAuthentication):
    PROPERTY_GCP_SERVICE_ACCOUNT = 'gcp_service_account'

    SCOPES = ['https://www.googleapis.com/auth/cloud-platform']

    def _get_token(self):
        service_account_file_content = self.authentication_data.get(
            self.PROPERTY_GCP_SERVICE_ACCOUNT
        )
        if service_account_file_content:
            if isinstance(service_account_file_content, text_type):
                service_account_file_content = \
                    json.loads(service_account_file_content)

            credentials = ServiceAccountCredentials.from_json_keyfile_dict(
                service_account_file_content,
                self.SCOPES
            )
            return credentials.get_access_token().access_token
        return None


class KubernetesApiAuthenticationVariants(KubernetesApiAuthentication):
    VARIANTS = (
        GCPServiceAccountAuthentication,
    )

    def get_token(self):
        return self._get_token()

    def _get_token(self):
        self.logger.debug('Checking Kubernetes authentication options.')

        for variant in self.VARIANTS:
            try:
                candidate = variant(self.logger, self.authentication_data) \
                    .get_token()

                self.logger.debug(
                    'Authentication option {0} will be used'.format(
                        variant.__name__)
                )
                return candidate
            except HelmKuberentesAuthenticationError:
                self.logger.debug(
                    'Authentication option {0} cannot be used'.format(
                        variant.__name__)
                )

        self.logger.debug(
            'Cannot generate Bearer token - no suitable authentication '
            'variant found for {0} properties'.format(self.authentication_data)
        )
        return None
