"""Server-side pagination for list endpoints.

Reads `page`/`per_page` off the query string (1-indexed page) and applies
LIMIT/OFFSET to an already-filtered, already-ordered SQLAlchemy query. The
`count` an endpoint already puts in `meta` keeps its existing meaning —
"items in this response" — so nothing that reads it breaks; this only adds
the total-across-all-pages figures the frontend needs to render page
controls.
"""
from flask import request


def paginate(query, *, default_per_page: int = 25, max_per_page: int = 200):
    """Returns (rows, meta) where meta = {"page", "per_page", "total_count",
    "total_pages"}. `query` must already carry every filter/order_by the
    caller wants — this only adds offset/limit and a matching count()."""
    page = max(request.args.get("page", default=1, type=int) or 1, 1)
    per_page = min(
        max(request.args.get("per_page", default=default_per_page, type=int) or default_per_page, 1),
        max_per_page,
    )

    total_count = query.order_by(None).count()
    rows = query.offset((page - 1) * per_page).limit(per_page).all()
    total_pages = max((total_count + per_page - 1) // per_page, 1)

    meta = {
        "page": page,
        "per_page": per_page,
        "total_count": total_count,
        "total_pages": total_pages,
    }
    return rows, meta
