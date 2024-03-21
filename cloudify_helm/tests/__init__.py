# Copyright © 2024 Dell Inc. or its subsidiaries. All Rights Reserved.

import unittest

from nativeedge.state import current_ctx
from nativeedge.mocks import MockNativeEdgeContext


class TestBase(unittest.TestCase):

    def setUp(self):
        super(TestBase, self).setUp()

    def tearDown(self):
        super(TestBase, self).tearDown()

    def mock_ctx(self,
                 test_properties=None,
                 test_runtime_properties=None,
                 test_resources=None,
                 test_operation=None,
                 test_managers=None):
        ctx = MockNativeEdgeContext(
            node_id="test_id",
            node_name="test_name",
            deployment_id='test_deployment',
            managers=test_managers,
            resources=test_resources,
            operation=test_operation,
            properties=test_properties or {},
            runtime_properties=test_runtime_properties,
        )
        current_ctx.set(ctx)
        return ctx
