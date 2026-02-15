from typing import Type, Optional, List, Iterable, Any


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


class BaseEnum:
    __names__: Iterable[str]
    __values__: Iterable[str]
    __key__: str
    __value__: str

    @property
    def value(self):
        return self.__value__

    @property
    def name(self):
        return self.__key__

    def __str__(self):
        return self.__key__

    def __hash__(self):
        return hash(str(self.value))

    def __eq__(self, other):
        if type(other) is str:
            if type(self.__value__) is str:
                return self.__key__ == other or self.__value__ == other
            return self.__key__ == other
        if issubclass(type(other), BaseEnum):
            if type(self.__value__) is str:
                return self.__key__ == other.__key__ or self.__value__ == other.__value__
            return self.__key__ == other.__key__
        return self.__key__ == str(other)

    def __repr__(self):
        return f'{self.__key__}.{self.__value__}'

    def __init__(self, m_key, m_val):
        self.__key__ = m_key
        if hasattr(m_val, "__dict__"):
            for key, value in m_val.__dict__.items():
                if not hasattr(self, key):
                    setattr(self, key, value)
        self.__value__ = m_val

    def __init_subclass__(cls):
        import inspect

        fields = {
            k: v
            for k, v in cls.__dict__.items()
            if not inspect.isroutine(v)
               and not k.startswith("_")
               and not isinstance(v, type)
        }
        for k, v in fields.items():
            setattr(cls, k, BaseEnum(k, v))
        setattr(cls, "__names__", fields.keys())
        setattr(cls, "__values__", fields.values())

    @classmethod
    def try_parse(cls: Type, s: Optional[str]) -> Optional[Any]:
        if s is None:
            return None
        if hasattr(cls, s.upper()):
            return getattr(cls, s.upper())
        if hasattr(cls, s):
            return getattr(cls, s)
        return None

    @classmethod
    def parse(cls: Type, s: str, nullable: bool = False) -> Optional[Any]:
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
    def values(cls) -> Iterable[str]:
        """
        list enum values
        """
        return cls.__values__

    @classmethod
    def names(cls) -> Iterable[str]:
        """
        list enum name
        """
        return cls.__names__
