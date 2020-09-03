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

import os
import mock
import shutil
import tempfile
import unittest

from cloudify.mocks import MockCloudifyContext
from cloudify.exceptions import NonRecoverableError

from cloudify_helm.tasks import (
    add_repo,
    remove_repo,
    install_binary,
    install_release,
    uninstall_binary,
    uninstall_release)
from cloudify_helm.constants import (
    DATA_DIR_ENV_VAR,
    CACHE_DIR_ENV_VAR,
    CONFIG_DIR_ENV_VAR)


class TestTasks(unittest.TestCase):

    def setUp(self):
        super(TestTasks, self).setUp()

    def tearDown(self):
        super(TestTasks, self).tearDown()

    def mock_runtime_properties(self):
        runtime_properties = {
            CONFIG_DIR_ENV_VAR: '/path/to/config',
            CACHE_DIR_ENV_VAR: '/path/to/cache',
            DATA_DIR_ENV_VAR: '/path/to/data'
        }
        return runtime_properties

    def mock_install_release_properties(self):
        properties = {
            "helm_config": {
                "executable_path": "/path/to/helm"
            },
            "client_config": {
                "kube_token": "abcd",
                "kube_api_server": "https://10.0.0.0"
            },
            "use_external_resource": False,
            "resource_config": {
                "name": "my_release",
                "chart": "my_chart",
                "set_values": {"name": "x", "value": "y"},
                "flags": []
            }

        }
        return properties

    def mock_ctx(self,
                 test_properties,
                 test_runtime_properties=None):
        ctx = MockCloudifyContext(
            node_id="test_id",
            node_name="test_name",
            properties=test_properties,
            runtime_properties=None if not test_runtime_properties
            else test_runtime_properties,
        )
        return ctx

    def test_install_binary_use_existing(self):
        properties = {
            "helm_config": {
                "executable_path": "/tmp/helm_3/helm"
            },
            "use_existing_resource": True,
            "installation_source": "https://fake_link",
        }
        ctx = self.mock_ctx(properties)
        kwargs = {
            'ctx': ctx
        }
        with self.assertRaisesRegexp(NonRecoverableError,
                                     'Helm executable not found'):
            install_binary(**kwargs)

    def test_install(self):
        properties = {
            "helm_config": {
                "executable_path": "/tmp/helm_3/helm"
            },
            "use_existing_resource": False,
            "installation_source":
                "https://get.helm.sh/helm-v3.3.0-linux-s390x.tar.gz",

        }

        ctx = self.mock_ctx(properties)
        kwargs = {
            'ctx': ctx
        }
        install_binary(**kwargs)
        self.assertEqual(ctx.instance.runtime_properties.get(
            "executable_path"),
            properties.get("helm_config").get("executable_path"))
        self.assertTrue(
            os.path.isfile(ctx.instance.runtime_properties.get(
                "executable_path")))

        # cleanup
        shutil.rmtree(os.path.dirname(ctx.instance.runtime_properties.get(
            "executable_path")))

    def test_uninstall_use_existing(self):
        fake_executable = tempfile.NamedTemporaryFile(delete=True)
        properties = {
            "helm_config": {
                "executable_path": fake_executable.name
            },
            "use_existing_resource": True,
            "installation_source":
                "https://get.helm.sh/helm-v3.3.0-linux-s390x.tar.gz",

        }
        ctx = self.mock_ctx(properties)
        kwargs = {
            'ctx': ctx
        }
        uninstall_binary(**kwargs)
        self.assertEqual(os.path.isfile(fake_executable.name), True)

    def test_uninstall(self):
        fake_executable = tempfile.NamedTemporaryFile(delete=False)
        properties = {
            "helm_config": {
                "executable_path": fake_executable.name
            },
            "use_existing_resource": False,
            "installation_source":
                "https://get.helm.sh/helm-v3.3.0-linux-s390x.tar.gz",

        }
        ctx = self.mock_ctx(properties)
        kwargs = {
            'ctx': ctx
        }
        uninstall_binary(**kwargs)
        self.assertEqual(os.path.isfile(fake_executable.name), False)

    def test_add_repo(self):
        properties = {
            "helm_config": {
                "executable_path": "/path/to/helm"
            },
            "use_external_resource": False,
            "resource_config": {
                "name": "stable",
                "repo_url":
                    "https://kubernetes-charts.storage.googleapis.com/",
                "flags": []

            }
        }

        ctx = self.mock_ctx(properties,
                            self.mock_runtime_properties())
        kwargs = {
            'ctx': ctx
        }
        with mock.patch('helm_sdk.Helm.repo_add') as fake_repo_add:
            with mock.patch('cloudify_helm.utils.os.path.exists',
                            return_value=True):
                add_repo(**kwargs)
                fake_repo_add.assert_called_once_with(
                    name="stable",
                    repo_url="https://kubernetes-charts.storage.googleapis"
                             ".com/",
                    flags=[])

    def test_add_repo_use_external_resource(self):
        properties = {
            "helm_config": {
                "executable_path": "/path/to/helm"
            },
            "use_external_resource": True,
            "resource_config": {
                "name": "stable",
                "repo_url":
                    "https://kubernetes-charts.storage.googleapis.com/",
                "flags": []

            }
        }

        ctx = self.mock_ctx(properties,
                            self.mock_runtime_properties())
        kwargs = {
            'ctx': ctx
        }
        mock_client_repo_list_response = \
            [{"name": "stable",
              "url": "https://kubernetes-charts.storage.googleapis.com/"}]
        with mock.patch('helm_sdk.Helm.repo_list',
                        return_value=mock_client_repo_list_response):
            with mock.patch('helm_sdk.Helm.repo_add') as fake_repo_add:
                with mock.patch('cloudify_helm.utils.os.path.exists',
                                return_value=True):
                    add_repo(**kwargs)
                    fake_repo_add.assert_not_called()

    def test_remove_repo(self):
        properties = {
            "helm_config": {
                "executable_path": "/path/to/helm"
            },
            "use_external_resource": False,
            "resource_config": {
                "name": "stable",
                "repo_url":
                    "https://kubernetes-charts.storage.googleapis.com/",
                "flags": []

            }
        }

        ctx = self.mock_ctx(properties,
                            self.mock_runtime_properties())
        kwargs = {
            'ctx': ctx
        }
        with mock.patch('helm_sdk.Helm.repo_remove') as fake_repo_add:
            with mock.patch('cloudify_helm.utils.os.path.exists',
                            return_value=True):
                remove_repo(**kwargs)
                fake_repo_add.assert_called_once_with(
                    name="stable",
                    repo_url="https://kubernetes-charts.storage.googleapis"
                             ".com/",
                    flags=[])

    def test_install_release(self):
        properties = self.mock_install_release_properties()
        ctx = self.mock_ctx(properties,
                            self.mock_runtime_properties())
        kwargs = {
            'ctx': ctx
        }

        with mock.patch('helm_sdk.Helm.install') as fake_install:
            with mock.patch('cloudify_helm.utils.os.path.exists',
                            return_value=True):
                install_release(**kwargs)
                fake_install.assert_called_once_with(
                    name=properties["resource_config"]["name"],
                    chart=properties["resource_config"]["chart"],
                    flags=[],
                    set_values=properties["resource_config"]["set_values"],
                    values_file=None,
                    kubeconfig=None,
                    token=properties["client_config"]["kube_token"],
                    apiserver=properties["client_config"]["kube_api_server"])

    def test_uninstall_release(self):
        properties = self.mock_install_release_properties()
        ctx = self.mock_ctx(properties,
                            self.mock_runtime_properties())
        kwargs = {
            'ctx': ctx
        }

        with mock.patch('helm_sdk.Helm.uninstall') as fake_uninstall:
            with mock.patch('cloudify_helm.utils.os.path.exists',
                            return_value=True):
                uninstall_release(**kwargs)
                fake_uninstall.assert_called_once()

