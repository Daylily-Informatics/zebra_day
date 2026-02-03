#!/usr/bin/env python3
"""
Capture screenshots of the zebra_day web UI using Playwright.

Usage:
    # Install playwright first
    pip install playwright
    playwright install chromium

    # Start the zebra_day server
    zday gui start

    # Run this script (auto-detects http/https)
    python scripts/capture_screenshots.py

    # Or specify URL explicitly
    python scripts/capture_screenshots.py --url http://localhost:8118

    # Screenshots will be saved to zebra_day/imgs/
"""

import argparse
import sys
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("Error: playwright not installed. Run:")
    print("  pip install playwright")
    print("  playwright install chromium")
    sys.exit(1)


def detect_server_url(host: str = "localhost", port: int = 8118) -> str | None:
    """Auto-detect whether server is running on HTTP or HTTPS."""
    import ssl
    import urllib.error

    # Try HTTPS first
    for protocol in ["https", "http"]:
        url = f"{protocol}://{host}:{port}/healthz"
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=2, context=ctx) as resp:
                if resp.status == 200:
                    return f"{protocol}://{host}:{port}"
        except (urllib.error.URLError, TimeoutError, OSError):
            continue
    return None


# Pages to capture
PAGES = [
    {"name": "dashboard", "path": "/", "wait_for": ".stat-card"},
    {"name": "printers", "path": "/printers", "wait_for": ".card"},
    {"name": "print_request", "path": "/print", "wait_for": "form"},
    {"name": "templates", "path": "/templates", "wait_for": ".card"},
    {"name": "config", "path": "/config", "wait_for": ".card"},
    {"name": "api_docs", "path": "/docs", "wait_for": ".swagger-ui"},
]


def capture_screenshots(
    base_url: str = "https://localhost:8118",
    output_dir: Path = Path("zebra_day/imgs"),
    viewport_width: int = 1280,
    viewport_height: int = 800,
    prefix: str = "ui_",
) -> list[Path]:
    """Capture screenshots of all UI pages.

    Args:
        base_url: The base URL of the zebra_day server
        output_dir: Directory to save screenshots
        viewport_width: Browser viewport width
        viewport_height: Browser viewport height
        prefix: Prefix for screenshot filenames

    Returns:
        List of paths to saved screenshots
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    saved_files: list[Path] = []

    with sync_playwright() as p:
        # Launch browser - ignore HTTPS errors for local dev certs
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": viewport_width, "height": viewport_height},
            ignore_https_errors=True,
        )
        page = context.new_page()

        for page_info in PAGES:
            url = f"{base_url}{page_info['path']}"
            output_path = output_dir / f"{prefix}{page_info['name']}.png"

            print(f"Capturing {page_info['name']}... ", end="", flush=True)

            try:
                page.goto(url, wait_until="networkidle", timeout=30000)

                # Wait for key element to be visible
                if page_info.get("wait_for"):
                    try:
                        page.wait_for_selector(page_info["wait_for"], timeout=5000, state="visible")
                    except Exception:
                        pass  # Continue even if element not found

                # Small delay for any animations
                page.wait_for_timeout(500)

                # Capture screenshot
                page.screenshot(path=str(output_path), full_page=False)
                saved_files.append(output_path)
                print(f"saved to {output_path}")

            except Exception as e:
                print(f"FAILED: {e}")

        browser.close()

    return saved_files


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture screenshots of zebra_day web UI")
    parser.add_argument(
        "--url",
        default=None,
        help="Base URL of zebra_day server (auto-detects http/https if not specified)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("zebra_day/imgs"),
        help="Output directory for screenshots (default: zebra_day/imgs)",
    )
    parser.add_argument("--width", type=int, default=1280, help="Viewport width (default: 1280)")
    parser.add_argument("--height", type=int, default=800, help="Viewport height (default: 800)")
    parser.add_argument("--prefix", default="ui_", help="Filename prefix (default: ui_)")

    args = parser.parse_args()

    # Auto-detect URL if not specified
    base_url = args.url
    if not base_url:
        print("Detecting server...")
        base_url = detect_server_url()
        if not base_url:
            print("ERROR: Could not connect to zebra_day server on localhost:8118")
            print("Make sure the server is running: zday gui start")
            return 1

    print(f"Capturing screenshots from {base_url}")
    print(f"Output directory: {args.output_dir}")
    print()

    saved = capture_screenshots(
        base_url=base_url,
        output_dir=args.output_dir,
        viewport_width=args.width,
        viewport_height=args.height,
        prefix=args.prefix,
    )

    print(f"\nCaptured {len(saved)} screenshots")
    return 0 if saved else 1


if __name__ == "__main__":
    sys.exit(main())
