from typing import Generic, TypeVar, TypedDict

T = TypeVar("T")


class PageResult(TypedDict, Generic[T]):
    items: list[T]
    page: int
    page_size: int
    total: int
