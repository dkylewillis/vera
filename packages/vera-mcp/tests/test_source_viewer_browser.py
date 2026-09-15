"""Optional browser test with a local MCP Apps host simulator.

VERA_BROWSER_TESTS=1 enables it; install playwright and a browser first.
VERA_BROWSER_CHANNEL=msedge uses an installed Edge instead of Chromium.
"""

import asyncio
import json
import os
from importlib.resources import files
from pathlib import Path

import pytest
from test_source_viewer import source_archives  # noqa: F401

from vera_mcp import build_server
from vera_mcp.source_viewer import SourceRef, source_view

pytestmark = pytest.mark.skipif(
    os.environ.get("VERA_BROWSER_TESTS") != "1", reason="opt-in browser integration test"
)


def test_source_viewer_browser(source_archives):  # noqa: F811 - imported pytest fixture
    from playwright.sync_api import sync_playwright

    async def initial():
        result = await build_server().call_tool(
            "vera_show_sources",
            {
                "sources": [
                    {**ref.model_dump(), "id": f"C{i}"} for i, ref in enumerate(source_archives, 1)
                ]
            },
        )
        return result.model_dump(by_alias=True)

    initial_result = asyncio.run(initial())
    widget = files("vera_mcp").joinpath("ui/source-viewer.html").read_text(encoding="utf-8")

    def tool_call(params):
        assert params["name"] == "vera_source_page"
        arguments = params["arguments"]
        view = source_view(
            SourceRef(file=arguments["file"], chunk_id=arguments["chunk_id"]),
            arguments.get("page", 0),
        )
        return {"_meta": {"vera/view": view}}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            channel=os.environ.get("VERA_BROWSER_CHANNEL") or None, headless=True
        )
        page = browser.new_page(viewport={"width": 1100, "height": 780})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.expose_function("veraTestTool", tool_call)
        page.set_content(
            '<iframe id="app" title="VERA" style="width:100%;height:740px;border:0"></iframe>'
        )
        page.evaluate(
            """({initial, widget}) => {
            const frame = document.querySelector('iframe');
            window.addEventListener('message', async event => {
              if (event.source !== frame.contentWindow) return;
              const m = event.data;
              const respond = result => frame.contentWindow.postMessage(
                {jsonrpc:'2.0',id:m.id,result}, '*');
              if (m.method === 'ui/initialize') respond({
                protocolVersion:'2026-01-26',
                hostCapabilities:{serverTools:{}},
                hostInfo:{name:'VERA test host',version:'1'},
                hostContext:{theme:'light',displayMode:'inline',availableDisplayModes:['inline','fullscreen']}
              });
              if (m.method === 'ui/notifications/initialized') frame.contentWindow.postMessage({
                jsonrpc:'2.0',method:'ui/notifications/tool-result',params:initial}, '*');
              if (m.method === 'tools/call') {
                const result = await window.veraTestTool(m.params);
                respond(result);
              }
              if (m.method === 'ui/request-display-mode') respond({mode:m.params.mode});
            });
            frame.srcdoc = widget;
            }""",
            {"initial": initial_result, "widget": widget},
        )
        frame = page.frame_locator("#app")
        launcher = frame.get_by_role("button", name="Open VERA sources", exact=True)
        launcher.wait_for()
        screenshot_dir = os.environ.get("VERA_SCREENSHOT_DIR")
        if screenshot_dir:
            Path(screenshot_dir).mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(Path(screenshot_dir) / "vera-source-launcher.png"))
        launcher.click()
        frame.get_by_role("button", name="Collapse", exact=True).wait_for()
        assert frame.locator(".sourceId").all_inner_texts() == ["[C1]", "[C2]"]
        frame.locator(".source").nth(0).click()
        image = frame.locator(".paper img")
        image.wait_for()
        assert image.evaluate("(img) => img.complete && img.naturalWidth > 0")
        assert frame.locator(".box").count() > 0
        frame.get_by_role("button", name="Next page", exact=True).click()
        frame.get_by_text("Page 2 of 2", exact=True).wait_for()
        assert frame.get_by_role("button", name="Next page", exact=True).is_disabled()
        frame.get_by_role("button", name="Previous page", exact=True).click()
        frame.get_by_text("Page 1 of 2", exact=True).wait_for()
        frame.get_by_role("button", name="Highlights on", exact=True).click()
        assert frame.locator("#viewport").evaluate("e=>e.classList.contains('no-highlights')")
        frame.get_by_role("button", name="Highlights off", exact=True).click()
        frame.get_by_role("button", name="Zoom in", exact=True).click()
        assert frame.locator(".paper").evaluate("e=>e.style.width") == "120%"
        frame.get_by_role("button", name="Collapse", exact=True).click()
        frame.get_by_role("button", name="Expand", exact=True).wait_for()
        frame.get_by_role("button", name="Expand", exact=True).click()
        frame.get_by_role("button", name="Collapse", exact=True).wait_for()
        frame.get_by_role("button", name="Zoom out", exact=True).click()

        if screenshot_dir:
            page.screenshot(path=str(Path(screenshot_dir) / "vera-source-viewer.png"))
        frame.locator(".source").nth(1).click()
        frame.locator(".lines").wait_for()
        assert frame.locator(".active").count() > 0
        assert frame.locator(".lines").inner_text().find("<script>") >= 0
        assert frame.locator("body").evaluate("()=>window.injected") is None
        frame.get_by_role("button", name="Close viewer", exact=True).click()
        launcher.wait_for()
        page.set_viewport_size({"width": 390, "height": 780})
        assert frame.locator("body").evaluate(
            "()=>document.documentElement.scrollWidth <= window.innerWidth"
        )
        if screenshot_dir:
            page.screenshot(path=str(Path(screenshot_dir) / "vera-source-viewer-mobile.png"))
        assert not errors, json.dumps(errors)
        browser.close()
