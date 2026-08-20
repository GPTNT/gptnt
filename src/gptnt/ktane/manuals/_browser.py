"""Playwright assembly of resolved HTML manuals through KtaneContent's merger."""

from __future__ import annotations

import contextlib
import functools
import json
import threading
from http import HTTPStatus, server as http_server
from importlib import metadata
from importlib.resources import files
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, override
from urllib.parse import unquote, urlparse

import playwright
import pymupdf
from playwright.sync_api import Error as PlaywrightError, Frame, Page, Route, sync_playwright

from gptnt.ktane.manuals.compiler_sources import KTANE_CONTENT_COMMIT, keypad_assets_identity
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
type FlattenedDocument = tuple[tuple[str, ...], str]
type FlattenedFrames = tuple[list[int], list[FlattenedDocument], list[str]]

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
        """Discard request logs from the short-lived private compilation server."""
        _ = format, args

    @override
    def do_GET(self) -> None:
        """Redirect synthetic merger URLs to their isolated local-document roots."""
        request_path = unquote(urlparse(self.path).path)
        source = self.local_documents.get(request_path)
        if source is not None:
            # Each local document gets its own URL directory so relative assets resolve beside it.
            location = f"/gptnt-local/{request_path.removeprefix('/HTML/').removesuffix('.html')}/"
            self.send_response(HTTPStatus.FOUND)
            self.send_header("Location", f"{location}{source.name}")
            self.end_headers()
            return
        super().do_GET()

    @override
    def translate_path(self, path: str) -> str:
        """Map isolated local URLs to disk without allowing parent-directory traversal."""
        request_path = unquote(urlparse(path).path)
        prefix = "/gptnt-local/"
        if request_path.startswith(prefix):
            token, separator, relative = request_path.removeprefix(prefix).partition("/")
            source = self.local_documents.get(f"/HTML/{token}.html")
            if separator and source is not None:
                candidate = (source.parent / relative).resolve()
                # Relative assets may stay within the document directory but cannot escape it.
                if candidate.is_relative_to(source.parent.resolve()):
                    return str(candidate)
        return super().translate_path(path)


class _LoopbackServer(http_server.ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


@contextlib.contextmanager
def _serve(source_root: Path, *, local_documents: dict[str, Path]) -> Iterator[str]:
    """Serve pinned and local manual files on an ephemeral loopback port."""
    # A distinct handler subclass keeps one render's local-document map out of global state.
    handler_type = type(
        "ManualRequestHandler", (_RequestHandler,), {"local_documents": local_documents}
    )
    request_handler = functools.partial(handler_type, directory=str(source_root))

    # Run the blocking stdlib server beside synchronous Playwright on the calling thread.
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
    # Playwright's package records the exact managed Chromium revision independently of its own
    # version, so both values participate in artifact invalidation.
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
    """Build one merger catalog record and its collision-free synthetic module token."""
    # Synthetic IDs prevent duplicate module selections from collapsing in the upstream merger.
    token = f"gptnt-{index:04d}"
    # Local documents are exposed through the token; pinned documents retain upstream filenames.
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


@functools.cache
def _load_javascript(name: str) -> str:
    """Read and cache one packaged browser expression by filename."""
    # importlib.resources works for both editable source trees and installed wheels.
    return files("gptnt.ktane.manuals").joinpath("_js", name).read_text(encoding="utf-8")


def _wait_for_document(frame: Frame) -> tuple[int, list[str]]:
    """Wait for stable font/image state and return printable and broken-image counts."""
    # A loaded frame is not printable until font substitution and image decoding have settled.
    _ = frame.wait_for_function(_load_javascript("fonts-loaded.js"))
    _ = frame.wait_for_function(_load_javascript("images-complete.js"))
    broken_images = frame.evaluate(_load_javascript("broken-images.js"))
    page_count = frame.locator(".section > .page").count()
    if page_count == 0:
        raise ManualBrowserError(f"manual HTML produced no printable pages: {frame.url}")
    return page_count, broken_images


def _launch_browser(playwright: Playwright) -> Browser:
    """Launch managed Chromium with background network services disabled."""
    try:
        # Disable browser services that could make compilation depend on external network state.
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
        # Convert the common setup failure into an actionable compiler message.
        if "executable doesn't exist" in str(error).casefold():
            raise ManualBrowserError(
                f"Playwright-managed Chromium is not installed. Run `{_BROWSER_INSTALL_COMMAND}`."
            ) from error
        raise


@contextlib.contextmanager
def _managed_browser(playwright: Playwright) -> Iterator[Browser]:
    """Launch Chromium and guarantee that it closes before Playwright shuts down."""
    browser = _launch_browser(playwright)
    try:
        yield browser
    finally:
        browser.close()


def _clean_print_document(frame: Frame) -> None:
    """Remove merger-only rule-seed chrome from one printable document frame."""
    frame.evaluate(_load_javascript("clean-print-document.js"))


def _flatten_document(frame: Frame) -> tuple[tuple[str, ...], str]:
    """Clone one rendered frame into self-contained head and section HTML fragments."""
    flattened = frame.evaluate(_load_javascript("flatten-document.js"))
    # Playwright values cross a dynamic JSON boundary, so validate the expected result shape.
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
    """Print flattened documents as one PDF and return any broken image URLs."""
    # Stylesheet order is significant, but identical head fragments need appear only once.
    head = "\n".join(
        dict.fromkeys(element for document_head, _ in documents for element in document_head)
    )
    sections = "\n".join(document_sections for _, document_sections in documents)
    # Printing one flat page tree avoids Chromium iframe pagination and PDF form-object issues.
    page.set_content(
        f"<!doctype html><html><head>{head}"
        "<style>html,body{margin:0;padding:0}</style></head>"
        f"<body>{sections}</body></html>",
        wait_until="networkidle",
        timeout=30_000,
    )
    actual_pages, broken_images = _wait_for_document(page.main_frame)
    expected_pages = sum(page_counts)
    # A count mismatch means flattening changed the accepted source pagination.
    if actual_pages != expected_pages:
        raise ManualBrowserError(
            f"flattened manual contains {actual_pages} pages; expected {expected_pages}"
        )
    # US Letter and zero margins match the dimensions already encoded by the manual page CSS.
    _ = page.pdf(
        path=str(output_pdf),
        format="Letter",
        print_background=True,
        display_header_footer=False,
        prefer_css_page_size=False,
        page_ranges=f"1-{expected_pages}",
        margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
    )
    # Reopen the file through the downstream PDF library before allowing assembly to continue.
    with pymupdf.open(output_pdf) as printed_document:
        if printed_document.page_count != expected_pages:
            raise ManualBrowserError(
                f"Chromium printed {printed_document.page_count} pages; expected {expected_pages}"
            )
    return broken_images


class _ManualRenderer:
    """Own one manual render's selection, browser state, failures, and output path."""

    def __init__(
        self,
        documents: Sequence[HtmlDocument],
        *,
        source_root: Path,
        keypad_root: Path,
        output_pdf: Path,
    ) -> None:
        """Prepare stable merger selection and empty validation state for one render."""
        self._documents = tuple(documents)
        self._source_root = source_root
        self._keypad_root = keypad_root
        self._output_pdf = output_pdf

        # Catalog SortKeys and synthetic tokens preserve every occurrence in resolver order.
        catalog_and_tokens = [
            _catalog_entry(document, index=index) for index, document in enumerate(self._documents)
        ]
        self._catalog = [entry for entry, _ in catalog_and_tokens]
        self._tokens = [token for _, token in catalog_and_tokens]

        # Only local documents require synthetic URL-to-disk mappings in the request handler.
        self._local_documents = {
            f"/HTML/{token}.html": document.source_path
            for document, token in zip(self._documents, self._tokens, strict=True)
            if isinstance(document, ResolvedLocalDocument)
        }

        # Route and page callbacks accumulate failures until asynchronous loading has settled.
        self._blocked_urls: list[str] = []
        self._page_errors: list[str] = []
        self._missing_keypad_assets: set[str] = set()
        self._compiler_origin: tuple[str, str] | None = None

    def render(self) -> tuple[int, ...]:
        """Render the prepared selection through the pinned merger and managed Chromium."""
        # Fail before browser startup when source preparation did not materialize the merger.
        merger = self._source_root / "More" / "Manual Merger" / "index.html"
        if not merger.is_file():
            raise ManualBrowserError(f"pinned Manual Merger is missing at {merger}")

        # Reverse context exit closes Chromium, then Playwright, then the loopback server.
        with (
            _serve(self._source_root, local_documents=self._local_documents) as base_url,
            sync_playwright() as playwright,
            _managed_browser(playwright) as browser,
        ):
            return self._render_in_browser(browser, base_url=base_url)

    def _handle_route(self, route: Route) -> None:
        """Resolve one request under the merger's exact-origin network policy."""
        parsed = urlparse(route.request.url)
        is_compiler_origin = self._compiler_origin == (parsed.scheme, parsed.netloc)

        # Only the private compiler origin may use the synthetic catalog endpoint.
        if is_compiler_origin and parsed.path == "/json/raw":
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"KtaneModules": self._catalog}),
            )
            return

        # Only compiler-origin Keypad requests receive committed high-resolution assets.
        if is_compiler_origin and parsed.path.startswith(_KEYPAD_URL_PREFIX):
            filename = unquote(parsed.path.removeprefix(_KEYPAD_URL_PREFIX))
            asset_path = self._keypad_root / filename
            if asset_path.is_file():
                route.fulfill(status=200, content_type="image/png", body=asset_path.read_bytes())
            else:
                self._missing_keypad_assets.add(filename)
                route.abort("failed")
            return

        # Browser-internal URLs and this compiler server are the complete request surface.
        if parsed.scheme in {"about", "blob", "data"} or is_compiler_origin:
            route.continue_()
            return

        self._blocked_urls.append(route.request.url)
        route.abort("blockedbyclient")

    def _record_page_error(self, error: PlaywrightError) -> None:
        """Record one uncaught page exception for validation after loading settles."""
        self._page_errors.append(str(error))

    def _new_page(self, browser: Browser) -> Page:
        """Create a browser page with the isolated route and error callbacks attached."""
        page = browser.new_page(viewport={"width": 1280, "height": 960})
        _ = page.route("**/*", self._handle_route)
        page.on("pageerror", self._record_page_error)
        return page

    def _load_merger(self, page: Page, *, base_url: str) -> None:
        """Load the merger and submit the ordered in-memory selection profile."""
        _ = page.goto(f"{base_url}/{_MERGER_PATH}", wait_until="networkidle", timeout=30_000)

        # Operation 1 is the upstream merger's explicitly enabled module-list mode.
        profile = {"EnabledList": self._tokens, "Operation": 1}
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

        # Profile processing is complete once the merger has created one frame per token.
        _ = page.wait_for_function(
            _load_javascript("manual-frames-loaded.js"), arg=len(self._documents)
        )

    def _flatten_frames(self, page: Page) -> FlattenedFrames:
        """Validate and flatten each selected frame while preserving resolver order."""
        page_counts: list[int] = []
        flattened_documents: list[FlattenedDocument] = []
        broken_images: list[str] = []

        for index, document in enumerate(self._documents):
            frame_element = page.locator(".manuals > iframe").nth(index).element_handle()
            frame = frame_element.content_frame()
            if frame is None:
                raise ManualBrowserError(
                    f"Manual Merger frame for {document.document_id} is unavailable"
                )

            # Capture the rendered result before flattening strips executable scripts.
            page_count, frame_broken = _wait_for_document(frame)
            page_counts.append(page_count)
            broken_images.extend(frame_broken)
            _clean_print_document(frame)
            flattened_documents.append(_flatten_document(frame))

        return page_counts, flattened_documents, broken_images

    # One check reports four distinct browser failure categories with category-specific messages.
    def _raise_errors(self, *, broken_images: list[str]) -> None:  # noqa: WPS238
        """Raise the most actionable accumulated browser validation failure, if any."""
        # Asset failures take priority because broken images are often their consequence.
        if self._missing_keypad_assets:
            raise ManualBrowserError(
                "High-resolution Keypad assets are unavailable: "
                f"{sorted(self._missing_keypad_assets)}"
            )
        if broken_images:
            raise ManualBrowserError(f"manual HTML contains broken images: {broken_images}")
        if self._blocked_urls:
            raise ManualBrowserError(
                f"manual HTML attempted requests outside the compiler origin: {self._blocked_urls}"
            )
        if self._page_errors:
            raise ManualBrowserError(f"manual HTML raised JavaScript errors: {self._page_errors}")

    def _render_in_browser(self, browser: Browser, *, base_url: str) -> tuple[int, ...]:
        """Run the load, frame capture, flat print, and final validation phases."""
        # Include the ephemeral port so other services on loopback remain inaccessible.
        compiler_url = urlparse(base_url)
        self._compiler_origin = (compiler_url.scheme, compiler_url.netloc)
        page = self._new_page(browser)
        self._load_merger(page, base_url=base_url)

        page_counts, flattened_documents, broken_images = self._flatten_frames(page)
        # Source-frame failures must stop compilation before a PDF is printed.
        self._raise_errors(broken_images=broken_images)

        flattened_broken_images = _print_documents(
            page,
            documents=flattened_documents,
            page_counts=page_counts,
            output_pdf=self._output_pdf,
        )
        # The flat print tree loads assets again and therefore receives its own validation pass.
        self._raise_errors(broken_images=flattened_broken_images)
        return tuple(page_counts)


def render_html(
    documents: Sequence[HtmlDocument], *, source_root: Path, keypad_root: Path, output_pdf: Path
) -> tuple[int, ...]:
    """Render ordered HTML documents with the pinned merger and managed Chromium."""
    renderer = _ManualRenderer(
        documents, source_root=source_root, keypad_root=keypad_root, output_pdf=output_pdf
    )
    return renderer.render()
