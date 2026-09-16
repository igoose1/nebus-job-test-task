import datetime
from typing import Any

from sqlalchemy import DateTime, Dialect
from sqlalchemy.types import TypeDecorator


class TZDateTime(TypeDecorator):
    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Dialect) -> datetime.datetime:
        if value is not None:
            if not value.tzinfo or value.tzinfo.utcoffset(value) is None:
                raise TypeError("tzinfo is required")
            value = value.astimezone(datetime.UTC).replace(tzinfo=None)
        return value  # type: ignore

    def process_result_value(
        self,
        value: Any,
        dialect: Dialect,
    ) -> datetime.datetime | None:
        if value is not None:
            value = value.replace(tzinfo=datetime.UTC)
        return value
