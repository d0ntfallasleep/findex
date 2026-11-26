import logging
from collections.abc import Callable
from functools import wraps
from time import perf_counter

logger = logging.getLogger(__name__)


def timed[**P, T](func: Callable[P, T]) -> Callable[P, T]:
    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        start = perf_counter()
        try:
            return func(*args, **kwargs)
        finally:
            logger.info("%s: %.2f ms", func.__name__, (perf_counter() - start) * 1000)

    return wrapper
