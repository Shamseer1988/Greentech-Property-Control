from datetime import date, datetime

from flask import Blueprint, Response, request

from ..services import reports as report_service
from ..utils.auth import require_permission
from ..utils.responses import success_response, error_response

reports_bp = Blueprint("reports", __name__)


@reports_bp.get("")
@require_permission("report.view")
def list_reports():
    return success_response(data=report_service.list_reports())


@reports_bp.get("/<slug>")
@require_permission("report.view")
def run_report(slug: str):
    filters = {k: v for k, v in request.args.items()}
    try:
        payload = report_service.build_report(slug, filters)
    except KeyError:
        return error_response("Report not found", 404)
    return success_response(data=payload, meta=payload.get("meta"))


_MIME = {
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
}


def _subtitle(payload: dict) -> str:
    """A one-line statement of what the reader is looking at — the month
    or cut-off the figures belong to, and how many rows. Printed reports
    circulate without their filters, so the page has to say."""
    meta = payload.get("meta") or {}
    bits = []
    for key, label in (("month", "Month"), ("upto", "As at"),
                       ("within_days", "Within days")):
        if meta.get(key):
            bits.append(f"{label}: {str(meta[key])[:10]}")
    bits.append(f"{len(payload.get('rows', []))} row(s)")
    bits.append(f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    return " · ".join(bits)


@reports_bp.get("/<slug>/export")
@require_permission("report.export")
def export_report(slug: str):
    filters = {k: v for k, v in request.args.items()}
    fmt = (filters.pop("format", None) or "xlsx").lower()
    if fmt not in _MIME:
        return error_response(f"format must be one of {sorted(_MIME)}", 400)
    try:
        payload = report_service.build_report(slug, filters)
    except KeyError:
        return error_response("Report not found", 404)

    info = report_service.REPORT_REGISTRY[slug]
    columns, rows = payload.get("columns", []), payload.get("rows", [])
    if fmt == "pdf":
        data = report_service.to_pdf(info["title"], columns, rows,
                                     subtitle=_subtitle(payload))
    else:
        data = report_service.to_workbook(info["title"], columns, rows)

    filename = f"{slug}-{date.today().isoformat()}.{fmt}"
    return Response(
        data,
        mimetype=_MIME[fmt],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
