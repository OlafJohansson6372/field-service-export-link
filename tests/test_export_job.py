from datetime import date
from unittest.mock import Mock

from field_models import DispatchStatus, ExportRequest, WorkOrderPhotoBatch
from export_job import build_csv_bytes, create_export, needs_follow_up


def test_follow_up_decision_and_csv_boundary() -> None:
    request = ExportRequest(
        export_id="batch-2026-03-14",
        requested_by="dispatch@example.com",
        work_orders=[
            WorkOrderPhotoBatch(
                work_order_id="WO-1001",
                dispatch_status=DispatchStatus.completed,
                photo_keys=["photos/WO-1001/front.jpg", "photos/WO-1001/panel.jpg"],
                technician_note="Need customer callback about replacement panel.",
                customer_name="River Street Studio",
                scheduled_date=date(2026, 3, 14),
            ),
            WorkOrderPhotoBatch(
                work_order_id="WO-1002",
                dispatch_status=DispatchStatus.completed,
                photo_keys=["photos/WO-1002/after.jpg"],
                technician_note="Installed and tested successfully.",
                customer_name="North Pier Cafe",
                scheduled_date=date(2026, 3, 14),
            ),
        ],
    )

    results = [
        (request.work_orders[0].work_order_id, needs_follow_up(request.work_orders[0]).value),
        (request.work_orders[1].work_order_id, needs_follow_up(request.work_orders[1]).value),
    ]

    assert results == [
        ("WO-1001", "needs_follow_up"),
        ("WO-1002", "closed"),
    ]

    csv_output = build_csv_bytes(
        request,
        [
            type("Result", (), {"work_order_id": "WO-1001", "follow_up_status": type("Status", (), {"value": "needs_follow_up"})()})(),
            type("Result", (), {"work_order_id": "WO-1002", "follow_up_status": type("Status", (), {"value": "closed"})()})(),
        ],
    ).decode("utf-8")

    assert "work_order_id,dispatch_status,photo_count,technician_note,customer_name,scheduled_date,follow_up_status" in csv_output
    assert "WO-1001,completed,2,Need customer callback about replacement panel.,River Street Studio,2026-03-14,needs_follow_up" in csv_output
    assert "WO-1002,completed,1,Installed and tested successfully.,North Pier Cafe,2026-03-14,closed" in csv_output


def test_generated_pdf_upload_uses_base64_data(monkeypatch) -> None:
    request = ExportRequest(
        export_id="batch-pdf-contract",
        requested_by="dispatch@example.com",
        work_orders=[],
    )
    put = Mock()
    infrai = Mock()
    infrai.storage.object.put = put
    infrai.storage.object.presign.side_effect = [
        {"url": "https://download.example/csv"},
        {"url": "https://download.example/pdf"},
    ]
    infrai.pdf.generate.return_value = {"url": "https://generated.example/summary.pdf"}
    monkeypatch.setattr("infrai_client.infrai", infrai)

    response = Mock(content=b"%PDF-1.7 generated document")
    response.raise_for_status = Mock()
    get = Mock(return_value=response)
    monkeypatch.setattr("export_job.httpx.get", get)

    create_export(request)

    pdf_body = put.call_args_list[1].args[2]
    assert pdf_body == {
        "content_type": "application/pdf",
        "data_base64": "JVBERi0xLjcgZ2VuZXJhdGVkIGRvY3VtZW50",
    }
    get.assert_called_once_with("https://generated.example/summary.pdf", timeout=30.0)
    response.raise_for_status.assert_called_once_with()
