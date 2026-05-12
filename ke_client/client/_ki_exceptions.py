from typing import Optional, List

from setuptools.errors import BaseError


class KIBaseError(BaseError):
    __ctx__: Optional[str]
    __message__: Optional[str]

    def __init__(self, message: str, *args, ctx: str, **kwargs):
        super().__init__(message, *args)
        self.__ctx__ = ctx
        self.__message__ = message

    def call_ctx(self):
        return self.__ctx__

    def __str__(self):
        return f"{self.__message__} in: {self.__ctx__}"


class KITypeError(KIBaseError, TypeError):
    def __init__(self, message: str, *args, ctx: str, **kwargs):
        super().__init__(message, *args, ctx=ctx, **kwargs)


class KIError(KIBaseError, Exception):
    def __init__(self, message: str, *args, ctx: str, **kwargs):
        super().__init__(message, *args, ctx=ctx, **kwargs)


class PatternError(KIBaseError, Exception):
    pattern_error: Optional[List[str]] = None
    result_pattern_error: Optional[List[str]] = None

    def __init__(self, message: str, pattern_error: Optional[List[str]] = None,
                 result_pattern_error=None,
                 *args, ctx: str, **kwargs):
        super().__init__(message, *args, ctx=ctx, **kwargs)
        self.pattern_error = pattern_error
        self.result_pattern_error = pattern_error
# class KIException(KIBaseError, Exception):
#     def __init__(self, message: str, *args, ctx: Optional[str] = None):
#         super().__init__(message, *args, ctx=ctx)
