"""Export Fall 2026 class plans without normalizing their table formats."""

import asyncio
import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTLINES_URL = "https://outline.uwaterloo.ca/viewer/?q="
OUTPUT_PATH = PROJECT_ROOT / "data" / "course_outlines" / "fall_2026_class_plans.json"

COURSES_SCRIPT = r"""() => {
    const heading = [...document.querySelectorAll('h3')]
        .find(e => e.innerText.trim() === 'Fall 2026');
    if (!heading) return {courses: []};
    const courses = [];
    for (const row of heading.parentElement.querySelectorAll('tbody tr')) {
        const link = [...row.querySelectorAll('a[href]')]
            .find(a => a.innerText.trim().toLowerCase() === 'view');
        if (!link) continue;
        const cells = [...row.querySelectorAll('td')];
        courses.push({
            course: cells[0].innerText.trim(),
            title: cells[1].innerText.trim(),
            sections: cells[2].innerText.trim(),
            url: link.href,
            href: link.getAttribute('href')
        });
    }
    return {courses};
}"""

PLAN_SCRIPT = r"""() => {
    const headings = [...document.querySelectorAll('h1,h2,h3,h4,h5,h6')];
    const heading = headings.find(e =>
        e.textContent.trim().toLowerCase() === 'tentative class plan');
    if (!heading) return {found: false, url: location.href};
    const level = Number(heading.tagName[1]);
    const next = headings.slice(headings.indexOf(heading) + 1)
        .find(e => Number(e.tagName[1]) <= level);
    const range = document.createRange();
    range.setStartAfter(heading);
    if (next) range.setEndBefore(next);
    else range.setEndAfter(document.body.lastChild);
    const section = document.createElement('div');
    section.append(range.cloneContents());
    const text = element => (element.innerText ?? element.textContent).trim();
    // Read cells from the live page so rendered line breaks are preserved.
    const tables = [...document.querySelectorAll('table')]
        .filter(table => range.intersectsNode(table)).map(table => {
        const rows = [...table.rows].filter(row => row.closest('table') === table);
        const cells = rows.map(row => [...row.cells].map(cell => ({
            text: text(cell),
            tag: cell.tagName.toLowerCase(),
            rowspan: cell.rowSpan,
            colspan: cell.colSpan
        })));
        return {
            columns: cells[0]?.map(cell => cell.text) || [],
            rows: cells.slice(1).map(row => row.map(cell => cell.text)),
            original_cells: cells,
            html: table.outerHTML
        };
    });
    return {
        found: true,
        url: location.href,
        page_heading: text(document.querySelector('h1')),
        section_title: text(heading),
        section_html: section.innerHTML,
        notes: [...document.querySelectorAll('p,li')]
            .filter(e => range.intersectsNode(e) && !e.closest('table'))
            .map(text).filter(Boolean),
        tables
    };
}"""


async def call_tool(session, name, arguments):
    result = await session.call_tool(name, arguments=arguments)
    if result.is_error:
        raise RuntimeError(f"{name} failed. Check Chrome and the current page.")
    return result


async def evaluate_json(session, function):
    result = await call_tool(session, "browser_evaluate", {"function": function})
    for block in result.content:
        if block.type != "text":
            continue
        text = block.text.split("### Result", 1)[-1].lstrip()
        try:
            value, _ = json.JSONDecoder().raw_decode(text)
        except ValueError:
            continue
        if isinstance(value, dict):
            return value
    raise RuntimeError("The page did not return the expected JSON.")


async def wait_for_dom(session, condition):
    for _ in range(30):
        state = await evaluate_json(session, f"() => ({{ready: Boolean({condition})}})")
        if state["ready"]:
            return
        await asyncio.sleep(1)
    raise RuntimeError("Expected page content did not load. Check university sign-in.")


async def extract_class_plans(session):
    opened = await call_tool(
        session, "browser_tabs", {"action": "new", "url": OUTLINES_URL}
    )
    # View links open new tabs. Remember the index tab to return for each click.
    tab_text = "\n".join(b.text for b in opened.content if b.type == "text")
    match = re.search(r"(?m)^-\s*(\d+):\s*\(current\)", tab_text)
    if not match:
        raise RuntimeError("Could not identify the outline-list tab.")
    list_tab = int(match.group(1))
    await wait_for_dom(
        session,
        "Array.from(document.querySelectorAll('h3')).some("
        "e => e.innerText.trim() === 'Fall 2026')",
    )
    courses = (await evaluate_json(session, COURSES_SCRIPT))["courses"]
    if not courses:
        raise RuntimeError("No enrolled Fall 2026 View links were found.")
    print(f"Found {len(courses)} enrolled Fall 2026 courses.")

    report = {
        "term": "Fall 2026",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "status": "success",
        "courses_discovered": len(courses),
        "courses": [],
    }
    tools = await session.list_tools()
    click_tool = next(t for t in tools.tools if t.name == "browser_click")
    if "target" not in click_tool.input_schema.get("properties", {}):
        raise RuntimeError("This script requires an MCP browser_click tool with target support.")

    for course in courses:
        entry = {**course, "status": "success"}
        entry.pop("href")
        try:
            await call_tool(session, "browser_tabs", {"action": "select", "index": list_tab})
            # This clicks the actual View link; it does not invent outline URLs.
            selector = "a[href=" + json.dumps(course["href"]) + "]"
            await call_tool(session, "browser_click", {"target": selector})
            tabs = await call_tool(session, "browser_tabs", {"action": "list"})
            tab_text = "\n".join(b.text for b in tabs.content if b.type == "text")
            tab_matches = re.findall(
                r"(?m)^-\s*(\d+):[^\n]*\(" + re.escape(course["url"]) + r"(?:#[^)]*)?\)",
                tab_text,
            )
            if not tab_matches:
                raise RuntimeError("View did not open the expected outline tab.")
            await call_tool(
                session, "browser_tabs", {"action": "select", "index": int(tab_matches[-1])}
            )
            await wait_for_dom(
                session,
                "location.pathname === " + json.dumps(course["href"]) +
                " && document.querySelector('h1') && "
                "document.querySelector('a[href=\"#tentative_class_plan\"]')",
            )
            plan = await evaluate_json(session, PLAN_SCRIPT)
            entry["class_plan"] = plan
            if not plan["found"]:
                raise RuntimeError("Tentative Class Plan section was not found.")
            if not plan["tables"]:
                raise RuntimeError("Class Plan section has no HTML table; original section saved.")
            print(f"{course['course']}: extracted {len(plan['tables'])} table(s)")
        except RuntimeError as error:
            entry["status"] = "failed"
            entry["error"] = str(error)
            report["status"] = "partial"
            print(f"{course['course']}: {error}")
        report["courses"].append(entry)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT_PATH.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(OUTPUT_PATH)
    print(f"Saved {OUTPUT_PATH}")
    if report["status"] != "success":
        raise RuntimeError("Some outlines could not be extracted; check the JSON report.")
    return report


async def main():
    load_dotenv(PROJECT_ROOT / ".env")

    npx = shutil.which("npx")
    if not npx:
        raise RuntimeError(
            "npx was not found. Install Node.js LTS and restart your terminal."
        )

    token = os.environ.get("PLAYWRIGHT_MCP_EXTENSION_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "Add PLAYWRIGHT_MCP_EXTENSION_TOKEN to your project .env file."
        )

    server = StdioServerParameters(
        command=npx,
        args=["-y", "@playwright/mcp@latest", "--extension"],
        env={"PLAYWRIGHT_MCP_EXTENSION_TOKEN": token},
        cwd=str(PROJECT_ROOT),
    )

    print("Connecting to the Playwright extension. Keep Chrome open.")
    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write, read_timeout_seconds=90) as session:
            await session.initialize()
            await extract_class_plans(session)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Stopped.")
    except RuntimeError as error:
        raise SystemExit(str(error))
