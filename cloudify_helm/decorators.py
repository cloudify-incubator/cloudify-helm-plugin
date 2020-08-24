from functools import wraps



from tasks import is_using_existing
from utils import (helm_from_ctx,
                   get_kubeconfig_file,
                   get_values_file)


def with_helm(func):
    @wraps(func)
    def f(*args, **kwargs):
        ctx = kwargs['ctx']
        with get_kubeconfig_file(ctx) as kubeconfig:
            with get_values_file(ctx) as values_file:
                helm = helm_from_ctx(ctx)
                kwargs['helm'] = helm
                kwargs['kubeconfig']= kubeconfig
                kwargs['values_file'] = values_file
                return func(*args, **kwargs)

    return f


def skip_if_existing(func):
    @wraps(func)
    def f(*args, **kwargs):
        ctx = kwargs['ctx']
        if not is_using_existing(ctx):
            return func(*args, **kwargs)

    return f
