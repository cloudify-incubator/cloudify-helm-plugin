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

from cloudify.state import current_ctx
from cloudify.exceptions import NonRecoverableError

from . import TestBase
from ..tasks import (
    add_repo,
    remove_repo,
    install_binary,
    install_release,
    upgrade_release,
    uninstall_binary,
    uninstall_release)
from ..constants import (
    HOST,
    API_KEY,
    API_OPTIONS,
    HELM_CONFIG,
    CONFIGURATION,
    CLIENT_CONFIG,
    RESOURCE_CONFIG,
    EXECUTABLE_PATH,
    CONFIG_DIR_ENV_VAR,
    CACHE_DIR_ENV_VAR,
    DATA_DIR_ENV_VAR)


class TestTasks(TestBase):

    def setUp(self):
        super(TestBase, self).setUp()

    def tearDown(self):
        super(TestBase, self).tearDown()

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
                "configuration": {
                    "api_options": {
                        "api_key": "abcd",
                        "host": "https://10.0.0.0"
                    }
                }
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
        with mock.patch('cloudify_helm.tasks.create_temporary_env_of_helm',
                        return_value=None):
            install_binary(**kwargs)
            self.assertEqual(ctx.instance.runtime_properties.get(
                EXECUTABLE_PATH),
                properties.get(HELM_CONFIG).get(EXECUTABLE_PATH))
            self.assertTrue(
                os.path.isfile(ctx.instance.runtime_properties.get(
                    EXECUTABLE_PATH)))

        # cleanup
        shutil.rmtree(os.path.dirname(ctx.instance.runtime_properties.get(
            EXECUTABLE_PATH)))

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
                "flags": [],
                'additional_args': '{''max_sleep_time'': 300}'
            }
        }

        ctx = self.mock_ctx(properties,
                            self.mock_runtime_properties())
        current_ctx.set(ctx)
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
                    flags=[],
                    additional_args='{max_sleep_time: 300}')

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
        current_ctx.set(ctx)
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
                    flags=[],
                    additional_args={'max_sleep_time': 300})

    def test_install_release(self):
        properties = self.mock_install_release_properties()
        ctx = self.mock_ctx(properties,
                            self.mock_runtime_properties())
        kwargs = {
            'ctx': ctx
        }
        current_ctx.set(ctx)
        with mock.patch('helm_sdk.Helm.install') as fake_install:
            with mock.patch('cloudify_helm.utils.os.path.exists',
                            return_value=True):
                install_release(**kwargs)
                fake_install.assert_called_once_with(
                    name=properties[RESOURCE_CONFIG]["name"],
                    chart=properties[RESOURCE_CONFIG]["chart"],
                    flags=[],
                    set_values=properties[RESOURCE_CONFIG]["set_values"],
                    values_file=None,
                    kubeconfig=None,
                    token=properties[CLIENT_CONFIG][CONFIGURATION][API_OPTIONS]
                    [API_KEY],
                    apiserver=properties[CLIENT_CONFIG][CONFIGURATION]
                    [API_OPTIONS][HOST],
                    ca_file=None,
                    additional_env={},
                    additional_args='{max_sleep_time: 300}')

    def test_uninstall_release(self):
        properties = self.mock_install_release_properties()
        ctx = self.mock_ctx(properties,
                            self.mock_runtime_properties())
        kwargs = {
            'ctx': ctx
        }
        current_ctx.set(ctx)
        with mock.patch('helm_sdk.Helm.uninstall') as fake_uninstall:
            with mock.patch('cloudify_helm.utils.os.path.exists',
                            return_value=True):
                uninstall_release(**kwargs)
                fake_uninstall.assert_called_once()

    def test_upgrade_release_no_chart(self):
        properties = self.mock_install_release_properties()
        ctx = self.mock_ctx(properties,
                            self.mock_runtime_properties())
        kwargs = {
            'ctx': ctx
        }
        current_ctx.set(ctx)
        with self.assertRaisesRegexp(NonRecoverableError,
                                     'Must provide chart for'
                                     ' upgrade release.'):
            with mock.patch('cloudify_helm.utils.os.path.exists',
                            return_value=True):
                upgrade_release(**kwargs)

    def test_upgrade_release(self):
        properties = self.mock_install_release_properties()
        properties['resource_config'][
            'values_file'] = 'initial/path/to/values/file'
        ctx = self.mock_ctx(properties,
                            self.mock_runtime_properties())
        kwargs = {
            'ctx': ctx,
            'chart': 'example/testchart',
            'values_file': 'upgrade/path/to/values/file',
            'set_values': {"name": "a", "value": "b"}
        }
        with mock.patch('helm_sdk.Helm.upgrade',
                        return_value='Success!') as fake_upgrade:
            with mock.patch('cloudify_helm.utils.os.path.exists',
                            return_value=True):
                with mock.patch('cloudify_helm.utils.os.path.isfile',
                                return_value=True):
                    upgrade_release(**kwargs)
                    fake_upgrade.assert_called_once_with(
                        release_name=properties[RESOURCE_CONFIG]["name"],
                        chart='example/testchart',
                        flags=None,
                        set_values={"name": "a", "value": "b"},
                        values_file='upgrade/path/to/values/file',
                        kubeconfig=None,
                        token=properties[CLIENT_CONFIG][CONFIGURATION]
                        [API_OPTIONS][API_KEY],
                        apiserver=properties[CLIENT_CONFIG][CONFIGURATION]
                        [API_OPTIONS][HOST],
                        ca_file=None,
                        additional_env={})
