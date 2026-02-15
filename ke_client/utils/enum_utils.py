from typing import Type, Optional, List, Iterable, Any, TypeVar, Generic

from pydantic import ConfigDict


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


T = TypeVar("T")


# E = TypeVar("E", bound="EnumItem")
class EnumItem(Generic[T]):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    __key__: str
    __value__: T

    @property
    def value(self: Type[T]) -> T:
        return self.__value__

    @property
    def name(self):
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

    def __str__(self):
        return self.__key__

    def __repr__(self):
        return f'{self.__key__}.{self.__value__}'

    def __init__(self, m_val: T):
        # if hasattr(m_val, "__dict__"):
        #     for key, value in m_val.__dict__.items():
        #         if not hasattr(self, key):
        #             setattr(self, key, value)
        # self.__key__ = m_key
        self.__value__ = m_val

    @classmethod
    def init_item(cls, m_key: str, m_val: T) -> 'EnumItem[T]':
        # if hasattr(m_val, "__dict__"):
        #     for key, value in m_val.__dict__.items():
        #         if not hasattr(self, key):
        #             setattr(self, key, value)
        instance = cls(m_val=m_val)
        instance.__key__ = m_key
        return instance

    # def lower(self):
    #     return self.name.lower()


class BaseEnum(Generic[T]):
    __names__: Iterable[str]
    __values__: Iterable[T]

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
            setattr(cls, k, EnumItem.init_item(k, v))
        setattr(cls, "__names__", fields.keys())
        setattr(cls, "__values__", fields.values())

    @classmethod
    def try_parse(cls: Type[T], s: Optional[str]) -> Optional[EnumItem[T]]:
        if s is None:
            return None
        if hasattr(cls, s.upper()):
            return getattr(cls, s.upper())
        if hasattr(cls, s):
            return getattr(cls, s)
        return None

    @classmethod
    def parse(cls: Type[T], s: str) -> EnumItem[T]:
        if s is None:
            # if not nullable:
            raise ValueError(f"Invalid enum value '{s}' ({cls.__name__}). ")
            # return None
        if hasattr(cls, s.upper()):
            return getattr(cls, s.upper())
        if hasattr(cls, s):
            return getattr(cls, s)
        # if hasattr(t, s.lower()):
        #     return getattr(t,s.lower())
        # if not nullable:
        raise ValueError(f"Invalid enum value '{s}' ({cls.__name__}). ")
        # return None

    @classmethod
    def value(cls: Type[T], s: str) -> Optional[T]:
        v = cls.try_parse(s)
        if v is not None:
            return v.value
        return None

    @classmethod
    def values(cls: Type[T]) -> Iterable[T]:
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
# SAMPLE:

# class MarketTypeValue(BaseModel):
#     model_config = ConfigDict(arbitrary_types_allowed=True)
#     name: str
#     uri_ref: str
#
#
# class MarketType(BaseEnum["MarketTypeValue"]):
#     DAY_AHEAD = MarketTypeValue(name="DayAheadMarket", uri_ref="DAYAHEAD_MARKET_TYPE")
#     INTRADAY = MarketTypeValue(name="IntradayMarket", uri_ref="INTRADAY_MARKET_TYPE")
#
