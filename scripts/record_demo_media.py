"""Record the app walkthrough GIF and the review-gallery screenshot for the README.

Unlike ``gcf demo`` (pure Python), this drives a real browser, so it needs the
dev extras plus Playwright with Chromium:

    pip install -e ".[ui]" playwright && playwright install chromium
    python scripts/record_demo_media.py --out docs/demo

Set ``CHROMIUM_PATH`` to use an existing Chromium binary.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import List

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _launch_kwargs() -> dict:
    path = os.environ.get("CHROMIUM_PATH")
    return {"executable_path": path} if path else {}


def _gif(frames: List[Path], out: Path, width: int = 1100, ms: int = 700) -> None:
    imgs = []
    for f in frames:
        im = Image.open(f).convert("RGB")
        im = im.resize(
            (width, int(im.height * width / im.width)), Image.Resampling.LANCZOS
        )
        imgs.append(
            im.quantize(
                colors=192, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE
            )
        )
    durations = [ms] * len(imgs)
    durations[-1] = 2600  # linger on the result
    imgs[0].save(
        out,
        save_all=True,
        append_images=imgs[1:],
        duration=durations,
        loop=0,
        optimize=True,
    )


async def _record_app(port: int, frames_dir: Path) -> List[Path]:
    from playwright.async_api import async_playwright

    frames: List[Path] = []

    async def snap(page, name: str) -> None:
        p = frames_dir / f"{len(frames):02d}-{name}.png"
        await page.screenshot(path=str(p))
        frames.append(p)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(**_launch_kwargs())
        page = await browser.new_page(viewport={"width": 1400, "height": 900})
        await page.goto(f"http://127.0.0.1:{port}", wait_until="networkidle")
        await page.get_by_label("Product / service *").wait_for(timeout=60000)
        await page.wait_for_timeout(1500)
        await snap(page, "start")

        async def type_into(label: str, text: str) -> None:
            await page.get_by_label(label).click()
            await page.get_by_label(label).type(text, delay=12)

        await type_into("Product / service *", "Cloudstep running shoes")
        await snap(page, "product")
        await type_into("Audience", "busy city runners")
        await type_into("Offer", "30% off launch week")
        await snap(page, "offer")
        await type_into(
            "Key benefits (one per line)",
            "Featherlight 180g build\nCushioned for 20km runs",
        )
        await type_into("Problem it solves", "sore feet after long runs")
        await snap(page, "brief")
        await page.get_by_role("button", name="✨ Generate & render").click()
        for i in range(8):
            await page.wait_for_timeout(1200)
            await snap(page, f"working-{i}")
            if await page.get_by_text("images ready").count():
                break
        await page.get_by_text("images ready").wait_for(timeout=120000)
        await page.wait_for_timeout(1500)
        for i in range(3):
            await page.mouse.move(700, 600)
            await page.mouse.wheel(0, 420)
            await page.wait_for_timeout(900)
            await snap(page, f"results-{i}")
        await browser.close()
    return frames


async def _shoot_gallery(gallery: Path, out: Path) -> None:
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(**_launch_kwargs())
        page = await browser.new_page(
            viewport={"width": 1400, "height": 1000}, device_scale_factor=1
        )
        await page.goto(gallery.resolve().as_uri())
        await page.wait_for_timeout(2500)
        await page.screenshot(path=str(out))
        await browser.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default="docs/demo")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="gcf-media-") as tmp:
        tmp_path = Path(tmp)

        # 1) Review gallery from a real dry run
        run_dir = tmp_path / "run"
        subprocess.run(
            [
                sys.executable,
                "-m",
                "gcf",
                "run",
                "--input",
                str(ROOT / "examples" / "demo_ads.csv"),
                "--out",
                str(run_dir),
                "--mode",
                "dry",
                "--formats",
                "square,story",
                "--max-creatives",
                "18",
            ],
            check=True,
            cwd=ROOT,
        )
        shot = tmp_path / "gallery.png"
        asyncio.run(_shoot_gallery(run_dir / "gallery.html", shot))
        Image.open(shot).convert("RGB").save(
            out / "07-review-gallery.jpg", quality=86, optimize=True
        )

        # 2) App walkthrough GIF (Creative Studio tab)
        port = _free_port()
        env = {**os.environ, "STREAMLIT_BROWSER_GATHER_USAGE_STATS": "false"}
        proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                str(ROOT / "app.py"),
                "--server.headless",
                "true",
                "--server.port",
                str(port),
            ],
            cwd=tmp_path,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        (tmp_path / "config.yaml").write_text(
            (ROOT / "config.yaml").read_text(encoding="utf-8"), encoding="utf-8"
        )
        try:
            deadline = time.time() + 60
            while time.time() < deadline:
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=1):
                        break
                except OSError:
                    time.sleep(0.5)
            frames_dir = tmp_path / "frames"
            frames_dir.mkdir()
            frames = asyncio.run(_record_app(port, frames_dir))
            _gif(frames, out / "08-studio-app.gif")
        finally:
            proc.terminate()
            proc.wait(timeout=20)
    print(f"Wrote {out / '07-review-gallery.jpg'} and {out / '08-studio-app.gif'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
