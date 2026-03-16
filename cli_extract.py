#!/usr/bin/env python3
"""
CLI wrapper for PDF extraction.

Reads all PDFs from ./pdf/ and writes extracted text to ./output/.
Each PDF produces a matching .txt file: ./output/<stem>.txt

Usage:
    python3 cli_extract.py
"""

import os
import sys
import logging

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

PDF_DIR = os.path.join(os.path.dirname(__file__), "pdf")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")


def main() -> None:
    if not os.path.isdir(PDF_DIR):
        print(f"✗ PDF folder not found: {PDF_DIR}")
        sys.exit(1)

    pdf_files = sorted(
        f for f in os.listdir(PDF_DIR) if f.lower().endswith(".pdf")
    )

    if not pdf_files:
        print(f"✗ No PDF files found in {PDF_DIR}")
        sys.exit(1)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Import here so the script can give a clear error if deps are missing
    from pdf_engine.extractor.measure import measure_pdf
    from pdf_engine.extractor.extract import extract_pdf

    print(f"Found {len(pdf_files)} PDF(s) in {PDF_DIR}\n")

    success = 0
    failed = 0

    for filename in pdf_files:
        pdf_path = os.path.join(PDF_DIR, filename)
        stem = os.path.splitext(filename)[0]

        print(f"Processing: {filename}")

        try:
            # Phase 1: measure
            report = measure_pdf(pdf_path)

            # Phase 2: extract — writes to OUTPUT_DIR/input.txt
            with open(pdf_path, "rb") as f:
                pdf_bytes = f.read()

            _, _ = extract_pdf(pdf_bytes, OUTPUT_DIR, report=report)

            # Rename from the hardcoded 'input.txt' to the real stem
            src = os.path.join(OUTPUT_DIR, "input.txt")
            dst = os.path.join(OUTPUT_DIR, f"{stem}.txt")
            if os.path.exists(src):
                if os.path.exists(dst):
                    os.remove(dst)
                os.rename(src, dst)
                print(f"  → {OUTPUT_DIR}/{stem}.txt\n")
            else:
                print(f"  ⚠ Output file not written for {filename}\n")

            success += 1

        except Exception as exc:
            print(f"  ✗ Failed: {exc}\n")
            failed += 1

    print(f"Done. {success} succeeded, {failed} failed.")
    print(f"Output folder: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
