class _NoopLimiter:
    def limit(self, *args, **kwargs):
        def deco(fn):
            return fn

        return deco


limiter = _NoopLimiter()
