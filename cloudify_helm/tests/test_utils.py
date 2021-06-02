########
# Copyright (c) 2021 Cloudify Platform Ltd. All rights reserved
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

import os
import mock

from cloudify.state import current_ctx
from cloudify.exceptions import NonRecoverableError

from . import TestBase
from ..utils import (create_venv,
                     get_ssl_ca_file,
                     install_aws_cli_if_needed,
                     check_aws_cmd_in_kubeconfig)
from ..constants import (API_OPTIONS,
                         SSL_CA_CERT,
                         AWS_CLI_VENV,
                         CLIENT_CONFIG,
                         CONFIGURATION,
                         AUTHENTICATION,
                         AWS_ENV_VAR_LIST)

RESOURCES = 'resources'


class TestUtils(TestBase):

    def setUp(self):
        super(TestBase, self).setUp()
        self.eks_kubeconfig = os.path.join(os.path.dirname(__file__),
                                           RESOURCES,
                                           'kubeconfig_eks.yaml')

        self.gke_kubeconfig = os.path.join(os.path.dirname(__file__),
                                           RESOURCES,
                                           'kubeconfig_gke.yaml')

    def tearDown(self):
        super(TestBase, self).tearDown()

    def mock_properties(self):
        properties = {
            "client_config": {
                "configuration": {
                    "api_options": {
                        "api_key": "abcd",
                        "host": "https://10.0.0.0"
                    }
                },
                "authentication": {
                    "aws_access_key_id": "demoaccesskeyid",
                    "aws_secret_access_key": "demosecretaccesskey",
                    "aws_default_region": "us-east-1"
                }
            },
        }
        return properties

    def test_install_aws_cli_if_needed_no_kubeconfig(self):
        res = install_aws_cli_if_needed()
        self.assertEqual(res, None)

    def test_install_aws_cli_if_needed_no_aws_cmd(self):
        current_ctx.set(self.mock_ctx(test_properties={}))
        res = install_aws_cli_if_needed(kubeconfig=self.gke_kubeconfig)
        self.assertEqual(res, None)

    def test_install_aws_cli_if_needed_no_aws_property(self):
        for aws_prop in AWS_ENV_VAR_LIST:
            properties = self.mock_properties()
            del properties[CLIENT_CONFIG][AUTHENTICATION][aws_prop.lower()]
            current_ctx.set(self.mock_ctx(test_properties=properties))
            with self.assertRaisesRegexp(NonRecoverableError,
                                         'one of: aws_access_key_id, '
                                         'aws_secret_access_key, '
                                         'aws_default_region is missing under '
                                         'client_config.authentication'):
                install_aws_cli_if_needed(self.eks_kubeconfig)

    def test_check_aws_cmd_in_kubeconfig(self):
        current_ctx.set(self.mock_ctx(test_properties={}))
        self.assertEqual(check_aws_cmd_in_kubeconfig(self.eks_kubeconfig),
                         True)
        self.assertEqual(check_aws_cmd_in_kubeconfig(self.gke_kubeconfig),
                         False)

    def test_create_venv(self):
        fake_deployment_dir = os.path.join('/opt',
                                           'mgmtworker',
                                           'work',
                                           'deployments',
                                           'default-tenant',
                                           'test-deployment')
        with mock.patch('cloudify_helm.utils.get_deployment_dir'):
            with mock.patch('cloudify_helm.utils.tempfile.mkdtemp',
                            return_value=fake_deployment_dir):
                with mock.patch('cloudify_helm.utils.run_subprocess'):
                    ctx = self.mock_ctx(test_properties={})
                    current_ctx.set(ctx)
                    create_venv()
                    self.assertEqual(
                        ctx.instance.runtime_properties.get(AWS_CLI_VENV),
                        fake_deployment_dir)

    def test_get_ssl_ca_file_content_in_blueprint(self):
        properties = self.mock_properties()
        ca_content = 'fake_ca_content_inside_blueprint'
        properties[CLIENT_CONFIG][CONFIGURATION][API_OPTIONS][
            SSL_CA_CERT] = ca_content
        current_ctx.set(self.mock_ctx(test_properties=properties))
        with mock.patch('cloudify_helm.utils.check_if_resource_inside_'
                        'blueprint_folder', return_value=False):
            with get_ssl_ca_file() as ca_file:
                with open(ca_file, 'r') as temp_ca_file:
                    self.assertEqual(temp_ca_file.read(), ca_content)

    def test_get_ssl_ca_file_on_the_manager(self):
        properties = self.mock_properties()
        ca_file_path = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                                    RESOURCES,
                                                    'ca_file'))
        properties[CLIENT_CONFIG][CONFIGURATION][API_OPTIONS][
            SSL_CA_CERT] = ca_file_path
        current_ctx.set(self.mock_ctx(test_properties=properties))
        with mock.patch('cloudify_helm.utils.check_if_resource_inside_'
                        'blueprint_folder', return_value=False):
            with get_ssl_ca_file() as ca_file:
                self.assertEqual(os.path.abspath(ca_file), ca_file_path)

    def test_get_ssl_ca_file_no_ca(self):
        properties = self.mock_properties()
        properties[CLIENT_CONFIG][CONFIGURATION][API_OPTIONS][
            SSL_CA_CERT] = ''
        current_ctx.set(self.mock_ctx(test_properties=properties))
        with mock.patch('cloudify_helm.utils.check_if_resource_inside_'
                        'blueprint_folder', return_value=False):
            with get_ssl_ca_file() as ca_file:
                self.assertEqual(ca_file, None)
