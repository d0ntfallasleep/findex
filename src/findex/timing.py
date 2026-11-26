import sys
from functools import wraps
from time import perf_counter


def timed(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        start = perf_counter()
        try:
            return func(*args, **kwargs)
        finally:
            print(
                f"{func.__name__}: {(perf_counter() - start) * 1000:.2f} ms",
                file=sys.stderr,
            )

    return wrapper
