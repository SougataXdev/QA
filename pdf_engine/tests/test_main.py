"""
tests/test_main.py — FastAPI route tests.
"""

import pytest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from pdf_engine.main import app


@pytest.fixture
def client():
    return TestClient(app)


_VALID_PDF = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj

2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj

3 0 obj
<< /Type /Page /Parent 2 0 R
   /MediaBox [0 0 612 792]
   /Contents 4 0 R
   /Resources << /Font << /F1 5 0 R >> >> >>
endobj

4 0 obj
<< /Length 44 >>
stream
BT /F1 12 Tf 100 700 Td (Hello World) Tj ET
endstream
endobj

5 0 obj
<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>
endobj

xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000296 00000 n 
0000000390 00000 n 

trailer << /Size 6 /Root 1 0 R >>
startxref
470
%%EOF"""


class TestHealthEndpoint:
    """Health check endpoint tests."""

    def test_health_returns_200(self, client):
        """Happy path: health endpoint returns 200."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["version"] == "1.0.0"


class TestProcessEndpoint:
    """Process endpoint tests."""

    def test_empty_file_returns_400(self, client):
        """Failure case: empty file → 400."""
        response = client.post(
            "/process",
            files={"file": ("test.pdf", b"", "application/pdf")},
            params={"url": "https://example.com"},
        )
        assert response.status_code == 400

    def test_invalid_file_returns_400(self, client):
        """Failure case: non-PDF file → 400."""
        response = client.post(
            "/process",
            files={"file": ("test.txt", b"hello world", "text/plain")},
            params={"url": "https://example.com"},
        )
        assert response.status_code == 400

    def test_invalid_crop_returns_400(self, client):
        """Failure case: crop_top >= crop_bottom → 400."""
        response = client.post(
            "/process",
            files={"file": ("test.pdf", _VALID_PDF, "application/pdf")},
            params={
                "url": "https://example.com",
                "crop_top": 0.9,
                "crop_bottom": 0.1,
            },
        )
        assert response.status_code == 400


class TestJobsEndpoint:
    """Jobs endpoint tests."""

    def test_nonexistent_job_returns_404(self, client):
        """Failure case: non-existent job → 404."""
        # Mock Redis to return None (no job found)
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)

        with patch('pdf_engine.main._get_redis', return_value=mock_redis):
            response = client.get("/jobs/nonexistent-job-id")
            assert response.status_code == 404
