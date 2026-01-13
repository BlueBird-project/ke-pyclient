from datetime import datetime as dt, tzinfo, timezone
import pytz

__current_ts__: int = int(dt.now().timestamp() * 1000.0)

# from datetime import datetime
from typing import Optional


# region xsd
def xsd_now(tz=pytz.utc):
    # tz=pytz.timezone('Europe/Paris')
    return xsd_from_ts(current_timestamp(), tz=tz)


def xsd_from_ts(ts: int, tz=pytz.utc) -> str:
    # tz=pytz.timezone('Europe/Paris')
    return dt.fromtimestamp(float(ts) / 1000.0, tz=tz).isoformat()


def xsd_to_ts(xsd_dt: str) -> int:
    return round(dt.fromisoformat(xsd_dt).timestamp() * 1000)


# endregion

# region date
DATE_FORMAT = '%Y-%m-%d'
DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def current_date_str(tz: tzinfo = timezone.utc, dformat=DATE_FORMAT) -> str:
    now_utc = dt.now(tz)
    return now_utc.strftime(dformat)


def datetime_to_str(d: Optional[dt] = None, tz: tzinfo = timezone.utc, dformat: str = DATE_FORMAT) -> str:
    """
    :param dformat:
    :param d: date to parse
    :param tz:
    :return:
    """
    if d is None:
        return current_date_str(tz=tz)
    return d.strftime(format=dformat)


def parse_date(str_date: str, dformat: str = DATE_FORMAT, tz: tzinfo = timezone.utc) -> int:
    d = dt.strptime(str_date, dformat, )
    dt_utc: dt = dt(year=d.year, month=d.month, day=d.day, tzinfo=tz)
    # d.replace(hour=0, minute=0, second=0)
    return to_timestamp(dt_utc)


def parse_date_time(str_date: str, dt_format: str = DATETIME_FORMAT, tz: tzinfo = timezone.utc) -> int:
    # f = "%Y-%m-%d %H:%M:%S.%fZ"
    d: dt = dt.strptime(str_date, dt_format)
    dt_utc: dt = dt(year=d.year, month=d.month, day=d.day, hour=d.hour, minute=d.minute,
                    second=d.second, microsecond=d.microsecond, tzinfo=tz)
    return to_timestamp(dt_utc)


def to_timestamp(datetime_instance: dt) -> int:
    return round(datetime_instance.timestamp() * 1000)


def from_timestamp(ts_ms: int) -> dt:
    return dt.fromtimestamp(timestamp=(float(ts_ms) / 1000.0))


def current_timestamp() -> int:
    now_utc = dt.now(timezone.utc)
    return int(now_utc.timestamp() * 1000)


def current_date() -> dt:
    return dt.now(timezone.utc)


def _tick():
    return int(dt.now(timezone.utc).timestamp() * 1000.0)


def tick():
    global __current_ts__
    __current_ts__ = _tick()
    return __current_ts__


def _tock(start: int, name: str = "tock", print_time=True):
    diff = int(dt.now(timezone.utc).timestamp() * 1000.0) - start
    if print_time and diff > 300:
        print(f"TIME ${name}: {diff} ms")
    return diff


def tock(print_time=True):
    global __current_ts__
    return _tock(start=__current_ts__, print_time=print_time)


def exec_time_monit(func):
    def wrapper(*args, **kwargs):
        name = func.__name__
        ts = _tick()
        try:
            res = func(*args, **kwargs)
            exec_time_ms = _tock(start=ts, name=name, print_time=False)
        except Exception as ex:
            _tock(start=ts, name=name, print_time=True)
            raise ex
        if type(res) is tuple:
            # hotfix TODO: python pre 3.5

            return list(res), exec_time_ms
            # return *res, exec_time_ms
        return res, exec_time_ms

    return wrapper


def exec_time(func):
    def wrapper(*args, **kwargs):
        name = func.__name__
        ts = _tick()
        try:
            res = func(*args, **kwargs)
        finally:
            _tock(start=ts, name=name, print_time=True)
        return res

    return wrapper
