import base64
import csv
import io
from typing import Dict, List

import httpx

from field_models import ExportItemResult, ExportRequest, ExportResponse, FollowUpStatus, WorkOrderPhotoBatch

EXPORT_BUCKET = "field-service-exports"


def needs_follow_up(work_order: WorkOrderPhotoBatch) -> FollowUpStatus:
    note = work_order.technician_note.lower()
    follow_up_markers = ["callback", "follow up", "follow-up", "return visit", "customer call"]
    if work_order.dispatch_status != "completed":
        return FollowUpStatus.needs_follow_up
    if any(marker in note for marker in follow_up_markers):
        return FollowUpStatus.needs_follow_up
    return FollowUpStatus.closed


def ensure_export_bucket() -> None:
    from infrai_client import infrai

    infrai.storage.bucket.create({"name": EXPORT_BUCKET})


def build_csv_bytes(export_request: ExportRequest, item_results: List[ExportItemResult]) -> bytes:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "work_order_id",
            "dispatch_status",
            "photo_count",
            "technician_note",
            "customer_name",
            "scheduled_date",
            "follow_up_status",
        ]
    )
    result_lookup: Dict[str, str] = {item.work_order_id: item.follow_up_status.value for item in item_results}
    for work_order in export_request.work_orders:
        writer.writerow(
            [
                work_order.work_order_id,
                work_order.dispatch_status.value,
                len(work_order.photo_keys),
                work_order.technician_note,
                work_order.customer_name,
                work_order.scheduled_date.isoformat(),
                result_lookup[work_order.work_order_id],
            ]
        )
    return output.getvalue().encode("utf-8")


def build_summary_markdown(export_request: ExportRequest, item_results: List[ExportItemResult]) -> str:
    lines = [
        f"# Work-order export {export_request.export_id}",
        "",
        f"Requested by: {export_request.requested_by}",
        "",
        "| Work order | Status | Follow-up | Photos | Customer |",
        "|---|---|---|---:|---|",
    ]
    lookup = {item.work_order_id: item.follow_up_status.value for item in item_results}
    for work_order in export_request.work_orders:
        lines.append(
            f"| {work_order.work_order_id} | {work_order.dispatch_status.value} | {lookup[work_order.work_order_id]} | {len(work_order.photo_keys)} | {work_order.customer_name} |"
        )
    return "\n".join(lines)


def create_export(export_request: ExportRequest) -> ExportResponse:
    from infrai_client import infrai

    ensure_export_bucket()
    item_results = [
        ExportItemResult(work_order_id=work_order.work_order_id, follow_up_status=needs_follow_up(work_order))
        for work_order in export_request.work_orders
    ]

    csv_key = f"exports/{export_request.export_id}/work_orders.csv"
    pdf_key = f"exports/{export_request.export_id}/work_orders_summary.pdf"

    csv_bytes = build_csv_bytes(export_request, item_results)
    infrai.storage.object.put(
        EXPORT_BUCKET,
        csv_key,
        {
            "content_type": "text/csv",
            "data_base64": base64.b64encode(csv_bytes).decode("ascii"),
        },
    )

    pdf_document = infrai.pdf.generate(
        {
            "markdown": build_summary_markdown(export_request, item_results),
            "page_size": "A4",
            "orientation": "portrait",
            "store": True,
        }
    )

    pdf_response = httpx.get(pdf_document["url"], timeout=30.0)
    pdf_response.raise_for_status()
    infrai.storage.object.put(
        EXPORT_BUCKET,
        pdf_key,
        {
            "content_type": "application/pdf",
            "data_base64": base64.b64encode(pdf_response.content).decode("ascii"),
        },
    )

    csv_presign = infrai.storage.object.presign(
        EXPORT_BUCKET,
        csv_key,
        {
            "op": "get",
            "expires_seconds": 3600,
            "response_disposition": 'attachment; filename="work_orders.csv"',
            "idempotency_key": f"{export_request.export_id}-csv-download",
        },
    )
    pdf_presign = infrai.storage.object.presign(
        EXPORT_BUCKET,
        pdf_key,
        {
            "op": "get",
            "expires_seconds": 3600,
            "response_disposition": 'attachment; filename="work_orders_summary.pdf"',
            "idempotency_key": f"{export_request.export_id}-pdf-download",
        },
    )

    return ExportResponse(
        export_id=export_request.export_id,
        bucket=EXPORT_BUCKET,
        csv_key=csv_key,
        pdf_key=pdf_key,
        csv_download_url=csv_presign["url"],
        pdf_download_url=pdf_presign["url"],
        items=item_results,
    )
