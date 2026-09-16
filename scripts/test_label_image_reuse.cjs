// Real React, synthetic photos/API only. Can also measure the previous frontend with LABEL_IMAGE_BASELINE=1.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawn } = require("node:child_process");
async function main() {
  const frontend =
    process.env.LABEL_IMAGE_FRONTEND ||
    path.resolve(__dirname, "../local_inspection_service/frontend");
  const baseline = process.env.LABEL_IMAGE_BASELINE === "1";
  const { chromium } = require(path.join(frontend, "node_modules/playwright"));
  const output = fs.mkdtempSync(path.join(os.tmpdir(), "label-image-reuse-"));
  const port = process.env.LABEL_IMAGE_PORT || "5187";
  const base = "http://127.0.0.1:" + port;
  const vite = spawn(
    process.execPath,
    [
      path.join(frontend, "node_modules/vite/bin/vite.js"),
      "--host",
      "127.0.0.1",
      "--port",
      port,
      "--strictPort",
      "--base",
      "/",
    ],
    {
      cwd: frontend,
      env: { ...process.env, VITE_ROUTER_BASENAME: "/" },
      stdio: "ignore",
    },
  );
  let browser;
  try {
    for (let i = 0; i < 100; i++) {
      try {
        if ((await fetch(base)).ok) break;
      } catch {}
      await new Promise((r) => setTimeout(r, 100));
    }
    browser = await chromium.launch({
      headless: true,
      args: [
        "--use-fake-device-for-media-stream",
        "--use-fake-ui-for-media-stream",
      ],
    });
    const context = await browser.newContext({
      viewport: { width: 1440, height: 900 },
      permissions: ["camera"],
    });
    const page = await context.newPage();
    page.setDefaultTimeout(15000);
    const errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await page.goto("about:blank");
    const photos = await page.evaluate(() => {
      const canvas = document.createElement("canvas");
      canvas.width = 2000;
      canvas.height = 1500;
      const ctx = canvas.getContext("2d"),
        data = ctx.createImageData(2000, 1500);
      let seed = 7;
      for (let i = 0; i < data.data.length; i += 4) {
        seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
        data.data[i] = seed & 255;
        data.data[i + 1] = (seed >>> 8) & 255;
        data.data[i + 2] = (seed >>> 16) & 255;
        data.data[i + 3] = 255;
      }
      ctx.putImageData(data, 0, 0);
      ctx.fillStyle = "white";
      ctx.fillRect(0, 0, 1200, 500);
      ctx.fillStyle = "black";
      ctx.font = "120px sans-serif";
      ctx.fillText("SYNTHETIC LABEL", 30, 250);
      const full = canvas.toDataURL("image/png").split(",")[1];
      const preview = document.createElement("canvas");
      preview.width = 1600;
      preview.height = 1200;
      preview.getContext("2d").drawImage(canvas, 0, 0, 1600, 1200);
      return {
        full,
        preview: preview.toDataURL("image/jpeg", 0.9).split(",")[1],
      };
    });
    const full = Buffer.from(photos.full, "base64"),
      small = Buffer.from(photos.preview, "base64");
    const media = {
      original: "actual-original",
      image: "actual-full",
      preview: "actual-preview",
      size: [2000, 1500],
    };
    const reference = {
      id: "a1",
      name: "标准 1",
      enabled: true,
      ordinal: 1,
      media: {
        ...media,
        image: "reference-full",
        preview: "reference-preview",
      },
    };
    const task = {
      id: "image-task",
      name: "图片加载测试",
      revision: 1,
      assets: [reference],
      runs: [],
    };
    let holdSubmit = false,
      releaseSubmit;
    let submits = 0,
      lost = false,
      failPreview = false,
      failFull = false,
      holdFull,
      releaseFull,
      owner = "fixture";
    const requestRuns = new Map();
    const requests = [],
      urls = new Map();
    let resultResponseAt = 0;
    await context.addInitScript(() => {
      window.__revoked = [];
      window.__created = [];
      const create = URL.createObjectURL.bind(URL),
        revoke = URL.revokeObjectURL.bind(URL);
      URL.createObjectURL = (object) => {
        const url = create(object);
        window.__created.push(url);
        return url;
      };
      URL.revokeObjectURL = (url) => {
        window.__revoked.push(url);
        revoke(url);
      };
    });
    const makeRun = (id, status = "running") => ({
      id,
      task_id: task.id,
      revision: 1,
      status,
      phase: status === "running" ? "layout" : "completed",
      created_at: 1,
      decision: "REVIEW_REQUIRED",
      reference,
      actual: media,
    });
    const result = {
      decision: "DIFFERENCES",
      similarity: 80,
      issues: [
        {
          id: 1,
          type: "missing",
          description: "测试差异",
          standardText: "A",
          actualText: "B",
          severity: "high",
          confidence: "",
          actual_box: [0.1, 0.2, 0.3, 0.4],
        },
      ],
    };
    await context.route("**/api/**", async (route) => {
      const req = route.request(),
        u = new URL(req.url()),
        p = u.pathname;
      if (!p.startsWith("/api/")) return route.continue();
      const reply = (value, status = 200) =>
        route.fulfill({
          status,
          contentType: "application/json",
          body: JSON.stringify(value),
        });
      if (p === "/api/auth/status")
        return reply({
          authenticated: !!owner,
          setup_required: false,
          user: {
            id: owner,
            username: owner,
            role: "user",
            permissions: ["inspection"],
          },
          features: {},
          default_user_permissions: [],
        });
      if (p === "/api/auth/logout") {
        owner = "";
        return reply({ status: "ok" });
      }
      if (p.endsWith("/capabilities")) return reply({ enabled: true });
      if (p.includes("/media/")) {
        const sha = p.split("/").pop();
        const data = sha.endsWith("full") ? full : small;
        requests.push({ sha, bytes: data.length });
        urls.set(sha, req.url());
        if (sha === "actual-full" && holdFull)
          await new Promise((resolve) => {
            releaseFull = resolve;
          });
        await new Promise((r) => setTimeout(r, 180));
        if (
          (sha === "actual-preview" && failPreview) ||
          (sha === "actual-full" && failFull)
        )
          return reply({}, 404);
        return route.fulfill({
          contentType: sha.endsWith("full") ? "image/png" : "image/jpeg",
          headers: { "Cache-Control": "private, no-store" },
          body: data,
        });
      }
      if (p === "/api/label-inspection/tasks")
        return reply({
          items: [
            {
              ...task,
              source: "word",
              standard_count: 1,
              run_count: task.runs.length,
              updated_at: 1,
            },
          ],
          next_cursor: null,
        });
      if (p === "/api/label-inspection/tasks/" + task.id) {
        if (task.runs[0]?.result) resultResponseAt = Date.now();
        return reply(task);
      }
      if (p.endsWith("/runs") && req.method() === "POST") {
        submits++;
        task.runs.unshift(makeRun("run-" + submits));
        const requestId = /name="request_id"\r\n\r\n([^\r]+)/.exec(
          req.postDataBuffer().toString(),
        )[1];
        requestRuns.set(requestId, task.runs[0]);
        if (holdSubmit)
          await new Promise((resolve) => {
            releaseSubmit = resolve;
          });
        if (lost) return route.abort("failed");
        return reply(task.runs[0]);
      }
      if (p.includes("/requests/"))
        return reply({
          run: holdSubmit ? null : requestRuns.get(p.split("/").pop()) || null,
        });
      return reply({ items: [] });
    });
    const go = async (run = "") => {
      await page.goto(
        base +
          "/workspace/label-inspection?task=" +
          task.id +
          (run ? "&run=" + run : ""),
      );
      await page
        .getByRole("heading", { name: "实物标签", exact: true })
        .waitFor();
    };
    const image = () => page.locator(".li-actual-panel .li-image img");
    const loaded = async () => {
      await image().waitFor();
      await page.waitForFunction(() => {
        const img = document.querySelector(".li-actual-panel .li-image img");
        return img?.complete && img.naturalWidth > 1;
      });
    };
    const select = async () => {
      await page
        .getByRole("button", { name: "选择标准 1", exact: true })
        .click();
    };
    const upload = async (
      buffer = full,
      name = "actual.png",
      mimeType = "image/png",
    ) => {
      await page
        .getByLabel("上传实物照片")
        .locator("input")
        .setInputFiles({ name, mimeType, buffer });
      await loaded();
    };
    const submit = async () => {
      await page.getByRole("button", { name: "开始检测", exact: true }).click();
      await page.waitForURL(/run=run-/);
      await loaded();
    };
    await go();
    await select();
    await upload();
    await image().evaluate((img) => {
      window.__photoNode = img;
      window.__photoSrc = img.src;
    });
    const submittedAt = Date.now();
    await submit();
    const submissionToImageReadyMs = Date.now() - submittedAt;
    if (!baseline) {
      assert.ok(
        await image().evaluate(
          (img) => img === window.__photoNode && img.src === window.__photoSrc,
        ),
      );
      assert.equal(
        requests.filter((r) => r.sha.startsWith("actual")).length,
        0,
      );
    }
    task.runs[0] = {
      ...task.runs[0],
      status: "completed",
      phase: "completed",
      decision: "DIFFERENCES",
      result,
      crop: [0, 0, 1200, 900],
    };
    await page.locator(".li-actual-panel .li-box-number").waitFor();
    await loaded();
    const metrics = {
      baseline,
      imageBytes: full.length,
      previewBytes: small.length,
      submissionToImageReadyMs,
      resultResponseToOverlayReadyMs: Date.now() - resultResponseAt,
      actualMediaRequests: requests.filter((r) => r.sha.startsWith("actual")),
    };
    fs.writeFileSync(
      path.join(output, "metrics.json"),
      JSON.stringify(metrics, null, 2),
    );
    if (baseline) {
      console.log("BASELINE " + JSON.stringify(metrics));
      return;
    }
    assert.ok(
      await image().evaluate(
        (img) => img === window.__photoNode && img.src === window.__photoSrc,
      ),
    );
    assert.equal(metrics.actualMediaRequests.length, 0);
    await page
      .getByRole("button", { name: "查看异常 1 详情", exact: true })
      .click();
    await page.getByRole("button", { name: "关闭详情" }).click();
    assert.ok(await image().evaluate((img) => img === window.__photoNode));
    await page.getByRole("button", { name: "放大实物图", exact: true }).click();
    await page.getByRole("dialog").waitFor();
    await page.keyboard.press("Escape");
    assert.equal(requests.filter((r) => r.sha.startsWith("actual")).length, 0);
    await page.screenshot({ path: path.join(output, "local-result.png") });
    // Leaving the run in the SPA releases its blob and never reuses it for another run.
    const localURL = await image().getAttribute("src");
    await page
      .getByRole("button", { name: "返回任务详情", exact: true })
      .click();
    await page.waitForFunction(
      (url) => window.__revoked.includes(url),
      localURL,
    );
    await go("run-1");
    await loaded();
    assert.ok((await image().getAttribute("src")).endsWith("actual-preview"));
    assert.equal(requests.filter((r) => r.sha === "actual-full").length, 0);
    // Refreshing an active historical run loads one preview; completion changes only overlays.
    task.runs[0] = {
      ...task.runs[0],
      status: "running",
      phase: "compare",
      result: null,
    };
    await page.reload();
    await loaded();
    const historyRequests = requests.filter((r) =>
      r.sha.startsWith("actual"),
    ).length;
    await image().evaluate((img) => (window.__historyNode = img));
    task.runs[0] = {
      ...task.runs[0],
      status: "completed",
      phase: "completed",
      result,
    };
    await page.locator(".li-actual-panel .li-box-number").waitFor();
    assert.ok(await image().evaluate((img) => img === window.__historyNode));
    assert.equal(
      requests.filter((r) => r.sha.startsWith("actual")).length,
      historyRequests,
    );
    // Slow full-size loading preserves a visible preview; failure supports explicit retry.
    holdFull = true;
    failFull = true;
    await page.getByRole("button", { name: "放大实物图", exact: true }).click();
    await page.getByText("正在加载高清图…").waitFor();
    assert.ok(
      await page.getByRole("dialog").getByAltText("图片预览").isVisible(),
    );
    await page.waitForFunction(
      () => document.querySelector(".li-zoom-images img")?.complete,
    );
    for (let i = 0; i < 100 && !releaseFull; i++)
      await new Promise((r) => setTimeout(r, 20));
    assert.ok(releaseFull);
    releaseFull();
    holdFull = false;
    await page.getByRole("button", { name: "重试高清图" }).waitFor();
    failFull = false;
    await page.getByRole("button", { name: "重试高清图" }).click();
    await page
      .getByRole("dialog")
      .getByAltText("原尺寸图片")
      .waitFor({ state: "visible" });
    await page.keyboard.press("Escape");
    failPreview = true;
    const beforeFallback = requests.filter(
      (r) => r.sha === "actual-full",
    ).length;
    await page.reload();
    await loaded();
    assert.ok((await image().getAttribute("src")).endsWith("actual-full"));
    assert.equal(
      requests.filter((r) => r.sha === "actual-full").length,
      beforeFallback + 1,
    );
    failFull = true;
    await page.reload();
    await page.getByText("图片缺失或无法读取", { exact: true }).waitFor();
    const failedCount = requests.length;
    await page.waitForTimeout(350);
    assert.equal(requests.length, failedCount);
    failPreview = false;
    failFull = false;
    // Lost upload acknowledgement uses the same request; local file and node survive recovery.
    await go();
    await select();
    await upload();
    lost = true;
    await submit();
    lost = false;
    assert.equal(submits, 2);
    assert.ok((await image().getAttribute("src")).startsWith("blob:"));
    task.runs[0] = {
      ...task.runs[0],
      status: "completed",
      phase: "completed",
      decision: "DIFFERENCES",
      result,
    };
    await page.locator(".li-actual-panel .li-box-number").waitFor();
    await page.getByRole("button", { name: "检测下一件", exact: true }).click();
    assert.equal(await image().count(), 0);
    // Replacement and camera capture use the same lifetime rules.
    await upload();
    const replaced = await image().getAttribute("src");
    await upload(small, "new.jpg", "image/jpeg");
    await page.waitForFunction(
      (url) => window.__revoked.includes(url),
      replaced,
    );
    await page
      .getByRole("button", { name: "开启摄像头 / 重拍", exact: true })
      .click();
    await page.getByRole("button", { name: "拍照", exact: true }).click();
    await loaded();
    await image().evaluate((img) => (window.__cameraNode = img));
    await submit();
    assert.ok(await image().evaluate((img) => img === window.__cameraNode));
    task.runs[0] = {
      ...task.runs[0],
      status: "completed",
      phase: "completed",
      result,
    };
    // Invalid local image can still display a server preview after successful upload.
    await go();
    await select();
    await page
      .getByLabel("上传实物照片")
      .locator("input")
      .setInputFiles({
        name: "invalid.png",
        mimeType: "image/png",
        buffer: Buffer.from("invalid image fixture"),
      });
    await page.getByText("图片缺失或无法读取").waitFor();
    await submit();
    assert.ok((await image().getAttribute("src")).endsWith("actual-preview"));
    task.runs[0] = {
      ...task.runs[0],
      status: "completed",
      phase: "completed",
      result,
    };
    // Same-tab task/history navigation and mobile overlays never display a previous blob.
    await go("run-1");
    await loaded();
    await page.setViewportSize({ width: 390, height: 844 });
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth > innerWidth + 1,
      ),
      false,
    );
    await page.getByRole("tab", { name: "实物", exact: true }).click();
    await loaded();
    await page.screenshot({ path: path.join(output, "history-mobile.png") });
    // JPEG EXIF orientations 1..8, including mirrored cases, must use the same
    // oriented pixels and normalized marker geometry as server-normalized images.
    await page.setViewportSize({ width: 1440, height: 900 });
    const quadrant = Buffer.from(
      await page.evaluate(() => {
        const c = document.createElement("canvas");
        c.width = 80;
        c.height = 40;
        const ctx = c.getContext("2d");
        ["#ff0000", "#00ff00", "#0000ff", "#ffff00"].forEach((color, i) => {
          ctx.fillStyle = color;
          ctx.fillRect((i % 2) * 40, Math.floor(i / 2) * 20, 40, 20);
        });
        return c.toDataURL("image/jpeg", 1).split(",")[1];
      }),
      "base64",
    );
    const topLeft = [
      [255, 0, 0],
      [0, 255, 0],
      [255, 255, 0],
      [0, 0, 255],
      [255, 0, 0],
      [0, 0, 255],
      [255, 255, 0],
      [0, 255, 0],
    ];
    for (let orientation = 1; orientation <= 8; orientation++) {
      const exif = Buffer.from(
        "45786966000049492a0008000000010012010300010000000100000000000000",
        "hex",
      );
      exif.writeUInt16LE(orientation, 24);
      const marker = Buffer.alloc(4);
      marker.writeUInt16BE(0xffe1);
      marker.writeUInt16BE(exif.length + 2, 2);
      const jpeg = Buffer.concat([
        quadrant.subarray(0, 2),
        marker,
        exif,
        quadrant.subarray(2),
      ]);
      media.size = orientation >= 5 ? [40, 80] : [80, 40];
      await go();
      await select();
      await upload(jpeg, `orientation-${orientation}.jpg`, "image/jpeg");
      const pixels = await image().evaluate((img) => {
        const c = document.createElement("canvas");
        c.width = img.naturalWidth;
        c.height = img.naturalHeight;
        const ctx = c.getContext("2d");
        ctx.drawImage(img, 0, 0);
        return {
          size: [img.naturalWidth, img.naturalHeight],
          rgb: [...ctx.getImageData(5, 5, 1, 1).data].slice(0, 3),
        };
      });
      assert.deepEqual(pixels.size, media.size);
      assert.ok(
        pixels.rgb.every(
          (v, i) => Math.abs(v - topLeft[orientation - 1][i]) < 20,
        ),
      );
      await submit();
      task.runs[0] = {
        ...task.runs[0],
        status: "completed",
        phase: "completed",
        result,
      };
      await page.locator(".li-actual-panel .li-box-number").waitFor();
      const alignment = await page
        .locator(".li-actual-panel .li-image")
        .evaluate((button) => {
          const image = button.querySelector("img").getBoundingClientRect();
          const box = button.querySelector("svg rect").getBoundingClientRect();
          return [
            (box.x - image.x) / image.width,
            (box.y - image.y) / image.height,
            box.width / image.width,
            box.height / image.height,
          ];
        });
      assert.ok(
        alignment.every((v, i) => Math.abs(v - [0.1, 0.2, 0.3, 0.4][i]) < 0.01),
      );
    }
    const oldOwnerURL = await image().getAttribute("src");
    owner = "second-fixture";
    await page.evaluate(() =>
      window.dispatchEvent(new Event("visibilitychange")),
    );
    await page.waitForFunction(
      (url) => window.__revoked.includes(url),
      oldOwnerURL,
    );
    await loaded();
    assert.ok(!(await image().getAttribute("src")).startsWith("blob:"));
    await page
      .getByRole("button", { name: "返回任务详情", exact: true })
      .click();
    await select();
    await upload(small, "logout.jpg", "image/jpeg");
    const abandonedURL = await image().getAttribute("src");
    holdSubmit = true;
    await page.getByRole("button", { name: "开始检测", exact: true }).click();
    for (let i = 0; i < 100 && !releaseSubmit; i++)
      await new Promise((r) => setTimeout(r, 20));
    assert.ok(releaseSubmit);
    assert.ok(
      await page
        .getByRole("button", { name: "开启摄像头 / 重拍", exact: true })
        .isDisabled(),
    );
    await page.getByRole("link", { name: "文字检验", exact: true }).click();
    await page
      .getByRole("heading", { name: "检测任务", exact: true })
      .waitFor();
    await page.waitForFunction(
      (url) => window.__revoked.includes(url),
      abandonedURL,
    );
    const uploadDone = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        response.url().endsWith("/runs"),
    );
    task.runs[0] = {
      ...task.runs[0],
      status: "completed",
      phase: "completed",
      result,
    };
    holdSubmit = false;
    releaseSubmit();
    await uploadDone;
    await page.waitForTimeout(250);
    assert.equal(new URL(page.url()).search, "");
    await go("run-1");
    await loaded();
    await page.getByRole("tab", { name: /^历史记录/ }).click();
    await page.locator(".li-history button").first().click();
    await page.getByRole("tab", { name: /^历史记录/ }).click();
    await page.locator(".li-history button").last().click();
    await loaded();
    assert.ok(!(await image().getAttribute("src")).startsWith("blob:"));
    await page
      .getByRole("button", { name: "返回任务详情", exact: true })
      .click();
    await select();
    await upload(small, "logout.jpg", "image/jpeg");
    const logoutURL = await image().getAttribute("src");
    await page.getByRole("button", { name: "更多操作", exact: true }).click();
    await page.getByRole("button", { name: "退出登录", exact: true }).click();
    await page.waitForURL(/\/login/);
    assert.ok(
      await page.evaluate((url) => window.__revoked.includes(url), logoutURL),
    );
    assert.deepEqual(errors, []);
    console.log(
      "label image reuse PASS " +
        JSON.stringify(metrics) +
        "; artifacts: " +
        output,
    );
  } catch (error) {
    if (browser) {
      const page = browser.contexts()[0]?.pages()[0];
      if (page) {
        console.error(await page.locator("body").innerText());
        await page.screenshot({ path: path.join(output, "failure.png") });
      }
    }
    throw error;
  } finally {
    if (browser) await browser.close();
    vite.kill();
  }
}
module.exports = main;
if (require.main === module)
  main().catch((e) => {
    console.error(e);
    process.exitCode = 1;
  });
