"""
tests/test_preflight.py — Preflight validation tests.
"""

import pytest
from pdf_engine.pipeline.preflight import run_preflight


# ── Helper: generate a minimal valid PDF with text ──
def _make_simple_pdf() -> bytes:
    """Generate a minimal PDF with extractable text using reportlab-free approach."""
    # Minimal PDF spec: single page with a text stream
    content = b"""%PDF-1.4
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
    return content


def _make_empty_pdf() -> bytes:
    """Generate a minimal PDF with NO text content (image-only simulation)."""
    content = b"""%PDF-1.4
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
   /Resources << >> >>
endobj

4 0 obj
<< /Length 0 >>
stream

endstream
endobj

xref
0 5
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000263 00000 n 

trailer << /Size 5 /Root 1 0 R >>
startxref
313
%%EOF"""
    return content


class TestPreflight:
    """Preflight validation test suite."""

    def test_valid_pdf_passes(self):
        """Happy path: valid PDF with text layer passes preflight."""
        result = run_preflight(_make_simple_pdf())
        assert result["has_text_layer"] is True
        assert result["page_count"] >= 1

    def test_corrupted_pdf_raises(self):
        """Failure case: garbage bytes should raise CORRUPTED_PDF."""
        with pytest.raises(ValueError, match="CORRUPTED_PDF"):
            run_preflight(b"this is not a pdf")

    def test_empty_bytes_raises(self):
        """Edge case: empty bytes should raise CORRUPTED_PDF."""
        with pytest.raises(ValueError, match="CORRUPTED_PDF"):
            run_preflight(b"")

    def test_no_text_layer_raises(self):
        """Failure case: PDF with no text content raises NO_TEXT_LAYER."""
        with pytest.raises(ValueError, match="NO_TEXT_LAYER"):
            run_preflight(_make_empty_pdf())
