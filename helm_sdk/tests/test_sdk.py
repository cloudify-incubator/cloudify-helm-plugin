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

import mock
import json
from mock import patch
from . import HelmTestBase, HELM_BINARY
from helm_sdk.exceptions import CloudifyHelmSDKError

mock_flags = [{'name': 'dry-run'},
              {'name': 'timeout', 'value': '100'}]
mock_set_args = [{'name': 'x', 'value': 'y'},
                 {'name': 'a', 'value': 'b'}]
mock_install_response = {
    "name": "examplerelease",
    "info": {"status": "deployed"},
    "manifest": "---\n# Source: postgresql/templates/secrets.yaml\napiVersion: v1\nkind: Secret\nmetadata:\n  name: examplerelease-postgresql\n  namespace: \"default\"\n  labels:\n    app.kubernetes.io/name: postgresql\n    helm.sh/chart: postgresql-12.1.7\n    app.kubernetes.io/instance: examplerelease\n    app.kubernetes.io/managed-by: Helm\ntype: Opaque\ndata:\n  postgres-password: \"TXNuRFAxTTFaNA==\"\n  # We don't auto-generate LDAP password when it's not provided as we do for other passwords\n", # noqa
    "version": 1,
    "namespace": "default"
}


class HelmSDKTest(HelmTestBase):

    def test_install_with_token_and_api(self):
        mock_execute = mock.Mock()
        mock_execute.return_value = json.dumps(mock_install_response)
        self.helm.execute = mock_execute
        self.helm.install('release1',
                          'my_chart',
                          mock_flags,
                          mock_set_args,
                          token='demotoken',
                          apiserver='https://1.0.0.0')
        cmd_expected = [
            '/tmp/helm',
            'install',
            'release1',
            'my_chart',
            '--wait',
            '--output=json',
            '--kube-token=demotoken',
            '--kube-apiserver=https://1.0.0.0',
            '--dry-run',
            '--timeout=100',
            '--set',
            "x='y'",
            '--set',
            "a='b'"
        ]
        mock_execute.assert_called_once_with(
            cmd_expected,
            additional_args=None,
            return_output=True
        )

    def test_install_with_kubeconfig(self):
        mock_execute = mock.Mock(return_value='{"manifest":"resourceA"}')
        self.helm.execute = mock_execute
        out = self.helm.install('release1',
                                'my_chart',
                                mock_flags,
                                mock_set_args,
                                kubeconfig='/path/to/config')
        cmd_expected = [HELM_BINARY, 'install', 'release1', 'my_chart',
                        '--wait', '--output=json',
                        '--kubeconfig=/path/to/config', '--dry-run',
                        '--timeout=100', '--set', "x='y'", '--set', "a='b'"]
        mock_execute.assert_called_once_with(cmd_expected,
                                             additional_args=None,
                                             return_output=True)
        self.assertEqual(out, {"manifest": "resourceA"})

    def test_install_no_token_and_no_kubeconfig(self):
        with self.assertRaisesRegexp(CloudifyHelmSDKError,
                                     'Must provide kubeconfig file path.'):
            self.helm.install('release1',
                              'my_chart',
                              mock_flags,
                              mock_set_args,
                              apiserver='https://1.0.0.0')

    def test_install_no_apiserver_and_no_kubeconfig(self):
        with self.assertRaisesRegexp(CloudifyHelmSDKError,
                                     'Must provide kubeconfig file path.'):
            self.helm.install('release1',
                              'my_chart',
                              mock_flags,
                              mock_set_args,
                              token='demotoken')

    @patch('helm_sdk.Helm.check_flag_wait_is_supported', return_value=True)
    def test_uninstall_with_kubekonfig(self, *_):
        mock_execute = mock.Mock()
        self.helm.execute = mock_execute

        self.helm.uninstall('release1',
                            mock_flags,
                            kubeconfig='/path/to/config')
        cmd_expected = [HELM_BINARY, 'uninstall', 'release1', '--wait',
                        '--kubeconfig=/path/to/config', '--dry-run',
                        '--timeout=100']
        mock_execute.assert_called_once_with(cmd_expected,
                                             additional_args=None)

    @patch('helm_sdk.Helm.check_flag_wait_is_supported', return_value=True)
    def test_uninstall_no_token_and_no_kubeconfig(self, *_):
        with self.assertRaisesRegexp(CloudifyHelmSDKError,
                                     'Must provide kubeconfig file path.'):
            self.helm.uninstall('release1',
                                mock_flags,
                                apiserver='https://1.0.0.0')

    @patch('helm_sdk.Helm.check_flag_wait_is_supported', return_value=True)
    def test_uninstall_no_apiserver_and_no_kubeconfig(self, *_):
        with self.assertRaisesRegexp(CloudifyHelmSDKError,
                                     'Must provide kubeconfig file path.'):
            self.helm.uninstall('release1',
                                mock_flags,
                                token='demotoken')

    def test_repo_add(self):
        mock_execute = mock.Mock()
        self.helm.execute = mock_execute
        self.helm.repo_add('my_repo', 'https://github.com/repo')
        cmd_expected = [HELM_BINARY, 'repo', 'add', 'my_repo',
                        'https://github.com/repo']
        mock_execute.assert_called_once_with(cmd_expected,
                                             additional_args=None)

    def test_repo_remove(self):
        mock_execute = mock.Mock()
        self.helm.execute = mock_execute
        self.helm.repo_remove('my_repo')
        cmd_expected = [HELM_BINARY, 'repo', 'remove', 'my_repo']
        mock_execute.assert_called_once_with(cmd_expected,
                                             additional_args=None)

    def test_upgrade_with_token_and_api(self):
        mock_execute = mock.Mock()
        mock_execute.return_value = json.dumps(mock_install_response)
        self.helm.execute = mock_execute
        self.helm.upgrade('release1',
                          'example/mariadb',
                          mock_flags,
                          mock_set_args,
                          token='demotoken',
                          apiserver='https://1.0.0.0')
        cmd_expected = [
            '/tmp/helm',
            'upgrade',
            'release1',
            'example/mariadb',
            '--atomic',
            '-o=json',
            '--kube-token=demotoken',
            '--kube-apiserver=https://1.0.0.0',
            '--dry-run',
            '--timeout=100',
            '--set',
            "x='y'",
            '--set',
            "a='b'"
        ]
        mock_execute.assert_called_once_with(
            cmd_expected,
            additional_args=None,
            return_output=True
        )

    def test_upgrade_with_kubeconfig(self):
        mock_execute = mock.Mock(return_value='{"name":"release1"}')
        self.helm.execute = mock_execute
        out = self.helm.upgrade('release1',
                                'my_chart',
                                mock_flags,
                                mock_set_args,
                                kubeconfig='/path/to/config')
        cmd_expected = [HELM_BINARY, 'upgrade', 'release1', 'my_chart',
                        '--atomic', '-o=json', '--kubeconfig=/path/to/config',
                        '--dry-run', '--timeout=100', '--set', "x='y'",
                        '--set', "a='b'"]
        mock_execute.assert_called_once_with(
            cmd_expected, additional_args=None, return_output=True)
        self.assertEqual(out, {"name": "release1"})

    def test_upgrade_no_token_and_no_kubeconfig(self):
        with self.assertRaisesRegexp(CloudifyHelmSDKError,
                                     'Must provide kubeconfig file path.'):
            self.helm.upgrade('release1',
                              'my_chart',
                              mock_flags,
                              mock_set_args,
                              apiserver='https://1.0.0.0')

    def test_upgrade_no_apiserver_and_no_kubeconfig(self):
        with self.assertRaisesRegexp(CloudifyHelmSDKError,
                                     'Must provide kubeconfig file path.'):
            self.helm.upgrade('release1',
                              'my_chart',
                              mock_flags,
                              mock_set_args,
                              token='demotoken')

    def test_upgrade_no_chart(self):
        with self.assertRaisesRegexp(CloudifyHelmSDKError,
                                     'Must provide chart for upgrade '
                                     'release.'):
            self.helm.upgrade(release_name='release1',
                              flags=mock_flags,
                              set_values=mock_set_args,
                              kubeconfig='/path/to/config')
