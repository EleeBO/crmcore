"""Tests for POST /api/v1/upload endpoint."""

from __future__ import annotations

import io
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


def _mock_generate_scenario():
    """Patch generate_scenario to return a mock Scenario with data."""
    from backend.pipeline.scenario import KeyFact, Objection, Scenario

    scenario = Scenario(
        key_facts=[KeyFact(fact="Test fact", source_file="test.pdf", source_page=1)],
        objections=[Objection(trigger="дорого", response="Нет")],
        talking_points=["point 1"],
    )
    return patch(
        "backend.pipeline.scenario.generate_scenario",
        new_callable=AsyncMock,
        return_value=scenario,
    )


def _mock_generate_scenario_empty():
    """Patch generate_scenario to return empty Scenario (LLM failure)."""
    from backend.pipeline.scenario import Scenario

    return patch(
        "backend.pipeline.scenario.generate_scenario",
        new_callable=AsyncMock,
        return_value=Scenario(),
    )


@pytest.fixture
async def upload_client(mock_redis):
    from backend.main import create_app

    app = create_app()
    app.state.redis = mock_redis
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


@pytest.mark.asyncio
async def test_upload_pdf_returns_knowledge_base_id(upload_client, mock_redis):
    """Upload a valid PDF → returns knowledge_base_id and chunks_count > 0."""
    import pathlib

    fixture = pathlib.Path(__file__).parent / "fixtures" / "sample.pdf"
    pdf_bytes = fixture.read_bytes()

    with _mock_generate_scenario():
        resp = await upload_client.post(
            "/api/v1/upload",
            files={"files": ("sample.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
            data={"session_id": "sess-001"},
        )

    assert resp.status_code in (200, 207), resp.text
    body = resp.json()
    assert "knowledge_base_id" in body
    assert len(body["knowledge_base_id"]) > 0
    assert body["chunks_count"] > 0
    assert body["files_indexed"] == 1
    assert body["failed_files"] == []
    mock_redis.set.assert_called()


@pytest.mark.asyncio
async def test_upload_docx_returns_chunks(upload_client):
    """Upload DOCX → chunks_count > 0."""
    import pathlib

    fixture = pathlib.Path(__file__).parent / "fixtures" / "sample.docx"
    docx_bytes = fixture.read_bytes()

    with _mock_generate_scenario():
        resp = await upload_client.post(
            "/api/v1/upload",
            files={
                "files": (
                    "sample.docx",
                    io.BytesIO(docx_bytes),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
            data={"session_id": "sess-002"},
        )

    assert resp.status_code in (200, 207), resp.text
    body = resp.json()
    assert body["chunks_count"] > 0


@pytest.mark.asyncio
async def test_upload_unsupported_type_returns_422_or_207(upload_client):
    """Uploading an .exe file: all files fail → 422."""
    # No scenario mock needed — upload fails before scenario generation
    resp = await upload_client.post(
        "/api/v1/upload",
        files={
            "files": (
                "malware.exe",
                io.BytesIO(b"MZ"),
                "application/octet-stream",
            )
        },
        data={"session_id": "sess-003"},
    )
    assert resp.status_code == 422
    body = resp.json()
    assert len(body.get("failed_files", [])) > 0


@pytest.mark.asyncio
async def test_upload_missing_session_id_returns_422(upload_client):
    """Missing session_id form field → 422."""
    resp = await upload_client.post(
        "/api/v1/upload",
        files={"files": ("x.pdf", io.BytesIO(b"%PDF"), "application/pdf")},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_upload_multiple_files(upload_client):
    """Multiple files → files_indexed equals success count."""
    import pathlib

    fixture_dir = pathlib.Path(__file__).parent / "fixtures"
    pdf_bytes = (fixture_dir / "sample.pdf").read_bytes()
    docx_bytes = (fixture_dir / "sample.docx").read_bytes()

    with _mock_generate_scenario():
        resp = await upload_client.post(
            "/api/v1/upload",
            files=[
                ("files", ("sample.pdf", io.BytesIO(pdf_bytes), "application/pdf")),
                (
                    "files",
                    (
                        "sample.docx",
                        io.BytesIO(docx_bytes),
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    ),
                ),
            ],
            data={"session_id": "sess-004"},
        )

    assert resp.status_code in (200, 207), resp.text
    body = resp.json()
    assert body["files_indexed"] == 2
    assert body["chunks_count"] > 0


@pytest.mark.asyncio
async def test_upload_response_has_time_ms(upload_client):
    """Response includes time_ms field."""
    import pathlib

    fixture = pathlib.Path(__file__).parent / "fixtures" / "sample.pdf"
    pdf_bytes = fixture.read_bytes()

    with _mock_generate_scenario():
        resp = await upload_client.post(
            "/api/v1/upload",
            files={"files": ("sample.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
            data={"session_id": "sess-005"},
        )

    body = resp.json()
    assert "time_ms" in body
    assert isinstance(body["time_ms"], int)


# ── New tests for scenario generation ────────────────────────────────────


@pytest.mark.asyncio
async def test_upload_generates_scenario(upload_client, mock_redis):
    """Upload calls generate_scenario and stores result in Redis."""
    import pathlib

    fixture = pathlib.Path(__file__).parent / "fixtures" / "sample.pdf"
    pdf_bytes = fixture.read_bytes()

    with _mock_generate_scenario() as mock_gen:
        resp = await upload_client.post(
            "/api/v1/upload",
            files={"files": ("sample.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
            data={"session_id": "sess-scenario"},
        )

    assert resp.status_code in (200, 207), resp.text
    mock_gen.assert_called_once()
    # Verify scenario stored in Redis
    calls = [str(c) for c in mock_redis.set.call_args_list]
    scenario_calls = [c for c in calls if "scenario" in c]
    assert len(scenario_calls) >= 1, f"Expected scenario Redis set, got: {calls}"


@pytest.mark.asyncio
async def test_upload_returns_scenario_preview(upload_client):
    """Response contains scenario preview when scenario has data."""
    import pathlib

    fixture = pathlib.Path(__file__).parent / "fixtures" / "sample.pdf"
    pdf_bytes = fixture.read_bytes()

    with _mock_generate_scenario():
        resp = await upload_client.post(
            "/api/v1/upload",
            files={"files": ("sample.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
            data={"session_id": "sess-preview"},
        )

    body = resp.json()
    assert body["scenario_generated"] is True
    assert body["scenario"] is not None
    assert "portrait" in body["scenario"]
    assert "objections_count" in body["scenario"]
    assert body["scenario"]["objections_count"] == 1


@pytest.mark.asyncio
async def test_upload_llm_failure_still_saves_docs_text(upload_client, mock_redis):
    """When LLM returns empty Scenario, docs_text is still saved."""
    import pathlib

    fixture = pathlib.Path(__file__).parent / "fixtures" / "sample.pdf"
    pdf_bytes = fixture.read_bytes()

    with _mock_generate_scenario_empty():
        resp = await upload_client.post(
            "/api/v1/upload",
            files={"files": ("sample.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
            data={"session_id": "sess-fail"},
        )

    assert resp.status_code in (200, 207), resp.text
    body = resp.json()
    assert body["scenario_generated"] is False
    assert body["scenario"] is None
    # docs_text should still be saved
    docs_calls = [
        c for c in mock_redis.set.call_args_list if "docs" in str(c.args[0])
    ]
    assert len(docs_calls) >= 1
