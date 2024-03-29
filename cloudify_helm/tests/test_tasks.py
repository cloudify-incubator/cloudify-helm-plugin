# Copyright © 2024 Dell Inc. or its subsidiaries. All Rights Reserved.

import os
import mock
import json
import shutil
import tempfile

from nativeedge.state import current_ctx
from nativeedge.exceptions import NonRecoverableError

from . import TestBase
from ne_helm.tasks import (
    add_repo,
    pull_chart,
    push_chart,
    remove_repo,
    prepare_args,
    install_binary,
    registry_login,
    install_release,
    upgrade_release,
    uninstall_binary,
    uninstall_release)
from ..constants import (
    HOST,
    API_OPTIONS,
    HELM_CONFIG,
    CONFIGURATION,
    CLIENT_CONFIG,
    RESOURCE_CONFIG,
    EXECUTABLE_PATH,
    CONFIG_DIR_ENV_VAR,
    CACHE_DIR_ENV_VAR,
    DATA_DIR_ENV_VAR)

mock_install_response = {
    "name": "my_release",
    "info": {"status": "deployed"},
    "manifest": "---\n# Source: postgresql/templates/secrets.yaml\napiVersion: v1\nkind: Secret\nmetadata:\n  name: examplerelease-postgresql\n  namespace: \"default\"\n  labels:\n    app.kubernetes.io/name: postgresql\n    helm.sh/chart: postgresql-12.1.7\n    app.kubernetes.io/instance: examplerelease\n    app.kubernetes.io/managed-by: Helm\ntype: Opaque\ndata:\n  postgres-password: \"TXNuRFAxTTFaNA==\"\n  # We don't auto-generate LDAP password when it's not provided as we do for other passwords\n", # noqa
    "version": 1,
    "namespace": "default"
}


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
                "set_values": [{"name": "x", "value": "y"}],
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
        with mock.patch('ne_helm.tasks.create_temporary_env_of_helm',
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

    def test_prepare_args(self):
        properties = {
            "helm_config": {
                "executable_path": "/path/to/helm"
            },
            "use_external_resource": True,
            "resource_config": {
                "name": "stable",
                "repo_url":
                    "https://kubernetes-charts.storage.googleapis.com/",
                "flags": [{'set': 'foo'}, {'set': 'bar'}, 'debug']
            }
        }

        ctx = self.mock_ctx(properties,
                            self.mock_runtime_properties())
        flags_override = [{'set': 'foo'}, {'set': 'baz'}]
        result = prepare_args(
            ctx.node.properties['resource_config'], flags_override)
        expected = properties['resource_config']
        expected['flags'] = [
            {'set': 'foo'},
            {'set': 'bar'},
            'debug',
            {'set': 'baz'},
        ]
        expected['additional_args'] = {'max_sleep_time': 300}
        assert result == expected

    @mock.patch('helm_sdk.Helm.execute')
    @mock.patch('ne_helm.utils.os.path.exists')
    @mock.patch('helm_sdk.Helm.repo_add')
    @mock.patch('ne_helm.utils.get_stored_property')
    def test_add_repo(self,
                      get_resource_config,
                      mock_repo_add,
                      mock_exists,
                      mock_execute):
        mock_execute.return_value = json.dumps('{"foo": "bar"}')
        mock_exists.return_value = True
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

        ctx = self.mock_ctx(
            properties,
            self.mock_runtime_properties())
        get_resource_config.return_value = properties['resource_config']
        current_ctx.set(ctx)
        kwargs = {
            'ctx': ctx
        }
        add_repo(**kwargs)
        mock_repo_add.assert_called_once_with(
            name="stable",
            repo_url="https://kubernetes-charts.storage.googleapis"
                     ".com/",
            flags=[],
            additional_args='{max_sleep_time: 300}')

    @mock.patch('ne_helm.utils.get_stored_property')
    def test_add_repo_use_external_resource(self, get_stored_property):
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
        get_stored_property.return_value = properties.get('resource_config')
        mock_client_repo_list_response = \
            [{"name": "stable",
              "url": "https://kubernetes-charts.storage.googleapis.com/"}]
        with mock.patch('helm_sdk.Helm.repo_list',
                        return_value=mock_client_repo_list_response):
            with mock.patch('helm_sdk.Helm.repo_add') as fake_repo_add:
                with mock.patch('ne_helm.utils.os.path.exists',
                                return_value=True):
                    add_repo(**kwargs)
                    fake_repo_add.assert_not_called()

    @mock.patch('ne_helm.utils.get_stored_property')
    def test_remove_repo(self, get_stored_property):
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
        get_stored_property.return_value = properties.get('resource_config')
        kwargs = {
            'ctx': ctx
        }
        with mock.patch('helm_sdk.Helm.repo_remove') as fake_repo_add:
            with mock.patch('ne_helm.utils.os.path.exists',
                            return_value=True):
                remove_repo(**kwargs)
                fake_repo_add.assert_called_once_with(
                    name="stable",
                    repo_url="https://kubernetes-charts.storage.googleapis"
                             ".com/",
                    flags=[],
                    additional_args={'max_sleep_time': 300})

    @mock.patch('ne_helm.decorators.Kubernetes')
    @mock.patch(
        'nativeedge_kubernetes_sdk.connection.decorators.get_kubeconfig_file')
    @mock.patch('helm_sdk.Helm.execute')
    @mock.patch('helm_sdk.Helm.install')
    @mock.patch('ne_helm.utils.os.path.isfile')
    @mock.patch('ne_helm.utils.os.path.exists')
    def helper_install_release(self,
                               properties,
                               ctx,
                               os_path_exists,
                               os_path_isfile,
                               fake_install,
                               mock_execute,
                               kube_config,
                               *_):
        mock_execute.return_value = json.dumps(mock_install_response)
        os_path_exists.return_value = True
        os_path_isfile.return_value = True
        kwargs = {
            'ctx': ctx
        }
        current_ctx.set(ctx)
        install_release(**kwargs)
        fake_install.assert_called_once_with(
            'my_release',
            chart=properties[RESOURCE_CONFIG]['chart'],
            flags=[],
            set_values=properties[RESOURCE_CONFIG]["set_values"],
            values_file=None,
            kubeconfig=kube_config(),
            token='abcd',
            apiserver=properties[CLIENT_CONFIG][CONFIGURATION]
            [API_OPTIONS][HOST],
            ca_file=None,
            additional_env=None,
            additional_args={'max_sleep_time': 300})

    @mock.patch('ne_helm.decorators.Kubernetes')
    @mock.patch(
        'nativeedge_kubernetes_sdk.connection.decorators.get_kubeconfig_file')
    @mock.patch('helm_sdk.Helm.execute')
    @mock.patch('helm_sdk.Helm.install')
    @mock.patch('ne_helm.utils.os.path.isfile')
    @mock.patch('ne_helm.utils.os.path.exists')
    @mock.patch('ne_helm.utils.get_stored_property')
    def test_install_release(self,
                             get_stored_property,
                             os_path_exists,
                             os_path_isfile,
                             fake_install,
                             mock_execute,
                             kube_config,
                             *_):
        mock_execute.return_value = json.dumps(mock_install_response)
        os_path_exists.return_value = True
        os_path_isfile.return_value = True
        properties = self.mock_install_release_properties()
        get_stored_property.return_value = properties.get('resource_config')
        ctx = self.mock_ctx(properties,
                            self.mock_runtime_properties())
        kwargs = {
            'ctx': ctx
        }
        current_ctx.set(ctx)
        install_release(**kwargs)
        fake_install.assert_called_once_with(
            properties[RESOURCE_CONFIG]["name"],
            chart=properties[RESOURCE_CONFIG]["chart"],
            flags=[],
            set_values=properties[RESOURCE_CONFIG]["set_values"],
            values_file=None,
            kubeconfig=kube_config(),
            token='abcd',
            apiserver=properties[CLIENT_CONFIG][CONFIGURATION]
            [API_OPTIONS][HOST],
            ca_file=None,
            additional_env=None,
            additional_args={'max_sleep_time': 300})

    @mock.patch('ne_helm.utils.get_stored_property')
    def test_install_release_general(self, get_stored_property):
        properties = self.mock_install_release_properties()
        ctx = self.mock_ctx(properties,
                            self.mock_runtime_properties())
        get_stored_property.return_value = properties.get(
            'resource_config')
        self.helper_install_release(properties, ctx)

    @mock.patch('ne_helm.utils.get_stored_property')
    def test_install_release_http_chart(self, get_stored_property):
        properties = self.mock_install_release_properties()
        # replace chart with http-base
        properties["resource_config"]["chart"] = "http://test/package.tgz"
        ctx = self.mock_ctx(properties,
                            self.mock_runtime_properties())
        get_stored_property.return_value = properties.get(
            'resource_config')
        self.helper_install_release(properties, ctx)

    @mock.patch('ne_helm.utils.get_stored_property')
    def test_install_release_local_resources(self, get_stored_property):
        properties = self.mock_install_release_properties()
        input_resouce = "./resources/package.tgz"
        properties["resource_config"]["chart"] = input_resouce
        test_resources = {input_resouce: input_resouce}
        ctx = self.mock_ctx(properties,
                            self.mock_runtime_properties(),
                            test_resources=test_resources)
        get_stored_property.return_value = properties.get(
            'resource_config')

        self.helper_install_release(properties, ctx)

    @mock.patch('ne_helm.utils.get_stored_property')
    def test_install_release_local_resources_rel(self, get_stored_property):
        properties = self.mock_install_release_properties()
        input_resouce = "resources/package.tgz"
        properties["resource_config"]["chart"] = input_resouce
        test_resources = {input_resouce: input_resouce}
        ctx = self.mock_ctx(properties,
                            self.mock_runtime_properties(),
                            test_resources=test_resources)
        get_stored_property.return_value = properties.get(
            'resource_config')
        self.helper_install_release(properties, ctx)

    @mock.patch('ne_helm.utils.get_stored_property')
    def test_uninstall_release(self, get_stored_property):
        properties = self.mock_install_release_properties()
        ctx = self.mock_ctx(properties,
                            self.mock_runtime_properties())
        kwargs = {
            'ctx': ctx
        }
        current_ctx.set(ctx)
        get_stored_property.return_value = properties.get(
            'resource_config')
        with mock.patch('helm_sdk.Helm.uninstall') as fake_uninstall:
            with mock.patch('ne_helm.utils.os.path.exists',
                            return_value=True):
                uninstall_release(**kwargs)
                fake_uninstall.assert_called_once()

    @mock.patch('ne_helm.decorators.Kubernetes')
    @mock.patch(
        'nativeedge_kubernetes_sdk.connection.decorators.get_kubeconfig_file')
    @mock.patch('helm_sdk.Helm.execute')
    @mock.patch('helm_sdk.Helm.upgrade')
    @mock.patch('ne_helm.utils.os.path.isfile')
    @mock.patch('ne_helm.utils.os.path.exists')
    @mock.patch('ne_helm.utils.get_stored_property')
    def test_upgrade_release(self,
                             get_stored_property,
                             os_path_exists,
                             os_path_isfile,
                             fake_upgrade,
                             mock_execute,
                             mock_kube,
                             *_):
        mock_execute.return_value = json.dumps(mock_install_response)
        os_path_exists.return_value = True
        os_path_isfile.return_value = True
        properties = self.mock_install_release_properties()
        properties['resource_config'][
            'values_file'] = 'initial/path/to/values/file'
        get_stored_property.return_value = properties.get('resource_config')
        ctx = self.mock_ctx(properties,
                            self.mock_runtime_properties())
        kwargs = {
            'ctx': ctx,
            'chart': 'example/testchart',
            'values_file': 'upgrade/path/to/values/file',
            'set_values': [{"name": "a", "value": "b"}],
        }
        upgrade_release(**kwargs)
        fake_upgrade.assert_called_once_with(
            'my_release',
            chart='my_chart',
            flags=[],
            set_values=[{"name": "x", "value": "y"}],
            values_file='upgrade/path/to/values/file',
            kubeconfig=mock_kube(),
            token='abcd',
            apiserver=properties[CLIENT_CONFIG][CONFIGURATION]
            [API_OPTIONS][HOST],
            ca_file=None,
            additional_env=None,
            additional_args={'max_sleep_time': 300}
        )

    @mock.patch('ne_helm.decorators.helm_from_ctx')
    @mock.patch('ne_helm.utils.os.path.isfile')
    @mock.patch('ne_helm.utils.os.path.exists')
    @mock.patch('ne_helm.utils.get_stored_property')
    def test_registry_login(self,
                            get_stored_property,
                            os_path_exists,
                            os_path_isfile,
                            mock_helm_from_ctx):
        os_path_exists.return_value = True
        os_path_isfile.return_value = True
        properties = {
            "helm_config": {
                "executable_path": "/path/to/helm"
            },
            "resource_config": {
                'host': '',
                'flags': [],
            }
        }
        mock_helm = mock.Mock()
        mock_helm_from_ctx.return_value = mock_helm
        get_stored_property.return_value = properties.get('resource_config')
        ctx = self.mock_ctx(properties)
        kwargs = {
            'ctx': ctx,
            'flags': [{'name': 'username', 'value': 'foobar'}]
        }
        registry_login(**kwargs)
        mock_helm.registry_login.assert_called_once_with(
            host='',
            flags=[{'name': 'username', 'value': 'foobar'}],
            additional_args={'max_sleep_time': 300}
        )

    @mock.patch('ne_helm.decorators.helm_from_ctx')
    @mock.patch('ne_helm.utils.os.path.isfile')
    @mock.patch('ne_helm.utils.os.path.exists')
    @mock.patch('ne_helm.utils.get_stored_property')
    def test_pull_chart(self,
                        get_stored_property,
                        os_path_exists,
                        os_path_isfile,
                        mock_helm_from_ctx):
        os_path_exists.return_value = True
        os_path_isfile.return_value = True
        properties = self.mock_install_release_properties()
        get_stored_property.return_value = properties.get('resource_config')
        ctx = self.mock_ctx(
            properties,
            self.mock_runtime_properties())
        kwargs = {
            'ctx': ctx
        }
        current_ctx.set(ctx)
        mock_helm = mock.Mock()
        mock_helm_from_ctx.return_value = mock_helm
        pull_chart(**kwargs)
        mock_helm.pull.assert_called_once_with(
            chart='my_chart',
            flags=[],
            additional_args={'max_sleep_time': 300})

    @mock.patch('ne_helm.decorators.helm_from_ctx')
    @mock.patch('ne_helm.utils.os.path.isfile')
    @mock.patch('ne_helm.utils.os.path.exists')
    @mock.patch('ne_helm.utils.get_stored_property')
    def test_push_chart(self,
                        get_stored_property,
                        os_path_exists,
                        os_path_isfile,
                        mock_helm_from_ctx):
        os_path_exists.return_value = True
        os_path_isfile.return_value = True
        properties = self.mock_install_release_properties()
        get_stored_property.return_value = properties.get('resource_config')
        ctx = self.mock_ctx(
            properties,
            self.mock_runtime_properties())
        kwargs = {
            'ctx': ctx
        }
        current_ctx.set(ctx)
        mock_helm = mock.Mock()
        mock_helm_from_ctx.return_value = mock_helm
        push_chart(**kwargs)
        mock_helm.push.assert_called_once_with(
            chart='my_chart',
            flags=[],
            additional_args={'max_sleep_time': 300})
