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

import sys
from functools import wraps

from cloudify.exceptions import NonRecoverableError
from cloudify.utils import exception_to_error_cause

from helm_sdk._compat import text_type
from .utils import (
    helm_from_ctx,
    get_auth_token,
    get_values_file,
    get_kubeconfig_file)


def with_helm(func):
    @wraps(func)
    def f(*args, **kwargs):
        ctx = kwargs['ctx']
        with get_kubeconfig_file(ctx) as kubeconfig:
            with get_values_file(ctx,
                                 kwargs.get('values_file')) as values_file:
                helm = helm_from_ctx(ctx)
                kwargs['helm'] = helm
                kwargs['kubeconfig'] = kubeconfig
                kwargs['values_file'] = values_file
                kwargs['token'] = get_auth_token(ctx)
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    _, _, tb = sys.exc_info()
                    raise NonRecoverableError(
                        '{0}'.format(text_type(e)),
                        causes=[exception_to_error_cause(e, tb)])

    return f
