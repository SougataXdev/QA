"""
tests/test_worker.py — Worker pipeline tests.

Uses mocks for Redis and Playwright. Tests pipeline orchestration logic.
"""

from unittest.mock import AsyncMock, patch, MagicMock
import pytest
import json

from pdf_engine.worker import run_pipeline, set_status


# ── Minimal valid PDF for testing ──
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


class TestWorker:
    """Worker pipeline orchestration tests."""

    @pytest.mark.asyncio
    async def test_corrupted_pdf_fails_gracefully(self):
        """Failure case: corrupted PDF → FAILED status with CORRUPTED_PDF."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock()
        mock_redis.close = AsyncMock()

        with patch('pdf_engine.worker._get_redis', return_value=mock_redis):
            await run_pipeline(
                ctx={},
                job_id="test-job-123",
                file_bytes=b"not a pdf",
                url="https://example.com",
                crop_top=0.0,
                crop_bottom=1.0,
                crop_left=0.0,
                crop_right=1.0,
                page_start=0,
                page_end=-1,
            )

        # Last Redis set call should contain FAILED status
        last_call = mock_redis.set.call_args_list[-1]
        stored_data = json.loads(last_call[0][1])
        assert stored_data["status"] == "FAILED"
        assert "CORRUPTED_PDF" in stored_data["error"]

    @pytest.mark.asyncio
    async def test_invalid_page_range_fails(self):
        """Failure case: invalid page range → FAILED status."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock()
        mock_redis.close = AsyncMock()

        with patch('pdf_engine.worker._get_redis', return_value=mock_redis):
            await run_pipeline(
                ctx={},
                job_id="test-job-456",
                file_bytes=_VALID_PDF,
                url="https://example.com",
                crop_top=0.0,
                crop_bottom=1.0,
                crop_left=0.0,
                crop_right=1.0,
                page_start=5,  # beyond page count
                page_end=3,    # end < start
            )

        last_call = mock_redis.set.call_args_list[-1]
        stored_data = json.loads(last_call[0][1])
        assert stored_data["status"] == "FAILED"

    def test_set_status_is_async(self):
        """Structural: set_status is an async function."""
        import asyncio
        assert asyncio.iscoroutinefunction(set_status)
