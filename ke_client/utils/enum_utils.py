from typing import Type, Optional, List


class EnumUtils:
    __value__: str

    def __init__(self, v):
        self.__value__ = self.__class__.parse(v)

    @property
    def value(self):
        return self.__value__

    @classmethod
    def parse(cls: Type, s: str, nullable: bool = False) -> Optional[str]:
        if s is None:
            if not nullable:
                raise ValueError(f"Invalid enum value '{s}' ({cls.__name__}). ")
            return None
        if hasattr(cls, s.upper()):
            return getattr(cls, s.upper())
        if hasattr(cls, s):
            return getattr(cls, s)
        # if hasattr(t, s.lower()):
        #     return getattr(t,s.lower())
        if not nullable:
            raise ValueError(f"Invalid enum value '{s}' ({cls.__name__}). ")
        return None

    @classmethod
    def try_parse(cls: Type, s: Optional[str]) -> Optional[str]:
        if s is None:
            return None
        if hasattr(cls, s.upper()):
            return getattr(cls, s.upper())
        if hasattr(cls, s):
            return getattr(cls, s)
        return None

    def __str__(self):
        return self.value

    def __hash__(self):
        return hash(str(self.value))

    def __eq__(self, other):
        if type(other) is str:
            return self.value == other
        return self.value == other

    def __repr__(self):
        return f'{type(self).__name__}.{self.__value__}'

    @classmethod
    def values(cls):
        """
        list enum values
        """
        import inspect
        return [enum_field for enum_field in inspect.getmembers(cls) if
                not enum_field[0].startswith("_") and not inspect.ismethod(enum_field[1]) and not enum_field[
                                                                                                      0] == "value"]

    @classmethod
    def names(cls) -> List[str]:
        """
        list enum values
        """
        import inspect
        return [enum_field[0] for enum_field in inspect.getmembers(cls) if
                not enum_field[0].startswith("_") and not inspect.ismethod(enum_field[1]) and not enum_field[
                                                                                                      0] == "value"]
