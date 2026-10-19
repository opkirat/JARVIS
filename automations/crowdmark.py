"""Sign into Crowdmark through Chrome and export scores from every course."""

import asyncio
import json
import os
import re
import shutil
from pathlib import Path
from datetime import datetime, timezone

from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = PROJECT_ROOT / "data" / "crowdmark" / "scores.json"
COURSES_URL = "https://app.crowdmark.com/student/courses"


COURSES_SCRIPT = r"""() => {
    const courses = new Map();
    for (const link of document.querySelectorAll('a[href]')) {
        const url = new URL(link.href);
        if (url.origin !== 'https://app.crowdmark.com' ||
            !/^\/student\/courses\/[^/]+\/?$/.test(url.pathname)) continue;
        const text = link.innerText.trim();
        if (!text) continue;
        const count = text.match(/(\d+)\s+assessments?\b/i);
        const title = text.split('\n')[0].trim();
        const previous = courses.get(url.href);
        courses.set(url.href, {
            title, url: url.href,
            expected_assessments: count ? Number(count[1]) :
                (previous?.expected_assessments ?? null)
        });
    }
    return {url: location.href, courses: [...courses.values()]};
}"""


SCORES_SCRIPT = r"""() => {
    const clean = element => element?.innerText.trim() || '';
    const assessments = [];
    let recognizedTables = 0;
    let invalidRows = 0;
    for (const table of document.querySelectorAll('table')) {
        const headers = [...table.querySelectorAll('thead th')]
            .map(cell => clean(cell).toLowerCase());
        const titleIndex = headers.indexOf('title');
        const statusIndex = headers.indexOf('status');
        const scoreIndex = headers.indexOf('score');
        if ([titleIndex, statusIndex, scoreIndex].includes(-1)) continue;
        recognizedTables++;
        for (const row of table.querySelectorAll('tbody tr')) {
            const cells = [...row.querySelectorAll('td')];
            const title = clean(cells[titleIndex]);
            const link = cells[titleIndex]?.querySelector('a[href]');
            if (!title || !link || cells.length < headers.length) {
                invalidRows++;
                continue;
            }
            assessments.push({
                title, url: link.href,
                status: clean(cells[statusIndex]) || null,
                score: clean(cells[scoreIndex]) || null
            });
        }
    }
    return {
        url: location.href,
        title: clean(document.querySelector('main h1, h1')),
        assessments, recognized_tables: recognizedTables, invalid_rows: invalidRows,
        empty_message: /has not assigned anything|no assessments/i.test(
            (document.querySelector('main') || document.body).innerText
        )
    };
}"""


async def call_tool(session, name, arguments):
    result = await session.call_tool(name, arguments=arguments)
    if result.is_error:
        # Avoid printing browser content or connection credentials on failure.
        raise RuntimeError(
            f"{name} failed. Check Chrome, the extension connection, and the page."
        )
    return result


async def evaluate_json(session, function):
    result = await call_tool(session, "browser_evaluate", {"function": function})
    for block in result.content:
        if block.type != "text":
            continue
        text = block.text
        if "### Result" in text:
            text = text.split("### Result", 1)[1].lstrip()
        try:
            value, _ = json.JSONDecoder().raw_decode(text)
        except ValueError:
            continue
        if isinstance(value, dict):
            return value
    raise RuntimeError("The browser did not return the expected JSON data.")


async def wait_for_dom(session, condition):
    """Wait for page content without ambiguous text matches."""
    for _ in range(30):
        state = await evaluate_json(
            session, f"() => ({{ready: Boolean({condition})}})"
        )
        if state["ready"]:
            return
        await asyncio.sleep(1)
    raise RuntimeError("The expected page content did not load within 30 checks.")


def score_percent(value):
    """Only convert explicit percentages; unavailable scores stay None."""
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*%\s*", value or "")
    return float(match.group(1)) if match else None


async def extract_scores(session):
    await call_tool(session, "browser_navigate", {"url": COURSES_URL})
    print("Waiting for your courses. Complete university sign-in if prompted.")
    await wait_for_dom(session, 'document.querySelector(\'a[href^="/student/courses/"]\')')
    index = await evaluate_json(session, COURSES_SCRIPT)
    courses = index.get("courses", [])
    if index.get("url", "").rstrip("/") != COURSES_URL or not courses:
        raise RuntimeError("No courses found. Finish signing in and run again.")

    report = {
        "source": "crowdmark",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "status": "success",
        "courses_discovered": len(courses),
        "courses": [],
    }
    print(f"Found {len(courses)} unique courses.")
    for course in courses:
        entry = {**course, "status": "success", "assessments": []}
        try:
            await call_tool(session, "browser_navigate", {"url": course["url"]})
            await wait_for_dom(
                session,
                "document.querySelector('table tbody tr') || "
                "/has not assigned anything|no assessments/i.test("
                "(document.querySelector('main') || document.body).innerText)",
            )
            page = await evaluate_json(session, SCORES_SCRIPT)
            if page["url"].rstrip("/") != course["url"].rstrip("/"):
                raise RuntimeError("The browser redirected away from this course.")
            if not page["recognized_tables"] and not page["empty_message"]:
                raise RuntimeError("No recognizable assessment table or empty state.")
            if page["invalid_rows"]:
                raise RuntimeError("Some assessment rows could not be read.")

            seen = set()
            for assessment in page["assessments"]:
                if assessment["url"] in seen:
                    continue
                seen.add(assessment["url"])
                entry["assessments"].append({
                    **assessment,
                    "score_percent": score_percent(assessment["score"]),
                })
            expected = course["expected_assessments"]
            actual = len(entry["assessments"])
            if expected is not None and actual != expected:
                raise RuntimeError(f"Expected {expected} assessments but extracted {actual}.")
            print(f"  {course['title']}: {actual} assessments")
        except RuntimeError as error:
            entry["status"] = "failed"
            entry["error"] = str(error)
            report["status"] = "partial"
            print(f"  {course['title']}: FAILED — {error}")
        report["courses"].append(entry)

    report["courses_completed"] = sum(
        course["status"] == "success" for course in report["courses"]
    )
    report["assessments_extracted"] = sum(
        len(course["assessments"]) for course in report["courses"]
    )
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = OUTPUT_PATH.with_suffix(".json.tmp")
    temporary_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary_path.replace(OUTPUT_PATH)
    print(f"Saved {report['assessments_extracted']} assessments to {OUTPUT_PATH}")
    if report["status"] != "success":
        raise RuntimeError("Extraction was partial. Check course errors in scores.json.")
    return report


async def find_sign_in(session, label):
    """Read a fresh snapshot so references belong to the current page."""
    result = await call_tool(session, "browser_snapshot", {})
    snapshot = "\n".join(
        block.text for block in result.content if block.type == "text"
    )

    # Use the real element reference from the page, rather than coordinates.
    words = r"\s+".join(re.escape(word) for word in label.split())
    return re.search(
        rf'(?:link|button) "{words}"[^\n]*?\[ref=([^\]]+)\]',
        snapshot,
        re.IGNORECASE,
    )

async def click_sign_in(session, click_tool, match, label):
    # Current MCP versions use "target"; older versions use "ref".
    properties = click_tool.input_schema.get("properties", {})
    target_key = "target" if "target" in properties else "ref"
    arguments = {target_key: match.group(1)}
    if "element" in properties:
        arguments["element"] = f"Crowdmark {label} link"

    await call_tool(session, "browser_click", arguments)
    print(f'Clicked "{label}".')


async def open_crowdmark(session):
    tools = await session.list_tools()
    click_tool = next(
        (tool for tool in tools.tools if tool.name == "browser_click"), None
    )
    if click_tool is None:
        raise RuntimeError("The MCP server does not expose browser_click.")

    print("Opening Crowdmark in a new Chrome tab...")
    await call_tool(
        session, "browser_tabs",
        {"action": "new", "url": COURSES_URL},
    )
    await wait_for_dom(session, "document.querySelector('h1')")
    current = await evaluate_json(session, "() => ({path: location.pathname})")
    if current.get("path", "").startswith("/student/"):
        print("Crowdmark is already signed in.")
        return

    await call_tool(session, "browser_navigate", {"url": "https://www.crowdmark.com/"})
    await wait_for_dom(
        session,
        "Array.from(document.querySelectorAll('a')).some("
        "a => /^sign\\s+in$/i.test(a.innerText.trim()))",
    )
    match = await find_sign_in(session, "Sign In")
    if not match:
        raise RuntimeError('Could not find "Sign In" on the Crowdmark homepage.')
    await click_sign_in(session, click_tool, match, "Sign In")

    current = await evaluate_json(session, "() => ({path: location.pathname})")
    if current.get("path", "").startswith("/student/"):
        print("Crowdmark is already signed in.")
        return

    match = await find_sign_in(session, "Sign in with LEARN")
    if not match:
        # A fresh session can show the general school chooser instead of
        # remembering Waterloo. Use the school page from your screenshot.
        await call_tool(
            session, "browser_navigate",
            {"url": "https://app.crowdmark.com/sign-in/waterloo"},
        )
        match = await find_sign_in(session, "Sign in with LEARN")
    if not match:
        raise RuntimeError(
            'Could not find "Sign in with LEARN" on the Waterloo sign-in page.'
        )
    await click_sign_in(session, click_tool, match, "Sign in with LEARN")
    print("LEARN sign-in selected.")


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
            await open_crowdmark(session)
            await extract_scores(session)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Stopped.")
    except RuntimeError as error:
        raise SystemExit(str(error))
