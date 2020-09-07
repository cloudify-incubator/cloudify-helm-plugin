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

import unittest

from helm_sdk.exceptions import CloudifyHelmSDKError
from helm_sdk.utils import prepare_parameter, prepare_set_parameter


class TestUtils(unittest.TestCase):

    def test_prepare_parameter(self):
        param_dict = {'name': 'param1'}
        self.assertEqual(prepare_parameter(param_dict), '--param1')
        param_dict.update({'value': 'value1'})
        self.assertEqual(prepare_parameter(param_dict), '--param1=value1')

    def test_prepare_set_parameter(self):
        set_dict_no_val = {'name': 'x'}
        with self.assertRaisesRegexp(CloudifyHelmSDKError,
                                     "set parameter name or value is missing"):
            prepare_set_parameter(set_dict_no_val)

        with self.assertRaisesRegexp(CloudifyHelmSDKError,
                                     "set parameter name or value is missing"):
            set_dict_no_name = {'value': 'y'}
            prepare_set_parameter(set_dict_no_name)
        # Now set_dict_no_val is a valid set parameter dictionary
        set_dict_no_val.update(set_dict_no_name)
        self.assertEqual(prepare_set_parameter(set_dict_no_val), '--set x=y')
