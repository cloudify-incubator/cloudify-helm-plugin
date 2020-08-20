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

import mock

from . import HelmTestBase, HELM_BINARY

mock_flags = [{'name': 'kube-token', 'value': 'demotoken'},
              {'name': 'kube-apiserver', 'value': 'https://1.0.0.0'}]
mock_set_args = [{'name': 'x', 'value': 'y'},
                 {'name': 'a', 'value': 'b'}]


class HelmSDKTest(HelmTestBase):

    def test_install(self):
        mock_execute = mock.Mock(return_value='{"manifest":"resourceA"}')
        self.helm.execute = mock_execute
        out = self.helm.install('release1', 'my_chart',
                                mock_flags,
                                mock_set_args)
        cmd_expected = [HELM_BINARY, 'install', 'release1', 'my_chart',
                        '--wait', '--output=json',
                        '--kube-token=demotoken',
                        '--kube-apiserver=https://1.0.0.0', '--set x=y',
                        '--set a=b']
        mock_execute.assert_called_once_with(cmd_expected, True)
        self.assertEqual(out, {"manifest": "resourceA"})

    def test_uninstall(self):
        mock_execute = mock.Mock()
        self.helm.execute = mock_execute
        self.helm.uninstall('release1', mock_flags)
        cmd_expected = [HELM_BINARY, 'uninstall', 'release1',
                        '--kube-token=demotoken',
                        '--kube-apiserver=https://1.0.0.0']
        mock_execute.assert_called_once_with(cmd_expected)

    def test_repo_add(self):
        mock_execute = mock.Mock()
        self.helm.execute = mock_execute
        self.helm.repo_add('my_repo', 'https://github.com/repo')
        cmd_expected = [HELM_BINARY, 'repo', 'add', 'my_repo',
                        'https://github.com/repo']
        mock_execute.assert_called_once_with(cmd_expected)

    def test_repo_remove(self):
        mock_execute = mock.Mock()
        self.helm.execute = mock_execute
        self.helm.repo_remove('my_repo')
        cmd_expected = [HELM_BINARY, 'repo', 'remove', 'my_repo']
        mock_execute.assert_called_once_with(cmd_expected)
