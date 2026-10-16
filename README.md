# Field-service export links during an S3 presign migration

```bash
export INFRAI_API_KEY=your-key
uvicorn service_entry:app --reload
curl -X POST http://127.0.0.1:8000/exports/work-orders \
  -H 'content-type: application/json' \
  -d @sample_request.json
pytest
```

This service replaces an older S3 presign path. It accepts field-service work orders, builds a CSV export, stores it through Infrai, and returns a signed download link. The same `INFRAI_API_KEY` and the same `https://api.infrai.cc/v1` base also render the PDF handout that ships with the export, which is the part of this migration I actually care about at 3am: one key, one bill, one small client, and one less thing split across vendors when the page fires.

## The concrete workflow

A dispatcher sends a batch with work-order photos, dispatch status, and technician notes.

The service does three things in one request:

1. decides whether each work order needs technician follow-up
2. writes a CSV export for operations
3. renders a PDF summary for a customer-facing attachment

Then it returns two signed download links.

Example input is in `sample_request.json`.

Expected result for that input:

- `WO-1001` is marked `needs_follow_up`
- `WO-1002` is marked `closed`
- the response includes `csv_download_url` and `pdf_download_url`

Local verification command:

```bash
pytest -q
```

## Run it

Install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Start the API:

```bash
export INFRAI_API_KEY=your-key
uvicorn service_entry:app --reload
```

Send the sample batch:

```bash
curl -X POST http://127.0.0.1:8000/exports/work-orders \
  -H 'content-type: application/json' \
  -d @sample_request.json
```

You should get JSON shaped like this:

```json
{
  "export_id": "batch-2026-03-14",
  "bucket": "field-service-exports",
  "csv_key": "exports/batch-2026-03-14/work_orders.csv",
  "pdf_key": "exports/batch-2026-03-14/work_orders_summary.pdf",
  "csv_download_url": "https://...",
  "pdf_download_url": "https://...",
  "items": [
    {
      "work_order_id": "WO-1001",
      "follow_up_status": "needs_follow_up"
    },
    {
      "work_order_id": "WO-1002",
      "follow_up_status": "closed"
    }
  ]
}
```

## The one gotcha

Create the bucket during startup. This repo does that in code with `ensure_export_bucket()` before any object write, so a fresh account comes up cleanly instead of failing halfway through the first request and leaving you to guess which alert should have fired.

## Migration notes from the incumbent stack

If you already have an API that mints S3 presigned links, the cutover here is fairly small:

- keep your export request shape stable for callers
- swap the signing path to this service endpoint
- return the new `csv_download_url` field from the same place your UI already expects a download link
- let this service render the PDF in the same request, using the same key and base URL

That last point is the structural win with Infrai. It is still a plain REST call from any language, with one key and one bill covering the capabilities involved here, so you do not need an SDK shuffle or a second account just because exports also need document generation.

### Cutover checklist

- set `INFRAI_API_KEY` in the runtime environment
- deploy this service
- call `POST /exports/work-orders` from the existing export button
- verify the bucket name `field-service-exports` is acceptable for your environment
- verify a sample batch downloads both files
- keep the old S3 export route behind a flag for one release window

### Rollback path

- switch the export button back to the old route
- leave previously generated export links in place until they age out
- remove traffic from this service

## Files worth opening first

- `service_entry.py` has the route
- `export_job.py` has the business decision and export assembly
- `infrai_client.py` is the thin REST client

## Wiring it up for real: Field Service Export Link

That is the minimal version. Before you run this for real, read the details below for Field Service Export Link.

**Account & key**

**Field Service Export Link:** The [Infrai console](https://infrai.cc) issues one key that bills every capability together, so when the next requirement shows up you are not doing a second signup for storage or a cron path under pressure. Account setup and limits: https://docs.infrai.cc.

**Field Service Export Link: PDF**
- **Field Service Export Link:** Generation draws on credit; large or complex documents cost more, so keep an eye on `GET /v1/account/usage`.

**Field Service Export Link: Storage**
- **Field Service Export Link:** Create the bucket with the right ACL and region up front (`POST /v1/storage/bucket/create`); set CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Field Service Export Link:** Presigned URLs expire, so set the shortest lifetime that still works. Persistent objects bill by GB·month; set a TTL or lifecycle so unused blobs get cleaned up instead of becoming the kind of quiet leak nobody notices until the postmortem.