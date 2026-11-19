"""Record the web UI demo: generate with Claude, run without AI, seed a fault, detect it.

Everything in the video is live: the UI server, NexStock in Docker and one Claude call (about
$0.10). Waits longer than a few seconds are sped up afterwards, and the caption says so.

Needs Playwright (pip install playwright) in any Python environment, Google Chrome, ffmpeg,
Docker, and ANTHROPIC_API_KEY plus the NEXSTOCK_* accounts in .env. From the repository root:

    <python with playwright> docs/demo/record_ui_demo.py
"""

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[2]
OUTPUT = REPO / "docs" / "demo" / "apiguard-ui-demo.mp4"
URL = "http://127.0.0.1:8765/"
WIDTH, HEIGHT = 1440, 900
SPEED_UP = 8
COMPOSE = ["docker", "compose", "-f", str(REPO / "apps/nexstock/compose.yaml")]

OVERLAY = """() => {
  const cursor = document.createElement('div');
  Object.assign(cursor.style, {position: 'fixed', width: '20px', height: '20px', left: '-40px',
    top: '-40px', borderRadius: '50%', background: 'rgba(255,255,255,.9)', zIndex: 99999,
    border: '2px solid #4c6ef5', boxShadow: '0 0 0 6px rgba(76,110,245,.28)',
    pointerEvents: 'none', transform: 'translate(-50%,-50%)', transition: 'transform .12s'});
  document.body.appendChild(cursor);
  addEventListener('mousemove', (e) => { cursor.style.left = e.clientX + 'px';
    cursor.style.top = e.clientY + 'px'; }, true);
  addEventListener('mousedown', () => cursor.style.transform = 'translate(-50%,-50%) scale(.65)', true);
  addEventListener('mouseup', () => cursor.style.transform = 'translate(-50%,-50%)', true);
  const caption = document.createElement('div');
  caption.id = 'demo-caption';
  Object.assign(caption.style, {position: 'fixed', left: '50%', bottom: '70px', zIndex: 99998,
    transform: 'translateX(-50%)', background: 'rgba(16,19,26,.94)', color: '#fff',
    padding: '12px 22px', borderRadius: '12px', font: '600 19px/1.35 system-ui, sans-serif',
    boxShadow: '0 8px 30px rgba(0,0,0,.45)', maxWidth: '82%', textAlign: 'center',
    border: '1px solid rgba(255,255,255,.12)', opacity: 0, transition: 'opacity .35s',
    pointerEvents: 'none'});
  document.body.appendChild(caption);
}"""


class Demo:
    def __init__(self, page):
        self.page = page
        self.start = time.monotonic()
        self.fast = []  # (start, end) seconds of video to speed up

    def now(self):
        return time.monotonic() - self.start

    def caption(self, text, hold=0.0):
        self.page.evaluate(
            """(t) => { const c = document.getElementById('demo-caption');
                c.style.opacity = t ? 1 : 0; if (t) c.innerHTML = t; }""",
            text,
        )
        time.sleep(hold)

    def scroll_to(self, selector, offset=70):
        self.page.evaluate(
            """([s, o]) => { const el = document.querySelector(s);
                scrollTo({top: el.getBoundingClientRect().top + scrollY - o, behavior: 'smooth'}); }""",
            [selector, offset],
        )
        time.sleep(1.3)

    def point(self, locator, pause=0.35):
        locator.scroll_into_view_if_needed()
        box = locator.bounding_box()
        self.page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, steps=28)
        time.sleep(pause)

    def click(self, locator, pause=0.5):
        self.point(locator)
        self.page.mouse.down()
        self.page.mouse.up()
        locator.click(trial=True)  # Fails loudly if the element was not clickable.
        time.sleep(pause)

    def wait_task(self, timeout, speed_up=False):
        self.page.wait_for_selector("#log-icon .spinner", timeout=15_000)
        began = self.now()
        self.page.wait_for_selector("#log-icon .spinner", state="detached", timeout=timeout * 1000)
        failed = self.page.locator("#log-icon .verdict-no").count()
        if failed:
            raise RuntimeError("task failed: " + self.page.inner_text("#log-body")[-800:])
        if speed_up:
            self.fast.append((began + 1.0, self.now()))
        time.sleep(1.8)  # Let the page reload its data.
        self.page.click("#log-head")  # Collapse the task log.
        time.sleep(0.6)


def record(video_dir):
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(
            viewport={"width": WIDTH, "height": HEIGHT},
            record_video_dir=str(video_dir),
            record_video_size={"width": WIDTH, "height": HEIGHT},
            color_scheme="dark",
        )
        page = context.new_page()
        demo = Demo(page)
        page.goto(URL)
        page.wait_for_selector("#suite-view .stats")
        page.evaluate(OVERLAY)
        time.sleep(0.8)
        sections = page.locator("section")

        demo.caption(
            "APIGuard: AI-generated API tests for FastAPI apps.<br>"
            "Target: NexStock, running in Docker with fixed seed data."
        )
        demo.point(page.locator("#chips"), 2.5)

        # 1. Generate.
        demo.caption("① Claude reads the OpenAPI specification and writes test definitions.")
        for tag in page.locator("#tags .toggle.on").all_inner_texts():
            name = tag.rsplit(" ", 1)[0]
            if name != "Categories":
                demo.click(page.locator(f'#tags [data-tag="{name}"]'), 0.3)
        if not page.locator('#tags [data-tag="Categories"].on').count():
            demo.click(page.locator('#tags [data-tag="Categories"]'))
        demo.click(page.locator("#generate"))
        demo.caption(f"Claude is writing tests for the Categories API (sped up ×{SPEED_UP})")
        demo.wait_task(timeout=300, speed_up=True)
        demo.caption("Saved: every test was checked against the specification before saving.")
        demo.point(page.locator("#suite-view .stats"), 2.5)
        demo.click(page.locator("#suite-view details summary"), 0.8)
        post = page.locator("#suite-view tr.clickable", has_text="POST").first
        demo.click(post, 0.3)
        demo.caption(
            "Each test is a plain, reusable definition: request, role and expected status."
        )
        page.mouse.wheel(0, 260)
        time.sleep(3.5)
        demo.click(page.locator("#suite-view details summary"), 0.6)

        # 2. Run on the original app.
        demo.scroll_to("section:nth-of-type(3)")
        demo.caption("② Run the saved suite on the original app. No AI model is used.")
        demo.click(page.locator("#run"))
        demo.wait_task(timeout=180)
        demo.caption("Found a real NexStock bug: deleting a category returns 500.")
        demo.point(page.locator("#run-view .stats"), 1.5)
        demo.click(page.locator('#run-view tr[data-result="0"]'), 0.3)
        page.mouse.wheel(0, 220)
        time.sleep(4)

        # 3. Seed a fault and run again.
        demo.scroll_to("section:nth-of-type(2)")
        demo.caption("③ Seed a fault: F02 makes “create category” return 200 instead of 201.")
        demo.click(page.locator('[data-variant="F02-category-create-wrong-status"]'))
        demo.wait_task(timeout=180)
        demo.point(sections.nth(1).locator(".variant.current"), 1.2)
        demo.scroll_to("section:nth-of-type(3)")
        demo.caption("Run the same saved suite on the faulty app.")
        demo.click(page.locator("#run"))
        demo.wait_task(timeout=180)

        # 4. Compare.
        demo.scroll_to("section:nth-of-type(4)")
        demo.caption("④ Tests that passed on the original now fail: the fault is detected.")
        demo.point(page.locator("#compare-view .banner"), 5)

        # 5. Evaluation.
        demo.scroll_to("section:nth-of-type(5)")
        demo.caption(
            "⑤ Full evaluation (118 tests, 4 API areas, 3 seeded faults):<br>"
            "APIGuard detected 3/3, the Schemathesis baseline 1/3."
        )
        demo.point(page.locator("#evaluation-view table"), 6)
        demo.caption("Suites and results are saved to disk. Runs never call the AI model.", 3.5)

        context.close()
        browser.close()
        return next(video_dir.glob("*.webm")), demo.fast


def encode(source, fast):
    """Speed up the listed spans and encode an MP4."""
    duration = float(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
         str(source)], text=True))  # fmt: skip
    spans, cursor = [], 0.0
    for start, end in fast:
        spans += [(cursor, start, 1), (start, end, SPEED_UP)]
        cursor = end
    spans.append((cursor, duration, 1))
    parts = [
        f"[0:v]trim={a:.2f}:{b:.2f},setpts=(PTS-STARTPTS)/{k}[v{i}]"
        for i, (a, b, k) in enumerate(spans)
    ]
    graph = ";".join(parts) + ";" + "".join(f"[v{i}]" for i in range(len(spans)))
    graph += f"concat=n={len(spans)}:v=1:a=0,fps=30[out]"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(source), "-filter_complex", graph,
         "-map", "[out]", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20",
         "-movflags", "+faststart", str(OUTPUT)],
        check=True,
    )  # fmt: skip


def main():
    env = {**os.environ, "NEXSTOCK_FAULT": ""}
    docker_bin = Path.home() / ".docker" / "bin"
    env["PATH"] = f"{docker_bin}{os.pathsep}{env['PATH']}"
    subprocess.run([*COMPOSE, "up", "--detach", "--wait", "api"], env=env, check=True,
                   capture_output=True)  # fmt: skip
    server = subprocess.Popen(
        [str(REPO / ".venv/bin/apiguard"), "ui", "nexstock", "--no-browser"],
        cwd=REPO, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
    )  # fmt: skip
    try:
        time.sleep(2)
        with tempfile.TemporaryDirectory() as directory:
            source, fast = record(Path(directory))
            encode(source, fast)
    finally:
        server.terminate()
        subprocess.run([*COMPOSE, "up", "--detach", "--wait", "api"], env=env,
                       capture_output=True, check=False)  # fmt: skip
    print(f"Saved {OUTPUT.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg is required")
    sys.exit(main())
