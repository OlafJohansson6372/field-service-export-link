from fastapi import FastAPI

from export_job import create_export
from field_models import ExportRequest, ExportResponse

app = FastAPI(title="Field Service Export Service")


@app.post("/exports/work-orders", response_model=ExportResponse)
def export_work_orders(request: ExportRequest) -> ExportResponse:
    return create_export(request)
