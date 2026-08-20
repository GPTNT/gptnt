"""Playwright assembly of resolved HTML manuals through KtaneContent's merger."""

from __future__ import annotations

import contextlib
import functools
import json
import threading
from http import HTTPStatus, server as http_server
from importlib import metadata
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, override
from urllib.parse import unquote, urlparse

import playwright
import pymupdf
from playwright.sync_api import Error as PlaywrightError, Frame, Page, Route, sync_playwright

from gptnt.ktane.manuals._compiler_sources import KTANE_CONTENT_COMMIT, keypad_assets_identity
from gptnt.ktane.manuals._javascript import load_javascript
from gptnt.ktane.manuals.resolution import (
    ResolvedKtaneContentAppendix,
    ResolvedKtaneContentModule,
    ResolvedLocalDocument,
)

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from playwright.sync_api import Browser, Playwright

type HtmlDocument = (
    ResolvedKtaneContentModule | ResolvedKtaneContentAppendix | ResolvedLocalDocument
)

_MERGER_PATH = "More/Manual%20Merger/index.html"
_KEYPAD_URL_PREFIX = "/HTML/img/Keypad/"
_BROWSER_INSTALL_COMMAND = "uv run playwright install chromium"
_PRINT_LAYOUT_REVISION = "ordered-flattened-merger-print-4"


class ManualBrowserError(RuntimeError):
    """The browser could not render or validate selected manual HTML."""


class _RequestHandler(http_server.SimpleHTTPRequestHandler):
    """Serve one KtaneContent checkout plus isolated local document roots."""

    local_documents: ClassVar[dict[str, Path]] = {}

    @override
    # The private loopback server deliberately has no request log sink.
    def log_message(self, format: str, *args: object) -> None:
        _ = format, args

    @override
    def do_GET(self) -> None:
        request_path = unquote(urlparse(self.path).path)
        source = self.local_documents.get(request_path)
        if source is not None:
            location = f"/gptnt-local/{request_path.removeprefix('/HTML/').removesuffix('.html')}/"
            self.send_response(HTTPStatus.FOUND)
            self.send_header("Location", f"{location}{source.name}")
            self.end_headers()
            return
        super().do_GET()

    @override
    def translate_path(self, path: str) -> str:
        request_path = unquote(urlparse(path).path)
        prefix = "/gptnt-local/"
        if request_path.startswith(prefix):
            token, separator, relative = request_path.removeprefix(prefix).partition("/")
            source = self.local_documents.get(f"/HTML/{token}.html")
            if separator and source is not None:
                candidate = (source.parent / relative).resolve()
                if candidate.is_relative_to(source.parent.resolve()):
                    return str(candidate)
        return super().translate_path(path)


class _LoopbackServer(http_server.ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


@contextlib.contextmanager
def _serve(source_root: Path, *, local_documents: dict[str, Path]) -> Iterator[str]:
    handler_type = type(
        "ManualRequestHandler", (_RequestHandler,), {"local_documents": local_documents}
    )
    request_handler = functools.partial(handler_type, directory=str(source_root))
    server = _LoopbackServer(("127.0.0.1", 0), request_handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = int(server.server_address[1])
    # Generator exit must trigger all three ordered server shutdown operations.
    try:  # noqa: WPS243
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def browser_renderer_identity() -> dict[str, str]:
    """Return the package and managed-browser revision used for cache identity."""
    browsers_path = Path(playwright.__file__).parent / "driver" / "package" / "browsers.json"
    browsers = json.loads(browsers_path.read_text(encoding="utf-8"))["browsers"]
    chromium = next(browser for browser in browsers if browser["name"] == "chromium")
    return {
        "assembly": f"KtaneContent Manual Merger at {KTANE_CONTENT_COMMIT}",
        "print_layout_revision": _PRINT_LAYOUT_REVISION,
        "playwright": metadata.version("playwright"),
        "chromium_revision": str(chromium["revision"]),
        "keypad_assets": f"committed-sha256:{keypad_assets_identity()}",
    }


def _catalog_entry(document: HtmlDocument, *, index: int) -> tuple[dict[str, str], str]:
    token = f"gptnt-{index:04d}"
    filename = token if isinstance(document, ResolvedLocalDocument) else document.source_path.stem
    return (
        {
            "ModuleID": token,
            "Name": document.document_id,
            "FileName": filename,
            "SortKey": f"{index:08d}",
        },
        token,
    )


def _configure_routes(
    page: Page,
    *,
    catalog: list[dict[str, str]],
    keypad_root: Path,
    blocked_urls: list[str],
    missing_keypad_assets: set[str],
) -> None:
    symbols_dir = keypad_root

    # This callback closes over the state for one isolated browser render.
    def handle_route(route: Route) -> None:  # noqa: WPS430
        parsed = urlparse(route.request.url)
        if parsed.path == "/json/raw":
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"KtaneModules": catalog}),
            )
            return
        if parsed.path.startswith(_KEYPAD_URL_PREFIX):
            filename = unquote(parsed.path.removeprefix(_KEYPAD_URL_PREFIX))
            asset_path = symbols_dir / filename
            if asset_path.is_file():
                route.fulfill(status=200, content_type="image/png", body=asset_path.read_bytes())
            else:
                missing_keypad_assets.add(filename)
                route.abort("failed")
            return
        if parsed.scheme in {"about", "blob", "data"} or parsed.hostname == "127.0.0.1":
            route.continue_()
            return
        blocked_urls.append(route.request.url)
        route.abort("blockedbyclient")

    _ = page.route("**/*", handle_route)


def _wait_for_document(frame: Frame) -> tuple[int, list[str]]:
    _ = frame.wait_for_function(load_javascript("fonts-loaded.js"))
    _ = frame.wait_for_function(load_javascript("images-complete.js"))
    broken_images = frame.evaluate(load_javascript("broken-images.js"))
    page_count = frame.locator(".section > .page").count()
    if page_count == 0:
        raise ManualBrowserError(f"manual HTML produced no printable pages: {frame.url}")
    return page_count, broken_images


def _launch_browser(playwright: Playwright) -> Browser:
    try:
        return playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-background-networking",
                "--disable-component-update",
                "--disable-default-apps",
                "--disable-extensions",
                "--disable-sync",
                "--metrics-recording-only",
                "--no-first-run",
                "--safebrowsing-disable-auto-update",
            ],
        )
    except PlaywrightError as error:
        if "executable doesn't exist" in str(error).casefold():
            raise ManualBrowserError(
                f"Playwright-managed Chromium is not installed. Run `{_BROWSER_INSTALL_COMMAND}`."
            ) from error
        raise


def _clean_print_document(frame: Frame) -> None:
    frame.evaluate(load_javascript("clean-print-document.js"))


# One check reports four distinct browser failure categories with category-specific messages.
def _raise_render_errors(  # noqa: WPS238
    *,
    broken_images: list[str],
    blocked_urls: list[str],
    page_errors: list[str],
    missing_keypad_assets: set[str],
) -> None:
    if missing_keypad_assets:
        raise ManualBrowserError(
            f"High-resolution Keypad assets are unavailable: {sorted(missing_keypad_assets)}"
        )
    if broken_images:
        raise ManualBrowserError(f"manual HTML contains broken images: {broken_images}")
    if blocked_urls:
        raise ManualBrowserError(f"manual HTML attempted non-loopback requests: {blocked_urls}")
    if page_errors:
        raise ManualBrowserError(f"manual HTML raised JavaScript errors: {page_errors}")


def _flatten_document(frame: Frame) -> tuple[tuple[str, ...], str]:
    flattened = frame.evaluate(load_javascript("flatten-document.js"))
    if not isinstance(flattened, dict):
        raise ManualBrowserError(f"manual HTML could not be flattened for print: {frame.url}")
    head = flattened.get("head")
    sections = flattened.get("sections")
    if (
        not isinstance(head, list)
        or not all(isinstance(element, str) for element in head)
        or not isinstance(sections, str)
        or not sections
    ):
        raise ManualBrowserError(f"manual HTML has no printable sections: {frame.url}")
    return tuple(head), sections


def _print_documents(
    page: Page,
    *,
    documents: Sequence[tuple[Sequence[str], str]],
    page_counts: Sequence[int],
    output_pdf: Path,
) -> list[str]:
    head = "\n".join(
        dict.fromkeys(element for document_head, _ in documents for element in document_head)
    )
    sections = "\n".join(document_sections for _, document_sections in documents)
    page.set_content(
        f"<!doctype html><html><head>{head}"
        "<style>html,body{margin:0;padding:0}</style></head>"
        f"<body>{sections}</body></html>",
        wait_until="networkidle",
        timeout=30_000,
    )
    actual_pages, broken_images = _wait_for_document(page.main_frame)
    expected_pages = sum(page_counts)
    if actual_pages != expected_pages:
        raise ManualBrowserError(
            f"flattened manual contains {actual_pages} pages; expected {expected_pages}"
        )
    _ = page.pdf(
        path=str(output_pdf),
        format="Letter",
        print_background=True,
        display_header_footer=False,
        prefer_css_page_size=False,
        page_ranges=f"1-{expected_pages}",
        margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
    )
    with pymupdf.open(output_pdf) as printed_document:
        if printed_document.page_count != expected_pages:
            raise ManualBrowserError(
                f"Chromium printed {printed_document.page_count} pages; expected {expected_pages}"
            )
    return broken_images


# This boundary owns one server/browser/print lifecycle and its accumulated validation state.
def render_html(  # noqa: WPS210,WPS213,WPS231
    documents: Sequence[HtmlDocument], *, source_root: Path, keypad_root: Path, output_pdf: Path
) -> tuple[int, ...]:
    """Render ordered HTML documents with the pinned merger and managed Chromium."""
    merger = source_root / "More" / "Manual Merger" / "index.html"
    if not merger.is_file():
        raise ManualBrowserError(f"pinned Manual Merger is missing at {merger}")

    catalog_and_tokens = [
        _catalog_entry(document, index=index) for index, document in enumerate(documents)
    ]
    catalog = [entry for entry, _ in catalog_and_tokens]
    tokens = [token for _, token in catalog_and_tokens]
    local_documents = {
        f"/HTML/{token}.html": document.source_path
        for document, token in zip(documents, tokens, strict=True)
        if isinstance(document, ResolvedLocalDocument)
    }
    profile = {"EnabledList": tokens, "Operation": 1}
    blocked_urls: list[str] = []
    page_errors: list[str] = []
    missing_keypad_assets: set[str] = set()

    # Keep the loopback server alive while Playwright starts and shuts down its driver process.
    # Separate contexts keep server shutdown outside the Playwright driver shutdown.
    with _serve(source_root, local_documents=local_documents) as base_url:  # noqa: SIM117
        with sync_playwright() as playwright:
            browser = _launch_browser(playwright)
            # Chromium must close after every rendering or validation failure.
            try:  # noqa: WPS229,WPS501
                page = browser.new_page(viewport={"width": 1280, "height": 960})
                _configure_routes(
                    page,
                    catalog=catalog,
                    keypad_root=keypad_root,
                    blocked_urls=blocked_urls,
                    missing_keypad_assets=missing_keypad_assets,
                )
                page.on("pageerror", lambda error: page_errors.append(str(error)))
                _ = page.goto(
                    f"{base_url}/{_MERGER_PATH}", wait_until="networkidle", timeout=30_000
                )
                with page.expect_file_chooser() as choice:
                    page.get_by_role("button", name="Upload profile").click()
                # Playwright publishes the chooser only after its context exits.
                file_chooser = choice.value  # noqa: WPS441
                file_chooser.set_files(
                    {
                        "name": "Bomb Defusal Manual.json",
                        "mimeType": "application/json",
                        "buffer": json.dumps(profile).encode(),
                    }
                )
                _ = page.wait_for_function(
                    load_javascript("manual-frames-loaded.js"), arg=len(documents)
                )

                page_counts: list[int] = []
                flattened_documents: list[tuple[tuple[str, ...], str]] = []
                broken_images: list[str] = []
                for index, document in enumerate(documents):
                    frame_element = page.locator(".manuals > iframe").nth(index).element_handle()
                    frame = frame_element.content_frame()
                    if frame is None:
                        # Browser traversal nests lifecycle, document, and frame checks.
                        raise ManualBrowserError(  # noqa: WPS220
                            f"Manual Merger frame for {document.document_id} is unavailable"
                        )
                    page_count, frame_broken = _wait_for_document(frame)
                    page_counts.append(page_count)
                    broken_images.extend(frame_broken)
                    _clean_print_document(frame)
                    flattened_documents.append(_flatten_document(frame))

                _raise_render_errors(
                    broken_images=broken_images,
                    blocked_urls=blocked_urls,
                    page_errors=page_errors,
                    missing_keypad_assets=missing_keypad_assets,
                )
                flattened_broken_images = _print_documents(
                    page,
                    documents=flattened_documents,
                    page_counts=page_counts,
                    output_pdf=output_pdf,
                )
                _raise_render_errors(
                    broken_images=flattened_broken_images,
                    blocked_urls=blocked_urls,
                    page_errors=page_errors,
                    missing_keypad_assets=missing_keypad_assets,
                )
            finally:
                browser.close()

    return tuple(page_counts)
