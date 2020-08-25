import os
import shutil
import tempfile
import unittest

from cloudify.mocks import (MockContext, MockCloudifyContext,
                            MockNodeInstanceContext,
                            MockNodeContext)

from cloudify_helm.tasks import (install,
                                 uninstall,
                                 install_release)


class TestTasks(unittest.TestCase):

    def setUp(self):
        super(TestTasks, self).setUp()

    def tearDown(self):
        super(TestTasks, self).tearDown()

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

    def test_install_use_existing(self):
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
        install(**kwargs)
        self.assertEqual(ctx.instance.runtime_properties.get(
            "executable_path"),
            properties.get("helm_config").get("executable_path"))

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
        install(**kwargs)
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
        uninstall(**kwargs)
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
        uninstall(**kwargs)
        self.assertEqual(os.path.isfile(fake_executable.name), False)


if __name__ == "__main__":
    unittest.main()
