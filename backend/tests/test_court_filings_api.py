import pytest


@pytest.mark.asyncio
async def test_create_filing_success(client):
    payload = {
        "case_number": "А40-12345/2026",
        "court_name": "Арбитражный суд г. Москвы",
        "claim_type": "Исковое заявление",
        "documents": [
            {
                "filename": "isk.pdf",
                "mime_type": "application/pdf",
                "size_bytes": 1024,
            }
        ],
    }
    response = await client.post("/court-filings/submissions", json=payload)
    assert response.status_code == 201
    body = response.json()
    assert body["case_number"] == payload["case_number"]
    assert body["status"] == "submitted"
    assert body["tracking_number"].startswith("CF-")
    assert len(body["documents"]) == 1


@pytest.mark.asyncio
async def test_create_filing_validation_error(client):
    payload = {
        "case_number": "А40-12345/2026",
        "court_name": "Арбитражный суд г. Москвы",
        "claim_type": "Исковое заявление",
        "documents": [
            {
                "filename": "isk.txt",
                "mime_type": "text/plain",
                "size_bytes": 1024,
            }
        ],
    }
    response = await client.post("/court-filings/submissions", json=payload)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_update_filing_status_and_get(client):
    create_payload = {
        "case_number": "А40-99999/2026",
        "court_name": "Арбитражный суд г. Москвы",
        "claim_type": "Апелляционная жалоба",
        "documents": [
            {
                "filename": "appeal.docx",
                "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "size_bytes": 2048,
            }
        ],
    }
    created = await client.post("/court-filings/submissions", json=create_payload)
    filing_id = created.json()["id"]

    patch_resp = await client.patch(
        f"/court-filings/submissions/{filing_id}/status",
        json={"status": "in_review", "comment": "Документ передан судье"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["status"] == "in_review"

    get_resp = await client.get(f"/court-filings/submissions/{filing_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == filing_id


@pytest.mark.asyncio
async def test_openapi_contains_court_filings_paths(client):
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/court-filings/submissions" in paths
    assert "/court-filings/submissions/{filing_id}/status" in paths
