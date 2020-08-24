from functools import wraps

from utils import helm_from_ctx
from tasks import is_using_existing


def with_helm(func):
    @wraps(func)
    def f(*args, **kwargs):
        ctx = kwargs['ctx']
        helm = helm_from_ctx(ctx)
        kwargs['helm'] = helm
        return func(*args, **kwargs)

    return f


def skip_if_existing(func):
    @wraps(func)
    def f(*args, **kwargs):
        ctx = kwargs['ctx']
        if not is_using_existing(ctx):
            return func(*args, **kwargs)

    return f
