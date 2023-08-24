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

import unittest

from cloudify.state import current_ctx
from cloudify.mocks import MockCloudifyContext


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
        ctx = MockCloudifyContext(
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
