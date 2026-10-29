import { chromium } from "playwright";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const videoDir = path.join(here, "raw");

const browser = await chromium.launch({
  headless: false,
  args: ["--use-angle=default", "--enable-webgl", "--ignore-gpu-blocklist"],
});
const context = await browser.newContext({
  viewport: { width: 1600, height: 900 },
  recordVideo: { dir: videoDir, size: { width: 1600, height: 900 } },
});
const page = await context.newPage();
page.setDefaultTimeout(20000);

async function caption(text) {
  await page.evaluate((message) => {
    let el = document.getElementById("demo-caption");
    if (!el) {
      el = document.createElement("div");
      el.id = "demo-caption";
      el.style.cssText = [
        "position:fixed",
        "left:50%",
        "bottom:78px",
        "transform:translateX(-50%)",
        "z-index:80",
        "max-width:760px",
        "padding:10px 16px",
        "border:1px solid #7fd3e8",
        "border-radius:10px",
        "background:rgba(11,18,32,0.92)",
        "color:#e6eef8",
        "font:600 16px/1.35 Segoe UI, sans-serif",
        "text-align:center",
        "pointer-events:none",
        "box-shadow:0 8px 28px rgba(0,0,0,0.35)",
      ].join(";");
      document.body.appendChild(el);
    }
    el.textContent = message;
  }, text);
}

async function shot(name) {
  await page.screenshot({ path: path.join(here, `${name}.png`) });
}

try {
  await page.goto("http://localhost:3000", { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: "Replay recorded gripper run" }).waitFor();
  await page.getByRole("button", { name: "Replay recorded gripper run" }).click();
  await page.getByText("13.831 N").waitFor();
  await page.getByText("Opening viewport").waitFor({ state: "hidden", timeout: 20000 }).catch(() => {});
  await page.getByText(/N actuator/).first().waitFor();
  await caption("128 stored designs. Safety margin is the worst-case train margin, 13.831 N.");
  await page.waitForTimeout(2200);
  await shot("01-twin");

  const canvas = page.locator("canvas");
  const box = await canvas.boundingBox();
  if (!box) throw new Error("The 3D canvas did not appear.");
  const cx = box.x + box.width * 0.55;
  const cy = box.y + box.height * 0.48;
  await caption("Drag to orbit the gripper. This is a live 3D model, not a picture.");
  await page.mouse.move(cx, cy);
  await page.mouse.down();
  await page.mouse.move(cx + 220, cy + 30, { steps: 28 });
  await page.waitForTimeout(400);
  await page.mouse.move(cx - 40, cy - 50, { steps: 28 });
  await page.mouse.up();
  await page.waitForTimeout(900);
  await shot("02-orbit");

  await page.getByRole("button", { name: "side", exact: true }).click();
  await caption("Side view. Finger length, pad, and actuator force come from the stored design.");
  await page.waitForTimeout(1800);
  await page.getByRole("button", { name: "front", exact: true }).click();
  await page.waitForTimeout(1500);
  await page.getByRole("button", { name: "isometric", exact: true }).click();
  await page.waitForTimeout(1200);

  await page.getByRole("button", { name: "Illustrative jaw" }).first().click();
  await caption("Illustrative jaw motion only. The surrogate scores a fixed jaw. This is not validated kinematics.");
  await page.waitForTimeout(3200);
  await page.getByRole("button", { name: "Illustrative jaw" }).first().click();
  await page.waitForTimeout(600);

  await page.getByRole("button", { name: "Swarm", exact: true }).click();
  await page.getByText("Y is stored fitness").waitFor();
  await caption("Swarm replay. Height is stored fitness. Shape is the search method.");
  await page.waitForTimeout(1200);
  await page.getByRole("button", { name: "2×" }).click();
  const replay = page.getByRole("button", { name: "Replay generations" });
  if (await replay.count()) {
    await replay.click();
  } else {
    await page.getByRole("button", { name: "Play" }).click();
  }
  await page.waitForTimeout(2800);
  await shot("03-swarm");

  await page.getByRole("button", { name: "front", exact: true }).click();
  await page.getByRole("button", { name: "Failures", exact: true }).click();
  await page.getByRole("button", { name: /adv-g00-05/ }).click();
  await page.getByText("-24.231 N").waitFor();
  await page.getByText(/N actuator/).first().waitFor();
  await page.getByRole("button", { name: "front", exact: true }).click();
  await page.getByRole("button", { name: "Reset" }).click();
  await caption("Failure adv-g00-05. Stored margin −24.231 N. The red object is not a stress map.");
  await page.waitForTimeout(3200);
  await shot("04-failure");

  await page.getByRole("button", { name: "Energy", exact: true }).click();
  await page.getByText("does not invent a plant").waitFor();
  await caption("This run is a gripper. The energy view does not invent a plant or an hourly trace.");
  await page.waitForTimeout(2600);
  await shot("05-energy");

  await page.getByRole("button", { name: "Digital Twin", exact: true }).click();
  await page.getByRole("button", { name: "isometric", exact: true }).click();
  await caption("Scores come only from the simulator. Planner text is a hypothesis.");
  await page.waitForTimeout(2200);
} catch (error) {
  await shot("error").catch(() => {});
  console.error(error);
  process.exitCode = 1;
} finally {
  const video = page.video();
  await context.close();
  await browser.close();
  if (video) console.log(await video.path());
}
