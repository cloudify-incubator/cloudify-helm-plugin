import sys
from functools import wraps

from cloudify.exceptions import NonRecoverableError
from cloudify.utils import exception_to_error_cause

from helm_sdk._compat import text_type
from .utils import (
    helm_from_ctx,
    get_values_file,
    get_kubeconfig_file)


def with_helm(func):
    @wraps(func)
    def f(*args, **kwargs):
        ctx = kwargs['ctx']
        with get_kubeconfig_file(ctx) as kubeconfig:
            with get_values_file(ctx) as values_file:
                helm = helm_from_ctx(ctx)
                kwargs['helm'] = helm
                kwargs['kubeconfig'] = kubeconfig
                kwargs['values_file'] = values_file
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    _, _, tb = sys.exc_info()
                    raise NonRecoverableError(
                        '{0}'.format(text_type(e),
                                     causes=[exception_to_error_cause(e, tb)]))

    return f
