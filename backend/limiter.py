class _NoopLimiter:
    """Fallback limiter that leaves endpoints unrestricted."""

    def limit(self, *args, **kwargs):  # noqa: D401 - simple passthrough decorator
        """Return a decorator that does not alter the wrapped function."""

        def decorator(func):
            return func

        return decorator


limiter = _NoopLimiter()

