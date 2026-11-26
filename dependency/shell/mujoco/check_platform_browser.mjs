// Browser verification against an isolated, temporary portal. No live accounts.
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawn, spawnSync } from "node:child_process";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../logic/mujoco");
const output = path.join(root, "artifacts", "platform_validation", "browser-" + Date.now());
await fs.mkdir(output, { recursive: true });
const python = path.join(root, ".venv", "Scripts", "python.exe");
const port = 8766;
const url = `http://127.0.0.1:${port}`;
const server = spawn(
    python,
    [
        "-c",
        "import sys;from pathlib import Path;import uvicorn;from embodied_arena.platform.app import create_app;from embodied_arena.platform.settings import Settings;uvicorn.run(create_app(Settings(data=Path(sys.argv[1]),practice_duration=1.0)),host='127.0.0.1',port=8766,proxy_headers=False)",
        path.join(output, "data"),
    ],
    { cwd: root, windowsHide: true, stdio: ["ignore", "ignore", "pipe"] },
);
let serverErrors = "";
server.stderr.on("data", (x) => {
    serverErrors = (serverErrors + x.toString()).slice(-20000);
});
const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const checks = [],
    errors = [];
let browser, ws, debugCommand;
let sequence = 0;
const pending = new Map();
const password = "browser-validation-only";
function assert(test, label) {
    if (!test) throw new Error(label);
    checks.push(label);
    console.log(label);
}
try {
    for (let i = 0; i < 40; i++) {
        try {
            if ((await fetch(url + "/api/status")).ok) break;
        } catch {}
        await pause(250);
    }
    const fixture = path.join(output, "submission.zip");
    const fixtureResult = spawnSync(
        python,
        [
            "-c",
            "import sys;from pathlib import Path;from embodied_arena.platform.packages import template_zip;Path(sys.argv[1]).write_bytes(template_zip('arena-python-v1'))",
            fixture,
        ],
        { cwd: root, windowsHide: true },
    );
    if (fixtureResult.status !== 0) throw new Error(fixtureResult.stderr.toString());
    browser = spawn(
        "C:/Program Files/Google/Chrome/Application/chrome.exe",
        [
            "--headless=new",
            "--disable-gpu",
            "--no-first-run",
            "--no-default-browser-check",
            "--remote-debugging-port=0",
            `--user-data-dir=${path.join(output, "chrome-profile")}`,
            "about:blank",
        ],
        { windowsHide: true, stdio: ["ignore", "ignore", "pipe"] },
    );
    const endpoint = await new Promise((resolve, reject) => {
        let logs = "";
        const timer = setTimeout(() => reject(new Error("Browser startup timeout")), 15000);
        browser.once("error", reject);
        browser.stderr.on("data", (chunk) => {
            logs += chunk.toString();
            const m = logs.match(/DevTools listening on (ws:\/\/[^\s]+)/);
            if (m) {
                clearTimeout(timer);
                resolve(m[1]);
            }
        });
    });
    ws = new WebSocket(endpoint);
    await new Promise((resolve, reject) => {
        ws.addEventListener("open", resolve, { once: true });
        ws.addEventListener("error", reject, { once: true });
    });
    ws.addEventListener("message", (event) => {
        const m = JSON.parse(event.data);
        if (m.method === "Runtime.exceptionThrown")
            errors.push(
                m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text,
            );
        if (m.id && pending.has(m.id)) {
            const item = pending.get(m.id);
            pending.delete(m.id);
            clearTimeout(item.timer);
            m.error ? item.reject(new Error(JSON.stringify(m.error))) : item.resolve(m.result);
        }
    });
    function send(method, params = {}, sessionId) {
        const id = ++sequence;
        return new Promise((resolve, reject) => {
            const timer = setTimeout(() => {
                pending.delete(id);
                reject(new Error("CDP timeout: " + method));
            }, 15000);
            pending.set(id, { resolve, reject, timer });
            ws.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }));
        });
    }
    const { browserContextId } = await send("Target.createBrowserContext", {
        disposeOnDetach: true,
    });
    const { targetId } = await send("Target.createTarget", {
        url: "about:blank",
        browserContextId,
    });
    const { sessionId } = await send("Target.attachToTarget", { targetId, flatten: true });
    const command = (method, params) => send(method, params, sessionId);
    debugCommand = command;
    await command("Page.enable");
    await command("Runtime.enable");
    await command("DOM.enable");
    await command("Emulation.setDeviceMetricsOverride", {
        width: 1440,
        height: 1080,
        deviceScaleFactor: 1,
        mobile: false,
    });
    await command("Page.navigate", { url });
    async function evaluate(expression) {
        const result = await command("Runtime.evaluate", {
            expression,
            returnByValue: true,
            awaitPromise: true,
        });
        if (result.exceptionDetails)
            throw new Error(
                result.exceptionDetails.exception?.description || result.exceptionDetails.text,
            );
        return result.result.value;
    }
    const js = (code) => evaluate(`(()=>{const q=s=>document.querySelector(s);${code}})()`);
    async function until(expression, label, timeout = 60000) {
        const end = Date.now() + timeout;
        while (Date.now() < end) {
            if (await evaluate(expression)) {
                checks.push(label);
                console.log(label);
                return;
            }
            await pause(300);
        }
        throw new Error("Timed out: " + label);
    }
    async function screenshot(name) {
        const shot = await command("Page.captureScreenshot", {
            format: "png",
            captureBeyondViewport: true,
        });
        await fs.writeFile(path.join(output, name + ".png"), Buffer.from(shot.data, "base64"));
    }
    async function click(selector) {
        await js(
            `const e=q(${JSON.stringify(selector)});if(!e)throw new Error('Missing element '+${JSON.stringify(selector)});e.click();`,
        );
    }
    async function fields(values) {
        await js(
            Object.entries(values)
                .map(
                    ([selector, value]) =>
                        `q(${JSON.stringify(selector)}).value=${JSON.stringify(value)};`,
                )
                .join(""),
        );
    }
    async function submit(id) {
        await js(`q(${JSON.stringify("#" + id)}).requestSubmit();`);
    }
    await until(
        "document.querySelector('#auth-form')!==null",
        "Initial administrator setup page is usable",
        15000,
    );
    await screenshot("setup-desktop");
    await fields({ "[name=username]": "browser_admin", "[name=password]": password });
    await submit("auth-form");
    await until(
        "Boolean(document.querySelector('.shell'))",
        "Browser creates administrator and opens the real workbench",
    );
    await screenshot("workbench-empty");
    await click("[data-view=admin]");
    await click("[data-admin-tab=environment]");
    await click("[data-action=deploy-runtime]");
    await until(
        "document.querySelector('#deployment-detail')?.textContent.includes('自检通过')",
        "Administrator one-click deploy runs the real simulation check",
        120000,
    );
    await screenshot("one-click-deployment");
    await click("[data-view=admin]");
    await click("[data-admin-tab=invites]");
    await fields({ "[name=uses]": "2" });
    await submit("invite-form");
    await until(
        "Boolean(document.querySelector('#invite-code'))",
        "Administrator generates an actual invitation",
    );
    const invite = await evaluate("document.querySelector('#invite-code').value");
    await click("[data-action=logout]");
    await until(
        "Boolean(document.querySelector('[data-auth=register]'))",
        "Logout returns to authentication before registering a contestant",
    );
    await click("[data-auth=register]");
    await fields({
        "[name=invite]": invite,
        "[name=username]": "browser_player",
        "[name=password]": password,
    });
    await submit("auth-form");
    await until(
        "Boolean(document.querySelector('#upload-form'))",
        "Invite registration opens contestant upload page",
    );
    assert(
        await evaluate("!document.querySelector('[data-view=admin]')"),
        "Contestant navigation does not retain administrator controls",
    );
    await fields({ "#upload-form [name=name]": "城市搜索 · 浏览器验证" });
    await js("q('#upload-form [name=auto_practice]').checked=true;");
    const documentNode = await command("DOM.getDocument", { depth: 0 });
    const fileNode = await command("DOM.querySelector", {
        nodeId: documentNode.root.nodeId,
        selector: "#zip-file",
    });
    await command("DOM.setFileInputFiles", { nodeId: fileNode.nodeId, files: [fixture] });
    await submit("upload-form");
    await until(
        "document.querySelector('#upload-status')?.textContent.includes('已保存')",
        "Actual ZIP upload reports saved immutable version",
    );
    await until(
        "document.querySelector('#submission-report')?.textContent.includes('接口通过')",
        "Browser displays real isolated runtime check success",
    );
    await screenshot("workbench-submission");
    await click("[data-view=practice]");
    await until(
        "document.querySelector('#practice-jobs')?.textContent.includes('已完成')",
        "Browser launches and completes a real cyber-city practice",
        90000,
    );
    await screenshot("practice-completed");
    await click("[data-watch]");
    await until(
        "document.querySelector('#replay-image')?.complete&&document.querySelector('#replay-image')?.naturalWidth>0",
        "Actual simulation replay image renders in browser",
    );
    await click("#replay-play");
    await pause(650);
    assert(
        await evaluate("Number(document.querySelector('#replay-slider').value)>0"),
        "Replay playback advances the time slider",
    );
    await screenshot("replay-city");
    await click("#close-dialog");
    await click("[data-view=competition]");
    await submit("entry-form");
    await until(
        "document.querySelector('#entry-panel')?.textContent.includes('参赛版本已锁定')",
        "Official registration visibly locks the tested version",
    );
    await screenshot("official-entry");
    await click("[data-view=docs]");
    assert(
        await evaluate(
            "document.querySelector('#main-content').textContent.includes('joint_targets')&&document.querySelector('#main-content').textContent.includes('reset_count')",
        ),
        "Interface documentation exposes the actual contract and reset behavior",
    );
    await screenshot("interface-docs");

    await click("[data-action=logout]");
    await until(
        "Boolean(document.querySelector('[data-auth=register]'))",
        "First contestant can end the session cleanly",
    );
    await click("[data-auth=register]");
    await fields({
        "[name=invite]": invite,
        "[name=username]": "browser_beta",
        "[name=password]": password,
    });
    await submit("auth-form");
    await until(
        "Boolean(document.querySelector('#upload-form'))",
        "Second contestant can register independently",
    );
    await fields({ "#upload-form [name=name]": "第二名选手策略" });
    const doc2 = await command("DOM.getDocument", { depth: 0 });
    const input2 = await command("DOM.querySelector", {
        nodeId: doc2.root.nodeId,
        selector: "#zip-file",
    });
    await command("DOM.setFileInputFiles", { nodeId: input2.nodeId, files: [fixture] });
    await submit("upload-form");
    await until(
        "document.querySelector('#submission-report')?.textContent.includes('接口通过')",
        "Second contestant version passes actual runtime checks",
    );
    await click("[data-view=competition]");
    await submit("entry-form");
    await until(
        "document.querySelector('#entry-panel')?.textContent.includes('参赛版本已锁定')",
        "Second contestant locks an independent entry",
    );

    const geometry = [];
    for (const width of [1440, 1024, 390, 320]) {
        await command("Emulation.setDeviceMetricsOverride", {
            width,
            height: 1100,
            deviceScaleFactor: 1,
            mobile: false,
        });
        for (const view of ["submissions", "practice", "competition", "results", "docs"]) {
            await click(`[data-view=${view}]`);
            await pause(100);
            const size = await evaluate(
                "({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,overflow:[...document.querySelectorAll('body *')].filter(e=>{const r=e.getBoundingClientRect();return r.width>0&&r.right>innerWidth+1&&!e.closest('.table-wrap')&&!e.closest('dialog:not([open])')}).map(e=>e.tagName+'#'+e.id)})",
            );
            geometry.push({ width, view, ...size });
            assert(
                size.scrollWidth <= size.width + 1 && size.overflow.length === 0,
                `${width}px contestant/${view} fits without page overflow`,
            );
        }
        if (width === 390) await screenshot("mobile-docs");
    }
    await command("Emulation.setDeviceMetricsOverride", {
        width: 1440,
        height: 1080,
        deviceScaleFactor: 1,
        mobile: false,
    });
    await click("[data-action=logout]");
    await until(
        "Boolean(document.querySelector('#auth-form'))",
        "Contestant logout returns to login",
    );
    assert(
        await evaluate("!document.querySelector('#dialog-body').textContent"),
        "Logout clears private modal contents",
    );
    await fields({ "[name=username]": "browser_admin", "[name=password]": password });
    await submit("auth-form");
    await until(
        "Boolean(document.querySelector('[data-view=admin]'))",
        "Administrator signs back into the correct role",
    );
    await click("[data-view=admin]");
    await until(
        "Boolean(document.querySelector('#schedule-form'))",
        "Administrator sees both real eligible entries",
    );
    await fields({ "#schedule-form [name=duration]": "1", "#schedule-form [name=scene]": "room" });
    await submit("schedule-form");
    await until(
        "Boolean(document.querySelector('[data-publish]'))",
        "Administrator schedules an actual two-player official match",
        90000,
    );
    await click("[data-publish]");
    await until(
        "document.querySelector('#admin-jobs')?.textContent.includes('正式成绩已发布')",
        "Administrator publishes real official scores and replay",
    );
    await screenshot("admin-queue");
    for (const tab of ["queue", "invites", "users", "environment", "requests"]) {
        await click(`[data-admin-tab=${tab}]`);
        assert(
            await evaluate("Boolean(document.querySelector('#main-content h1'))"),
            "Administrator " + tab + " page opens",
        );
    }
    await click("[data-admin-tab=environment]");
    await click("[data-action=refresh-node]");
    await until(
        "!document.querySelector('[data-action=refresh-node]')?.disabled&&document.querySelector('#environment-detail')?.textContent.includes('就绪')",
        "Runtime availability refresh reaches the real Docker node",
    );
    assert(errors.length === 0, "No browser JavaScript exceptions were observed");
    const report = {
        scope: "real browser against isolated portal data; live data unchanged",
        passed: checks.length,
        checks,
        errors,
        geometry,
        output,
    };
    await fs.writeFile(
        path.join(root, "artifacts", "platform_validation", "browser.json"),
        JSON.stringify(report, null, 2),
    );
    console.log(JSON.stringify({ passed: checks.length, output }));
    await command("Page.close").catch(() => {});
} catch (error) {
    let page;
    if (debugCommand) {
        page = await debugCommand("Runtime.evaluate", {
            expression:
                "({url:location.href,text:document.body?.innerText,html:document.documentElement.outerHTML.slice(0,3000)})",
            returnByValue: true,
        }).catch(() => null);
        const shot = await debugCommand("Page.captureScreenshot", {
            format: "png",
            captureBeyondViewport: true,
        }).catch(() => null);
        if (shot)
            await fs.writeFile(path.join(output, "failure.png"), Buffer.from(shot.data, "base64"));
    }
    await fs.writeFile(
        path.join(output, "failure.json"),
        JSON.stringify({ checks, errors, error: String(error), serverErrors, page }, null, 2),
    );
    console.error(error);
    process.exitCode = 1;
} finally {
    for (const p of pending.values()) clearTimeout(p.timer);
    ws?.close();
    browser?.kill();
    server.kill();
}
