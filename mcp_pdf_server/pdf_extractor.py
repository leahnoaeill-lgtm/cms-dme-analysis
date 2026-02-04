#!/usr/bin/env python3
"""
PDF Text Extractor for Claude Code

A standalone script to extract text from PDFs and search for specific terms.
Can be called via Bash to enable Claude to read PDF documents.

Usage:
    # Extract all text from a PDF URL
    python3 pdf_extractor.py extract "https://example.com/policy.pdf"

    # Search for a term in a PDF
    python3 pdf_extractor.py search "https://example.com/policy.pdf" "E0469"

    # Extract from local file
    python3 pdf_extractor.py extract "/path/to/file.pdf"
"""

import sys
import os
import ssl
import tempfile
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

# Create SSL context that doesn't verify certificates (for corporate/self-signed certs)
SSL_CONTEXT = ssl.create_default_context()
SSL_CONTEXT.check_hostname = False
SSL_CONTEXT.verify_mode = ssl.CERT_NONE

try:
    import fitz  # PyMuPDF
except ImportError:
    print("ERROR: PyMuPDF not installed. Run: pip3 install PyMuPDF")
    sys.exit(1)

# User agent to avoid blocks
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def download_pdf(url: str) -> bytes:
    """Download PDF from URL and return bytes."""
    request = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=30, context=SSL_CONTEXT) as response:
            return response.read()
    except HTTPError as e:
        raise Exception(f"HTTP Error {e.code}: {e.reason}")
    except URLError as e:
        raise Exception(f"URL Error: {e.reason}")


def extract_text_from_pdf(source: str, max_pages: int = None) -> str:
    """Extract text from PDF (URL or local path)."""

    # Determine if URL or local file
    if source.startswith(('http://', 'https://')):
        pdf_bytes = download_pdf(source)
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    else:
        if not os.path.exists(source):
            raise Exception(f"File not found: {source}")
        doc = fitz.open(source)

    text_parts = []
    pages_to_process = doc.page_count
    if max_pages:
        pages_to_process = min(max_pages, doc.page_count)

    for page_num in range(pages_to_process):
        page = doc[page_num]
        page_text = page.get_text()
        if page_text.strip():
            text_parts.append(f"--- Page {page_num + 1} of {doc.page_count} ---\n{page_text}")

    doc.close()
    return "\n\n".join(text_parts)


def search_pdf_for_term(source: str, term: str, context_chars: int = 500) -> str:
    """Search PDF for a term and return matches with context."""

    # Extract full text
    full_text = extract_text_from_pdf(source)

    if not full_text.strip():
        return f"PDF contains no readable text (may be scanned images).\nSource: {source}"

    # Search for term (case-insensitive)
    term_lower = term.lower()
    text_lower = full_text.lower()

    matches = []
    start = 0

    while True:
        pos = text_lower.find(term_lower, start)
        if pos == -1:
            break

        # Get context around the match
        context_start = max(0, pos - context_chars)
        context_end = min(len(full_text), pos + len(term) + context_chars)

        # Extend to line boundaries for cleaner context
        while context_start > 0 and full_text[context_start] != '\n':
            context_start -= 1
        while context_end < len(full_text) and full_text[context_end] != '\n':
            context_end += 1

        context = full_text[context_start:context_end].strip()
        matches.append({
            "position": pos,
            "context": context
        })

        start = pos + 1

    # Format results
    if not matches:
        return f"Term '{term}' NOT FOUND in PDF.\nSource: {source}\n\nThe PDF was successfully read but does not contain this term."

    result_parts = [
        f"FOUND {len(matches)} match(es) for '{term}'",
        f"Source: {source}",
        ""
    ]

    for i, match in enumerate(matches, 1):
        result_parts.append(f"{'='*60}")
        result_parts.append(f"MATCH {i} (character position {match['position']})")
        result_parts.append(f"{'='*60}")
        result_parts.append(match['context'])
        result_parts.append("")

    return "\n".join(result_parts)


def print_usage():
    """Print usage instructions."""
    print("""
PDF Text Extractor for Claude Code
==================================

Usage:
    python3 pdf_extractor.py extract <url_or_path> [max_pages]
    python3 pdf_extractor.py search <url_or_path> <term> [context_chars]

Commands:
    extract  - Extract all text from a PDF
    search   - Search for a specific term and show context

Examples:
    # Extract text from URL
    python3 pdf_extractor.py extract "https://example.com/policy.pdf"

    # Extract only first 5 pages
    python3 pdf_extractor.py extract "https://example.com/policy.pdf" 5

    # Search for E0469 in a PDF
    python3 pdf_extractor.py search "https://example.com/policy.pdf" "E0469"

    # Search with more context (1000 chars around each match)
    python3 pdf_extractor.py search "https://example.com/policy.pdf" "E0469" 1000
""")


def main():
    if len(sys.argv) < 3:
        print_usage()
        sys.exit(1)

    command = sys.argv[1].lower()
    source = sys.argv[2]

    try:
        if command == "extract":
            max_pages = int(sys.argv[3]) if len(sys.argv) > 3 else None
            text = extract_text_from_pdf(source, max_pages)
            if text.strip():
                print(f"PDF Text Extracted from: {source}\n")
                print(text)
            else:
                print(f"PDF contains no readable text (may be scanned images).\nSource: {source}")

        elif command == "search":
            if len(sys.argv) < 4:
                print("ERROR: Search requires a term. Usage: search <url_or_path> <term>")
                sys.exit(1)
            term = sys.argv[3]
            context_chars = int(sys.argv[4]) if len(sys.argv) > 4 else 500
            result = search_pdf_for_term(source, term, context_chars)
            print(result)

        else:
            print(f"Unknown command: {command}")
            print_usage()
            sys.exit(1)

    except Exception as e:
        print(f"ERROR: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
