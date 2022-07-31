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
    prepare_aws_env,
    get_ssl_ca_file,
    get_kubeconfig_file,
    get_connection_details_from_shared_cluster)


def with_helm(ignore_properties_values_file=False):
    """
    This decorator creates Helm client for operations and handle special
    parameters like kubeconfig, authentication token etc.
    :param ignore_properties_values_file: whether to ignore the values file
    path resides under properties->resource_config
    (used by upgrade release operation in order avoid collisions between node
    properties and user inputs).
    """

    def decorator(func):
        @wraps(func)
        def f(*args, **kwargs):
            ctx = kwargs['ctx']
            endpoint_from_shared_cluster,\
            token_from_shared_cluster,\
            ssl_ca_cert_from_shared_cluster = \
                get_connection_details_from_shared_cluster()
            if endpoint_from_shared_cluster:
                kwargs['host'] = endpoint_from_shared_cluster
            with get_kubeconfig_file(ctx) as kubeconfig:
                with get_values_file(
                        ctx,
                        ignore_properties_values_file,
                        kwargs.get('values_file')) as values_file:
                    with get_ssl_ca_file(ssl_ca_cert_from_shared_cluster) as \
                            ssl_ca:
                        helm = helm_from_ctx(ctx)
                        kwargs['helm'] = helm
                        kwargs['kubeconfig'] = kubeconfig
                        kwargs['values_file'] = values_file
                        kwargs['token'] = get_auth_token(
                            ctx, token_from_shared_cluster)
                        kwargs['ca_file'] = ssl_ca
                        try:
                            return func(*args, **kwargs)
                        except Exception as e:
                            _, _, tb = sys.exc_info()
                            raise NonRecoverableError(
                                '{0}'.format(text_type(e)),
                                causes=[exception_to_error_cause(e, tb)])
        return f

    return decorator


def prepare_aws(func):
    """
    This decorator prepares AWS environment.
    Check if AWS CLI is needed in order to authenticate with kubernetes and
    prepare the environment variables.
    """
    @wraps(func)
    def f(*args, **kwargs):
        kubeconfig = kwargs.get('kubeconfig')
        kwargs['env_vars'] = prepare_aws_env(kubeconfig)
        try:
            return func(*args, **kwargs)
        except Exception as e:
            _, _, tb = sys.exc_info()
            raise NonRecoverableError(
                '{0}'.format(text_type(e)),
                causes=[exception_to_error_cause(e, tb)])
    return f
