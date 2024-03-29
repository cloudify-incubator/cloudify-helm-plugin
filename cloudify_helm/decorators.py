# Copyright © 2024 Dell Inc. or its subsidiaries. All Rights Reserved.

import sys
from functools import wraps

from nativeedge.exceptions import NonRecoverableError
from nativeedge.utils import exception_to_error_cause

from helm_sdk._compat import text_type
from helm_sdk.kubernetes import Kubernetes

from .utils import (
    helm_from_ctx,
    get_values_file,
    prepare_aws_env)


def with_kubernetes(fn):
    def wrapper(**kwargs):
        kwargs.update(
            {
                'kubernetes': Kubernetes(
                    kwargs['ctx'].logger,
                    kwargs.get('host'),
                    kwargs.get('token'),
                    kwargs.get('kubeconfig')
                )
            }
        )
        return fn(**kwargs)
    return wrapper


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
            with get_values_file(
                    ctx,
                    ignore_properties_values_file,
                    kwargs.get('values_file')) as values_file:
                helm = helm_from_ctx(ctx)
                kwargs['helm'] = helm
                kwargs['values_file'] = values_file
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
        if isinstance(kubeconfig, (dict, str)):
            kwargs['env_vars'] = prepare_aws_env(kubeconfig)
        try:
            return func(*args, **kwargs)
        except Exception as e:
            _, _, tb = sys.exc_info()
            raise NonRecoverableError(
                '{0}'.format(text_type(e)),
                causes=[exception_to_error_cause(e, tb)])
    return f
