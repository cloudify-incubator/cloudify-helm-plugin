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
import re
import pathlib
from setuptools import setup


def get_version():
    current_dir = pathlib.Path(__file__).parent.resolve()
    with open(os.path.join(current_dir,'cloudify_helm/__version__.py'),
              'r') as outfile:
        var = outfile.read()
        return re.search(r'\d+.\d+.\d+', var).group()


setup(
    name='cloudify-helm-plugin',
    version=get_version(),
    author='Cloudify',
    author_email='hello@cloudify.co',
    description='Enables Cloudify support Helm',
    packages=['helm_sdk', 'cloudify_helm'],
    license='LICENSE',
    install_requires=[
        "cloudify-common>=4.5.5",
        'deepdiff==3.3.0',
        # "cloudify-utilities-plugins-sdk>=0.0.126",
    ],
    test_requires=[
        "cloudify-common>=4.5.5",
        'deepdiff==3.3.0',
    ]
)
