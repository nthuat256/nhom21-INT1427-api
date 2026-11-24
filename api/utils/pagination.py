from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.types.pagination import PageResult


def paginate(db: Session, model: Any, page: int, page_size: int, query: Any) -> PageResult[Any]:
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": rows, "page": page, "page_size": page_size, "total": total}
