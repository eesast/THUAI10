"use strict";

const app = document.getElementById("app");
const notice = document.getElementById("notice");
const dialog = document.getElementById("detail-dialog");
const state = {
    me: null,
    epoch: 0,
    view: "submissions",
    adminTab: "queue",
    env: null,
    deployment: null,
    tournaments: [],
    runtimes: null,
    operations: null,
    submissions: [],
    jobs: [],
    entries: [],
    board: [],
    requests: [],
    users: [],
    invites: [],
    selectedSubmission: null,
    busy: false,
    authMode: "login",
    setup: false,
    watch: null,
    playing: false,
    frameIndex: 0,
};
let noticeTimer, pollTimer, playTimer;
const esc = (value) =>
    String(value ?? "").replace(
        /[&<>"']/g,
        (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c],
    );
const date = (value) =>
    value ? new Date(value * 1000).toLocaleString("zh-CN", { hour12: false }) : "—";
const version = (row) => `V${String(row.revision).padStart(3, "0")}`;
const own = () => state.submissions.filter((s) => s.user_id === state.me.id);
const ready = () => own().filter((s) => s.state === "ready");
const titles = {
    submissions: "我的策略",
    practice: "练习中心",
    competition: "正式比赛",
    results: "成绩与回放",
    docs: "接口与环境",
    admin: "比赛管理",
    league: "赛事与总榜",
    operations: "后台维护",
};
const labels = {
    waiting_check: "等待运行检查",
    checking: "运行检查中",
    static_failed: "静态检查失败",
    check_failed: "运行检查失败",
    ready: "接口通过",
    queued: "排队中",
    waiting_node: "等待执行环境",
    preparing: "准备环境",
    running: "仿真运行中",
    completed: "已完成",
    failed: "运行失败",
    cancelled: "已取消",
    passed: "通过",
    waiting: "等待检查",
};
const statusBadge = (value) =>
    `<span class="badge ${["ready", "passed", "completed"].includes(value) ? "good" : ["static_failed", "check_failed", "failed"].includes(value) ? "bad" : ["queued", "waiting_node", "preparing", "checking", "waiting_check", "waiting"].includes(value) ? "wait" : "neutral"}">${esc(labels[value] || value)}</span>`;
const empty = (title, text = "") =>
    `<div class="empty"><h3>${esc(title)}</h3><p>${esc(text)}</p></div>`;
const options = (rows, same = false) =>
    `${same ? '<option value="">与主测版本相同</option>' : ""}${rows.map((s) => `<option value="${esc(s.id)}">${esc(version(s) + " · " + s.name)}</option>`).join("")}`;

function toast(message, error = false) {
    clearTimeout(noticeTimer);
    notice.textContent = message;
    notice.className = error ? "error" : "";
    notice.hidden = false;
    noticeTimer = setTimeout(() => {
        notice.hidden = true;
    }, 5500);
}
function readableError(data) {
    if (typeof data?.detail === "string") return data.detail;
    if (Array.isArray(data?.detail)) {
        const field = data.detail[0]?.loc?.at(-1);
        return (
            {
                password: "密码需要 10–128 个字符。",
                username: "账号需要 3–24 位字母、数字或下划线。",
                invite: "请填写完整的邀请码。",
                duration: "比赛时长需要在 1–120 秒之间。",
            }[field] || "提交的内容格式不正确，请检查必填项。"
        );
    }
    return "操作未完成，请稍后重试。";
}
async function api(path, { method = "GET", body } = {}) {
    const headers = {};
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (method !== "GET" && state.me) headers["X-CSRF-Token"] = state.me.csrf;
    const response = await fetch("/api" + path, {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
        credentials: "same-origin",
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
        const error = new Error(readableError(data));
        error.status = response.status;
        throw error;
    }
    return data;
}
function brand() {
    return '<div class="brand"><span class="brand-mark" aria-hidden="true"></span><div><div class="brand-name">THUAI10 · MuJoCo</div><div class="brand-subtitle">EMBODIED COMPETITION</div></div></div>';
}
function authScreen() {
    clearInterval(pollTimer);
    const register = state.authMode === "register" && !state.setup;
    app.innerHTML = `<main class="auth-shell"><section class="auth-art">${brand()}<div><span class="eyebrow">YOUR INTELLIGENCE. A NEW WORLD.</span><h1>让你的机器人，<br>走进这座城市。</h1><p>把视觉理解、运动控制和决策，放进同一个真实物理世界。提交你的策略，开始下一场探索。</p><div class="row spacer"><span class="badge">MuJoCo</span><span class="badge">G1 · 29 DoF</span><span class="badge">RGB-D 视觉</span></div></div><p class="small">统一机器人与运行环境 · 离线推理 · 可追溯的比赛记录</p></section><section class="auth-form-wrap"><div class="auth-form stack"><div class="tight"><span class="eyebrow">${state.setup ? "FIRST LAUNCH" : "COMPETITOR PORTAL"}</span><h2>${state.setup ? "创建管理员" : register ? "加入竞技场" : "欢迎回来"}</h2><p class="muted small">${state.setup ? "首次启动，请在服务器本机设置管理员账号。没有默认密码。" : register ? "使用管理员提供的邀请码创建选手账号。" : "登录后管理策略、发起练习和查看比赛。"}</p></div>${!state.setup ? `<div class="segmented" aria-label="登录或注册"><button type="button" data-auth="login" aria-pressed="${!register}">登录</button><button type="button" data-auth="register" aria-pressed="${register}">邀请码注册</button></div>` : ""}<form id="auth-form" class="stack">${register ? '<label class="field">邀请码<input class="input" name="invite" required autocomplete="off" placeholder="管理员提供的 NEON-…"></label>' : ""}<label class="field">账号<input class="input" name="username" pattern="[a-zA-Z0-9_]{3,24}" minlength="3" maxlength="24" required autocomplete="username" placeholder="3–24 位字母、数字或下划线"></label><label class="field">密码<input class="input" type="password" name="password" minlength="10" maxlength="128" required autocomplete="${state.setup || register ? "new-password" : "current-password"}" placeholder="至少 10 个字符"></label><p id="auth-error" class="form-error" role="alert" hidden></p><button class="button primary" type="submit">${state.setup ? "创建管理员并进入平台" : register ? "注册并进入平台" : "登录工作台"}</button></form><p class="auth-footer">代码、模型和练习记录仅本人及管理员可见。正式成绩与回放由管理员发布后，对平台内选手开放。</p></div></section></main>`;
}
function nav() {
    const symbols = {
        submissions: "◇",
        practice: "▷",
        competition: "◎",
        results: "▥",
        docs: "≡",
        admin: "⚙",
        league: "◈",
        operations: "☷",
    };
    return Object.entries(titles)
        .filter(([key]) => !["admin", "operations"].includes(key) || state.me.role === "admin")
        .map(
            ([key, title]) =>
                `${key === "admin" ? '<div class="nav-section">ORGANIZER</div>' : ""}<button type="button" data-view="${key}" ${state.view === key ? 'aria-current="page"' : ""}><span class="nav-icon" aria-hidden="true">${symbols[key]}</span>${title}</button>`,
        )
        .join("");
}
function nodeBadge() {
    return `<span class="badge ${state.env?.node?.ready ? "good" : "wait"}">${state.env?.node?.ready ? "执行环境就绪" : "执行环境待就绪"}</span>`;
}
function render() {
    if (!state.me) return authScreen();
    app.innerHTML = `<div class="shell"><aside class="sidebar" id="sidebar">${brand()}<nav class="nav" aria-label="主导航">${nav()}</nav><div class="sidebar-foot"><p>统一环境 · 局域网平台</p><p>MuJoCo / API v1</p><p class="spacer">策略决定表现，裁判记录过程。</p></div></aside><div class="workspace"><header class="topbar"><button class="icon-button" id="mobile-menu" type="button" aria-label="展开导航" aria-controls="sidebar" aria-expanded="false">≡</button><span class="topbar-title">选手平台 / ${esc(titles[state.view])}</span><span id="node-badge">${nodeBadge()}</span><div class="identity"><span class="avatar" aria-hidden="true">${esc(state.me.username.slice(0, 1).toUpperCase())}</span><div><div>${esc(state.me.username)}</div><div class="small muted">${state.me.role === "admin" ? "管理员" : "参赛选手"}</div></div></div><button class="logout" type="button" data-action="logout">退出</button></header><main class="content" id="main-content">${viewHTML()}</main></div></div>`;
}
function heading(title, text, action = "") {
    return `<div class="page-heading row between"><div><h1>${esc(title)}</h1><p>${esc(text)}</p></div>${action}</div>`;
}
function reportHTML() {
    const row = state.submissions.find((s) => s.id === state.selectedSubmission) || own()[0];
    if (!row)
        return '<p class="muted">上传后显示目录、清单、语法和运行检查结果。</p><div class="callout">静态检查不会执行代码。运行检查通过后，才能练习或报名。</div>';
    return `<div class="row between"><span>${esc(version(row) + " · " + row.name)}</span>${statusBadge(row.state)}</div><ul class="check-list">${row.report.map((r) => `<li class="${esc(r.state)}"><span>${esc(r.name)}</span>${statusBadge(r.state)}<span class="detail">${esc(r.detail)}</span></li>`).join("")}</ul><p class="small muted">SHA-256 <span class="mono">${esc(row.sha256.slice(0, 16))}…</span></p>${row.state === "ready" && row.user_id === state.me.id ? (row.report.some((r) => r.detail?.includes("已自动加入城市练习队列")) ? `<button type="button" class="button" data-view="practice">查看自动练习与结果</button>` : `<button type="button" class="button" data-practice-version="${row.id}">用此版本练习</button>`) : ""}`;
}
function versionsHTML() {
    const rows = state.submissions;
    if (!rows.length)
        return empty("还没有提交版本", "下载模板，把你的策略和离线权重一起打包上传。");
    return `<div class="table-wrap"><table class="table"><thead><tr><th>版本 / 策略</th>${state.me.role === "admin" ? "<th>选手</th>" : ""}<th>检查状态</th><th>提交时间</th><th>操作</th></tr></thead><tbody>${rows.map((s) => `<tr><td><span class="mono">${version(s)}</span> · ${esc(s.name)}<div class="small muted">${(s.bytes / 1024 ** 2).toFixed(2)} MB</div></td>${state.me.role === "admin" ? `<td>${esc(s.username)}</td>` : ""}<td>${statusBadge(s.state)}</td><td class="small nowrap">${date(s.created)}</td><td><div class="row"><button type="button" class="button ghost" data-report="${s.id}">检查报告</button>${["check_failed", "waiting_check"].includes(s.state) ? `<button type="button" class="button ghost" data-recheck="${s.id}">重新检查</button>` : ""}<a class="button ghost" href="/api/submissions/${s.id}/download">下载原包</a></div></td></tr>`).join("")}</tbody></table></div>`;
}
function submissionsHTML() {
    const l = state.env?.limits || {};
    return `<section class="hero"><span class="eyebrow">BUILD A BRAIN. ENTER THE CITY.</span><h1>下一位探索者，<br>由你的代码驱动。</h1><p>视觉理解、关节控制与自主决策。把策略带进霓虹街区，让每一步都有记录。</p><div class="row"><a class="button primary" href="/api/template?kind=walking">下载入门行走包</a><button class="button" type="button" data-view="docs">查看接口要求</button></div></section><div class="split"><section class="panel stack"><div class="row between"><h2>提交新版本</h2><span class="badge neutral">每次上传独立保存</span></div><form id="upload-form" class="stack"><label class="field">策略名称<input class="input" name="name" maxlength="60" required placeholder="给这个策略一个名字"></label><div class="upload-area"><span class="upload-icon" aria-hidden="true">◇</span><label class="field">选择 ZIP 提交包<input class="input" id="zip-file" type="file" name="file" accept=".zip,application/zip" required></label><small>代码、submission.json 与离线权重；单包 ≤ ${l.upload_mb || 128} MB。</small></div><label class="field">版本说明 <span class="muted small">可选</span><textarea class="input" name="description" maxlength="2000" placeholder="例如：改进店内目标识别，调整转身控制"></textarea></label><p class="small muted">环境：<code>${esc(state.env?.node?.environment || "arena-python-v1")}</code> · 解压后 ≤ ${l.expanded_mb || 512} MB · 不包含虚拟环境</p><label class="row small"><input type="checkbox" name="auto_practice">检查通过后自动开始城市练习，并返回成绩与回放</label><progress id="upload-progress" value="0" max="100" aria-label="文件上传进度" hidden></progress><p id="upload-status" class="small muted" aria-live="polite"></p><p id="upload-error" class="form-error" role="alert" hidden></p><div class="row"><button class="button primary" type="submit">上传并检查</button><button class="button ghost" type="button" data-view="docs">格式说明</button></div></form></section><section class="panel stack"><div class="section-title"><h2>检查报告</h2><span class="small">仅本人及管理员可见</span></div><div class="stack" id="submission-report" aria-live="polite">${reportHTML()}</div></section></div><section class="section-space"><div class="section-title"><h2>${state.me.role === "admin" ? "全部提交版本" : "我的提交版本"}</h2><span class="small">历史版本不会被覆盖</span><button class="button ghost" type="button" data-action="refresh">刷新状态</button></div><div id="versions-table">${versionsHTML()}</div></section>`;
}
function jobHTML(job, admin = false) {
    const active = ["queued", "waiting_node", "preparing", "running"].includes(job.state);
    const names = job.players.map((p) => (p ? `${p.username} / ${version(p)}` : "—")).join(" vs ");
    return `<article class="job"><div class="row between"><div><div class="job-name">${job.kind === "official" ? "正式比赛" : job.kind === "check" ? "接口检查" : "自助练习"} · ${job.scene === "cyber_city" ? "城市检索" : "房间检索"}</div><div class="job-sub">${esc(names)}</div></div>${statusBadge(job.state)}</div><p class="status-message">${esc(job.message)}</p>${active ? `<progress value="${Math.round(job.progress * 100)}" max="100" aria-label="本局仿真进度"></progress>` : ""}<div class="stats-line"><span>${date(job.created)}</span>${job.position ? `<span>队列第 ${job.position} 位</span>` : ""}<span>仿真时长 ${job.duration} 秒</span>${job.started ? `<span>实际已用 ${Math.max(0, Math.round((job.finished || Date.now() / 1000) - job.started))} 秒</span>` : ""}</div>${job.result?.scores ? `<p class="number">任务分 ${job.result.scores.map((x, i) => `选手 ${i + 1}：${x}`).join(" / ")} · ${job.result.tie ? "并列" : `选手 ${job.result.winners[0] + 1} 获胜`}</p>` : ""}<div class="row">${job.artifacts_expired ? '<span class="badge neutral">画面已按保留期清理，成绩保留</span>' : ""}${job.kind !== "check" ? `<button class="button ghost" type="button" data-diagnostics="${job.id}">运行诊断</button>` : ""}${["failed", "cancelled"].includes(job.state) && (admin || job.kind === "practice") ? `<button class="button" type="button" data-retry="${job.id}">按原配置重试</button>` : ""}${job.kind !== "check" ? `<button type="button" class="button" data-watch="${job.id}">${job.state === "running" ? "查看运行画面" : "查看结果与回放"}</button>` : ""}${active && (admin || job.kind === "practice") ? `<button type="button" class="button ghost" data-cancel="${job.id}">取消${job.kind === "practice" ? "练习" : "场次"}</button>` : ""}${admin && job.kind === "official" && job.state === "completed" && !job.published && !job.tournament_id ? `<button type="button" class="button primary" data-publish="${job.id}">发布正式成绩与回放</button>` : ""}${job.published ? '<span class="badge good">正式成绩已发布</span>' : ""}</div></article>`;
}
function practiceJobsHTML() {
    const rows = state.jobs.filter((j) => j.kind === "practice");
    return rows.length
        ? rows.map((j) => jobHTML(j)).join("")
        : empty("还没有练习记录", "通过接口检查后，选一个版本开始第一局。");
}
function practiceHTML() {
    const rows = ready();
    return (
        heading("先练习，再走上赛场", "自己的版本独立对局，也可以与自己的历史版本比较。") +
        compareHTML() +
        `<div class="stack"><section class="panel stack"><div class="row between"><h2>发起练习</h2><span class="badge neutral">练习记录私有</span></div><form id="practice-form" class="stack"><div class="split"><label class="field">主测版本<select class="input" name="submission_id" id="practice-version" required>${rows.length ? options(rows) : '<option value="">暂无通过检查的版本</option>'}</select></label><label class="field">对战版本<select class="input" name="opponent_id" id="practice-opponent">${options(rows, true)}</select></label></div><label class="field">任务场景<select class="input" name="scene"><option value="cyber_city">霓虹城市 · 双街区搜索</option><option value="room">房间 · 基础视觉检索</option></select></label><div class="row"><button class="button primary" type="submit" ${rows.length ? "" : "disabled"}>加入练习队列</button><span class="small muted">每局 ${state.env?.limits?.practice_seconds || 60} 仿真秒 · 最多两场未完成练习</span></div><p class="small muted">选择相同版本时，会创建两份独立策略实例，分别控制两台机器人。平台同时运行一局，其他场次排队。</p><p class="form-error" id="practice-error" role="alert" hidden></p></form></section><section><div class="section-title"><h2>我的练习</h2><button class="button ghost" type="button" data-action="refresh">刷新</button></div><div class="job-list" id="practice-jobs">${practiceJobsHTML()}</div></section></div>`
    );
}
function entryHTML() {
    const entry = state.entries.find((e) => e.user_id === state.me.id);
    if (entry)
        return `<div class="row between"><h2>参赛版本已锁定</h2><span class="badge good">已报名</span></div><p>${esc(version(entry) + " · " + entry.name)}</p><p class="small muted">报名时间 ${date(entry.created)}。后续上传不会改变本轮报名和已经安排的比赛。如需调整，请联系管理员解锁报名。</p>`;
    const rows = ready();
    return `<h2>选择正式参赛版本</h2><form id="entry-form" class="stack"><label class="field">通过检查的版本<select class="input" name="submission_id" id="entry-version" required>${rows.length ? options(rows) : '<option value="">请先上传并通过检查</option>'}</select></label><div class="callout">报名后锁定该版本，由管理员安排对手和场次。新提交不会自动替换参赛代码。</div><button class="button primary" type="submit" ${rows.length ? "" : "disabled"}>报名并锁定版本</button><p class="form-error" id="entry-error" role="alert" hidden></p></form>`;
}
function competitionHTML() {
    const rows = state.jobs.filter(
        (j) => j.kind === "official" && j.players.some((p) => p?.username === state.me.username),
    );
    return (
        heading("正式比赛", "绑定确定的代码版本，让每一场比赛可以追溯。") +
        `<div class="stack"><section class="panel stack" id="entry-panel">${entryHTML()}</section><section><div class="section-title"><h2>我的正式场次</h2><span class="small">比赛由管理员统一安排</span></div><div class="job-list" id="official-jobs">${rows.length ? rows.map((j) => jobHTML(j)).join("") : empty("等待正式排赛", "完成报名后，管理员会安排对手、场景和比赛时长。")}</div></section></div>`
    );
}
function boardHTML() {
    return state.board.length
        ? state.board.map((j) => jobHTML(j)).join("")
        : empty("正式成绩尚未发布", "完成正式比赛并经管理员发布后，成绩和回放会显示在这里。");
}
function resultsHTML() {
    return (
        heading(
            "比赛成绩与行为回放",
            "正式记录对平台内选手开放；代码、模型和私人错误日志保持私有。",
        ) +
        `<div class="callout">按场次展示裁判实际成绩，同分为并列。练习成绩不计入正式比赛。</div><section class="section-space job-list" id="official-board">${boardHTML()}</section>`
    );
}
function docsHTML() {
    const l = state.env?.limits || {},
        n = state.env?.node || {};
    return (
        heading(
            "让代码与机器人说同一种语言",
            "下载模板、确认依赖，再实现你的视觉与关节控制。",
            '<a class="button primary" href="/api/template">下载 ZIP 模板</a>',
        ) +
        `<div class="stack"><div class="docs-grid"><section class="panel stack"><span class="step-label">提交格式</span><h2>一个 ZIP，包含完整策略</h2><pre>submission.zip
├── submission.json
├── policy.py
├── models/   离线模型权重
└── src/      可选辅助模块</pre><p class="small muted">允许额外包一层目录。文件名大小写敏感，不接受链接、安装脚本执行或虚拟环境。</p><details><summary>submission.json</summary><pre>{
  "name": "我的城市搜索策略",
  "api_version": 1,
  "entry_point": "policy:Policy",
  "environment": "${esc(n.environment || "arena-python-v1")}"
}</pre></details></section><section class="panel stack"><span class="step-label">统一环境</span><h2>离线运行，依赖保持一致</h2><div id="environment-detail" class="tight">${environmentHTML()}</div><p class="small muted">不临时安装依赖或下载模型。默认环境使用 CPU；PyTorch 与 GPU 支持以已发布的运行环境列表为准。额外依赖由管理员统一发布。</p></section></div><section class="panel stack"><h2>输入观测与动作接口</h2><div class="table-wrap"><table class="table"><thead><tr><th>你能看到什么</th><th>字段与约定</th></tr></thead><tbody><tr><td>摄像头与深度</td><td><code>visual.rgb</code> uint8 / H×W×3；<code>visual.depth</code> 沿光轴的米制深度；图像 10 Hz</td></tr><tr><td>机器人状态</td><td><code>proprio</code>：关节角、角速度、wxyz 姿态、脚部接触指示</td></tr><tr><td>任务与自身信息</td><td><code>tasks</code>：公共及自己的任务；<code>game</code>：自己的生命、分数和冷却</td></tr><tr><td>输出关节动作</td><td><code>joint_targets</code>：29 个有限实数，单位 rad，按观测 <code>joint_names</code> 顺序</td></tr><tr><td>输出开火请求</td><td><code>fire</code>：True / False，实际开火由裁判规则决定</td></tr></tbody></table></div><pre>class Policy:
    def __init__(self, player_id=0, config=None):
        self.player_id = player_id

    def act(self, observation):
        return {
            "joint_targets": observation["proprio"]["q"].copy(),
            "fire": False,
        }</pre><div class="callout">这段只演示数据格式，不能保证站立或行走。动作 50 Hz，图像 10 Hz；慢视觉应缓存识别结果。reset_count 变化时重置运控历史。平台不提供物品真值坐标或自动行走指令。</div><details><summary>查看 29 个关节名称</summary><div class="table-wrap"><table class="table"><thead><tr><th>序号</th><th>关节</th><th>目标单位</th></tr></thead><tbody>${(state.env?.joint_names || []).map((name, i) => `<tr><td>${i + 1}</td><td><code>${esc(name)}</code></td><td>rad</td></tr>`).join("")}</tbody></table></div><p class="small muted">实际调用以 observation.proprio.joint_names 返回顺序为准。</p></details></section><section class="panel stack"><h2>运行限额</h2><div class="table-wrap"><table class="table"><tbody><tr><th>上传 / 解压后</th><td>${l.upload_mb} / ${l.expanded_mb} MB</td><th>账号提交存储</th><td>${l.user_mb} MB</td></tr><tr><th>每策略 CPU / 内存</th><td>${l.cpus} 核 / ${l.memory_mb} MB</td><th>初始化 / 单次响应</th><td>${l.init_seconds} / ${l.act_seconds} 秒</td></tr><tr><th>实际运行上限</th><td>${l.wall_seconds} 秒</td><th>并行比赛</th><td>1 局</td></tr></tbody></table></div><p class="small muted">超时沿用上一有效关节目标，本周期不开火，过期动作丢弃；单策略异常不停止另一名选手。比赛计分沿用裁判规则。</p></section><section class="panel stack"><h2>申请额外依赖</h2><form id="dependency-form" class="stack"><label class="field">库名、版本及用途<textarea class="input" name="text" minlength="3" maxlength="2000" required placeholder="例如：需要某个推理库的固定版本，用于运行已经离线准备好的模型。"></textarea></label><div class="row"><button class="button" type="submit">提交给管理员</button><span class="small muted">管理员回复不等于环境已经发布，以可用环境列表为准。</span></div><p class="form-error" id="dependency-error" role="alert" hidden></p></form><div id="my-requests">${requestsHTML(false)}</div></section></div>`
    );
}
function environmentHTML() {
    const n = state.env?.node || {};
    return `<p>${nodeBadge()}</p><p class="small">${esc(n.message || "正在检测执行节点")}</p>${
        n.libraries
            ? `<p class="small muted">${Object.entries(n.libraries)
                  .map(([key, val]) => esc(key + " " + val))
                  .join(" · ")}</p>`
            : ""
    }<p class="small">环境 <code>${esc(n.environment || "arena-python-v1")}</code></p>${n.image_id ? `<p class="small muted environment-value">镜像摘要 ${esc(n.image_id)}</p>` : ""}`;
}
function requestsHTML(admin) {
    const rows = state.requests;
    return rows.length
        ? `<div class="stack">${rows.map((r) => `<div class="panel-flat tight"><div class="row between"><span>${admin ? esc(r.username) : "我的申请"}</span><span class="badge ${r.state === "pending" ? "wait" : "good"}">${r.state === "pending" ? "待回复" : "已回复"}</span></div><p>${esc(r.text)}</p><p class="small muted">${date(r.created)}</p>${r.reply ? `<p class="callout">${esc(r.reply)}</p>` : ""}${admin ? `<button class="button ghost" type="button" data-reply="${r.id}">回复申请</button>` : ""}</div>`).join("")}</div>`
        : '<p class="small muted">暂无依赖申请。</p>';
}
function adminQueueHTML() {
    const entries = state.entries;
    return `<div class="stack"><section class="panel stack"><div class="row between"><div class="tight"><h2>练习队列管理</h2><p class="small muted">正式比赛优先安排下一局，已开始的练习继续运行。</p></div><button class="button" type="button" data-action="toggle-queue">${state.env?.practice_paused ? "恢复接收练习" : "暂停接收新练习"}</button></div><span class="small muted">当前：${state.env?.practice_paused ? "暂停接收新练习" : "接收练习"}</span></section><section class="panel stack"><h2>安排正式比赛</h2>${entries.length >= 2 ? `<form id="schedule-form" class="stack"><div class="split"><label class="field">选手 A / 已锁定版本<select class="input" name="user_a">${entries.map((e) => `<option value="${e.user_id}">${esc(e.username + " / " + version(e) + " · " + e.name)}</option>`).join("")}</select></label><label class="field">选手 B / 已锁定版本<select class="input" name="user_b">${entries.map((e, i) => `<option value="${e.user_id}" ${i === 1 ? "selected" : ""}>${esc(e.username + " / " + version(e) + " · " + e.name)}</option>`).join("")}</select></label></div><div class="split"><label class="field">场景<select class="input" name="scene"><option value="cyber_city">霓虹城市</option><option value="room">房间</option></select></label><label class="field">仿真时长（秒）<input class="input" type="number" name="duration" min="1" max="120" value="60" required></label></div><button class="button primary" type="submit">加入正式比赛队列</button><p class="form-error" id="schedule-error" role="alert" hidden></p></form>` : empty("还需要两名已报名选手", "让选手先上传策略、通过接口检查并锁定参赛版本。")}<div class="table-wrap"><table class="table"><thead><tr><th>已报名选手</th><th>固定版本</th><th>操作</th></tr></thead><tbody>${entries.map((e) => `<tr><td>${esc(e.username)}</td><td>${esc(version(e) + " · " + e.name)}</td><td><button class="button ghost" type="button" data-unlock="${e.user_id}">解锁报名</button></td></tr>`).join("")}</tbody></table></div></section><section><div class="section-title"><h2>运行与等待中的场次</h2><button class="button ghost" type="button" data-action="refresh">刷新状态</button></div><div id="admin-jobs" class="job-list">${adminJobsHTML()}</div></section></div>`;
}
function adminJobsHTML() {
    return state.jobs.length
        ? state.jobs.map((j) => jobHTML(j, true)).join("")
        : empty("队列为空", "提交检查、练习和正式场次会出现在这里。");
}
function invitesHTML() {
    return state.invites.length
        ? `<div class="table-wrap"><table class="table"><thead><tr><th>邀请码</th><th>有效期</th><th>剩余次数</th><th>状态</th><th>操作</th></tr></thead><tbody>${state.invites.map((i) => `<tr><td class="mono">${esc(i.hint)}</td><td>${date(i.expires)}</td><td>${i.remaining}</td><td>${!i.active ? "已停用" : i.expires < Date.now() / 1000 ? "已过期" : i.remaining ? "有效" : "已用尽"}</td><td>${i.active ? `<button class="button ghost" type="button" data-disable-invite="${i.id}">停用</button>` : "—"}</td></tr>`).join("")}</tbody></table></div>`
        : empty("还没有邀请码", "生成后把完整邀请码交给参赛选手。");
}
function usersHTML() {
    return `<div class="table-wrap"><table class="table"><thead><tr><th>账号</th><th>身份</th><th>注册时间</th><th>状态 / 操作</th></tr></thead><tbody>${state.users.map((u) => `<tr><td>${esc(u.username)}</td><td>${u.role === "admin" ? "管理员" : "选手"}</td><td>${date(u.created)}</td><td>${u.role === "admin" ? "管理员账号" : `<button class="button ghost" type="button" data-toggle-user="${u.id}">${u.active ? "停用账号" : "恢复账号"}</button>`}</td></tr>`).join("")}</tbody></table></div>`;
}
function adminHTML() {
    const tabs = {
        queue: "队列与排赛",
        invites: "邀请码",
        users: "选手账号",
        environment: "运行环境",
        requests: "依赖申请",
    };
    let body = "";
    if (state.adminTab === "queue") body = adminQueueHTML();
    if (state.adminTab === "invites")
        body = `<div class="stack"><section class="panel stack"><h2>邀请新选手</h2><form id="invite-form" class="stack"><div class="split"><label class="field">有效期<select class="input" name="days"><option value="7">7 天</option><option value="30">30 天</option><option value="1">1 天</option></select></label><label class="field">可使用次数<input class="input" type="number" name="uses" min="1" max="100" value="1" required></label></div><button class="button primary" type="submit">生成邀请码</button><p class="form-error" id="invite-error" role="alert" hidden></p></form><div id="new-invite" class="stack" hidden></div></section><div id="invites-list">${invitesHTML()}</div></div>`;
    if (state.adminTab === "users")
        body = `<section class="panel"><div id="users-list">${usersHTML()}</div></section>`;
    if (state.adminTab === "environment")
        body = adminEnvironmentHTML() + '<div id="runtime-slot">' + runtimeHTML() + "</div>";
    if (state.adminTab === "requests")
        body = `<section class="panel stack"><h2>选手的依赖申请</h2><p class="small muted">回复只记录处理意见，不会自动安装库。环境实际发布后才能运行相关提交。</p><div id="admin-requests">${requestsHTML(true)}</div></section>`;
    return (
        heading(
            "组织比赛，让规则保持一致",
            "邀请码、提交、排队、正式发布与执行环境，在同一处管理。",
        ) +
        `<div class="segmented" aria-label="管理员功能">${Object.entries(tabs)
            .map(
                ([key, name]) =>
                    `<button type="button" data-admin-tab="${key}" aria-pressed="${state.adminTab === key}">${name}</button>`,
            )
            .join("")}</div><div class="section-space">${body}</div>`
    );
}
function viewHTML() {
    return (
        {
            submissions: submissionsHTML,
            practice: practiceHTML,
            competition: competitionHTML,
            results: resultsHTML,
            docs: () =>
                starterHTML() + docsHTML() + '<div id="runtime-slot">' + runtimeHTML() + "</div>",
            admin: adminHTML,
            league: leagueHTML,
            operations: operationsHTML,
        }[state.view] || submissionsHTML
    )();
}

function deploymentHTML() {
    const d = state.deployment;
    if (!d) return '<p class="small muted">部署入口将在平台升级完成后开放。</p>';
    return `<div class="row between"><span>${esc(d.stage)}</span><span class="badge ${d.state === "completed" ? "good" : d.state === "failed" ? "bad" : "neutral"}">${d.state === "running" ? "部署中" : d.state === "completed" ? "自检通过" : d.state === "failed" ? "需要处理" : "待部署"}</span></div>${d.state === "running" ? `<progress value="${d.progress}" max="100" aria-label="部署阶段进度"></progress>` : ""}<button class="button primary" type="button" data-action="deploy-runtime" ${d.state === "running" ? "disabled" : ""}>${d.state === "running" ? "正在部署与自检" : "一键部署并自检"}</button><details><summary>部署日志</summary><pre>${esc(d.logs.join("\n") || "点击部署后显示日志。")}</pre></details>`;
}
function adminEnvironmentHTML() {
    return `<section class="panel stack"><h2>部署与仿真通信</h2><div class="stack" id="environment-detail">${environmentHTML()}</div><div class="stack" id="deployment-detail" aria-live="polite">${deploymentHTML()}</div><div class="row"><button class="button" type="button" data-action="refresh-node">重新检测执行环境</button></div><div class="callout">部署会检查机器人资源、启动已安装的执行引擎、准备固定镜像，并实际验证双策略与 MuJoCo 的 RGB-D／关节动作通信。已有镜像会复用，自检不计入成绩。</div><p class="small muted">需要安装 Docker Desktop 时，请先在服务器完成安装。首次安装平台也可以双击项目根目录“一键部署.cmd”。</p><p class="small muted">只读提交、禁外网、独立临时目录及资源限额；额外依赖仍需发布新环境版本。</p></section>`;
}

async function sync(full = false) {
    if (!state.me) return;
    const epoch = state.epoch;
    const paths = [
        "/environment",
        "/submissions",
        "/jobs",
        "/entries",
        "/leaderboard",
        "/requests",
        "/tournaments",
        "/runtimes",
    ];
    const keys = [
        "env",
        "submissions",
        "jobs",
        "entries",
        "board",
        "requests",
        "tournaments",
        "runtimes",
    ];
    if (state.me.role === "admin") {
        paths.push("/admin/users", "/admin/invites", "/admin/deployment", "/admin/operations");
        keys.push("users", "invites", "deployment", "operations");
    }
    const results = await Promise.all(
        paths.map((p) =>
            api(p).catch((e) => {
                if (
                    e.status === 404 &&
                    ["/admin/deployment", "/admin/operations", "/runtimes"].includes(p)
                )
                    return null;
                if (e.status === 404 && p === "/tournaments") return [];
                throw e;
            }),
        ),
    );
    if (!state.me || state.epoch !== epoch) return;
    results.forEach((v, i) => {
        state[keys[i]] = v;
    });
    if (full) render();
    else updateLive();
}
function updateSelect(id, rows, same = false) {
    const select = document.getElementById(id);
    if (!select || document.activeElement === select) return;
    const value = select.value;
    select.innerHTML =
        rows.length || same ? options(rows, same) : '<option value="">暂无通过检查的版本</option>';
    if ([...select.options].some((o) => o.value === value)) select.value = value;
}
function updateLive() {
    const patch = (id, html) => {
        const node = document.getElementById(id);
        const editing =
            node?.contains(document.activeElement) &&
            document.activeElement.matches("input,select,textarea");
        if (node && node.dataset.html !== html && !editing) {
            node.innerHTML = html;
            node.dataset.html = html;
        }
    };
    patch("node-badge", nodeBadge());
    patch("versions-table", versionsHTML());
    patch("submission-report", reportHTML());
    patch("practice-jobs", practiceJobsHTML());
    updateComparisonOptions();
    patch("official-board", boardHTML());
    patch(
        "official-jobs",
        state.jobs
            .filter(
                (j) =>
                    j.kind === "official" &&
                    j.players.some((p) => p?.username === state.me.username),
            )
            .map((j) => jobHTML(j))
            .join("") || empty("等待正式排赛", "管理员安排后会出现在这里。"),
    );
    const locked = state.entries.some((e) => e.user_id === state.me.id);
    if (locked || !document.getElementById("entry-form")) patch("entry-panel", entryHTML());
    else {
        updateSelect("entry-version", ready());
        const submit = document.querySelector("#entry-form button[type=submit]");
        if (submit) submit.disabled = !ready().length;
    }
    patch("tournament-boards", tournamentBoardsHTML());
    if (state.view === "operations") render();
    patch("runtime-slot", runtimeHTML());
    patch("environment-detail", environmentHTML());
    patch("deployment-detail", deploymentHTML());
    patch("admin-jobs", adminJobsHTML());
    patch("invites-list", invitesHTML());
    patch("users-list", usersHTML());
    patch("my-requests", requestsHTML(false));
    patch("admin-requests", requestsHTML(true));
    updateSelect("practice-version", ready());
    updateSelect("practice-opponent", ready(), true);
    const practiceSubmit = document.querySelector("#practice-form button[type=submit]");
    if (practiceSubmit) practiceSubmit.disabled = !ready().length;
}
function setView(view) {
    if (!(view in titles) || (view === "admin" && state.me.role !== "admin")) return;
    state.view = view;
    render();
    window.scrollTo({ top: 0, behavior: "instant" });
}
async function enter() {
    await sync(true);
    clearInterval(pollTimer);
    pollTimer = setInterval(() => {
        if (!state.busy && state.me)
            sync()
                .then(() => (state.watch && dialog.open ? refreshWatch() : null))
                .catch(sessionError);
    }, 5000);
}
function sessionError(error) {
    if (error.status === 401) {
        clearSession();
        authScreen();
        toast("登录已过期，请重新登录。", true);
    } else toast(error.message, true);
}
function formError(id, error) {
    const node = document.getElementById(id);
    if (node) {
        node.textContent = error.message;
        node.hidden = false;
    } else toast(error.message, true);
}
async function formRequest(form, errorId, fn) {
    const button = form.querySelector("button[type=submit]");
    button.disabled = true;
    const old = document.getElementById(errorId);
    if (old) old.hidden = true;
    try {
        await fn(Object.fromEntries(new FormData(form)));
    } catch (e) {
        formError(errorId, e);
    } finally {
        if (button.isConnected) button.disabled = false;
    }
}
function upload(form) {
    const file = form.elements.file.files[0],
        l = state.env.limits;
    if (!file) return;
    if (file.size > l.upload_mb * 1024 ** 2)
        return formError("upload-error", new Error(`ZIP 不能超过 ${l.upload_mb} MB。`));
    state.busy = true;
    const button = form.querySelector("button[type=submit]");
    button.disabled = true;
    const progress = document.getElementById("upload-progress"),
        status = document.getElementById("upload-status"),
        error = document.getElementById("upload-error");
    error.hidden = true;
    progress.hidden = false;
    progress.value = 0;
    status.textContent = "正在传输文件…";
    const xhr = new XMLHttpRequest();
    xhr.open(
        "POST",
        "/api/submissions?" +
            new URLSearchParams({
                name: form.elements.name.value,
                description: form.elements.description.value,
                auto_practice: String(Boolean(form.elements.auto_practice?.checked)),
            }),
    );
    xhr.setRequestHeader("Content-Type", "application/zip");
    xhr.setRequestHeader("X-CSRF-Token", state.me.csrf);
    xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) {
            progress.value = (e.loaded / e.total) * 100;
            status.textContent =
                progress.value >= 100
                    ? "传输完成，正在保存并检查 ZIP…"
                    : `正在上传 ${Math.round(progress.value)}%`;
        }
    };
    xhr.timeout = 180000;
    xhr.onload = async () => {
        try {
            const result = JSON.parse(xhr.responseText);
            if (xhr.status >= 400) throw new Error(readableError(result));
            state.selectedSubmission = result.id;
            status.textContent = `V${String(result.revision).padStart(3, "0")} 已保存。${result.state === "static_failed" ? "静态检查失败，请查看报告。" : "正在排队进行隔离运行检查。"}`;
            form.elements.file.value = "";
            await sync();
            toast(
                result.state === "static_failed"
                    ? "请根据检查报告修复后上传新版本。"
                    : "提交已保存，检查状态会自动更新。",
                result.state === "static_failed",
            );
        } catch (e) {
            formError("upload-error", e);
            status.textContent = "上传未完成。";
        } finally {
            state.busy = false;
            button.disabled = false;
        }
    };
    xhr.onerror = () => {
        state.busy = false;
        button.disabled = false;
        formError("upload-error", new Error("连接中断，请检查平台服务后重试。"));
    };
    xhr.ontimeout = () => {
        state.busy = false;
        button.disabled = false;
        formError(
            "upload-error",
            new Error("传输超时。请先刷新版本列表，确认是否已保存，再决定是否重传。"),
        );
    };
    xhr.send(file);
}

function clearSession() {
    state.epoch++;
    state.me = null;
    state.env = null;
    state.deployment = null;
    state.view = "submissions";
    state.adminTab = "queue";
    state.selectedSubmission = null;
    for (const key of ["submissions", "jobs", "entries", "board", "requests", "users", "invites"])
        state[key] = [];
    closeDialog();
}
function closeDialog() {
    clearInterval(playTimer);
    state.playing = false;
    state.watch = null;
    if (dialog.open) dialog.close();
    document.getElementById("dialog-body").replaceChildren();
}
document.getElementById("close-dialog").addEventListener("click", closeDialog);
dialog.addEventListener("cancel", closeDialog);
async function watch(jobId) {
    closeDialog();
    const epoch = state.epoch;
    const [job, replay, events] = await Promise.all([
        api("/jobs/" + jobId),
        api("/jobs/" + jobId + "/replay"),
        api("/jobs/" + jobId + "/events"),
    ]);
    if (!state.me || epoch !== state.epoch) return;
    state.watch = { id: jobId, job, replay, events };
    state.frameIndex = 0;
    document.getElementById("dialog-title").textContent =
        job.kind === "official" ? "正式比赛 · 结果与回放" : "练习 · 结果与回放";
    document.getElementById("dialog-body").innerHTML =
        `<div class="row between"><span>${job.players.map((p) => esc(p?.username || "—")).join(" vs ")}</span><span id="watch-state">${statusBadge(job.state)}</span></div><div id="watch-scores">${watchScores(job)}</div><img class="replay-image" id="replay-image" alt="本局真实仿真画面，包含裁判视角与双方 RGB 摄像头" ${replay.frames.length ? "" : "hidden"}><p class="muted small" id="replay-empty" ${replay.frames.length ? "hidden" : ""}>画面尚未生成。仿真开始后会自动显示首帧。</p><div class="replay-controls"><button class="button" type="button" id="replay-play">播放</button><input type="range" id="replay-slider" min="0" max="${Math.max(0, replay.frames.length - 1)}" value="0" aria-label="回放时间轴"><span class="small number" id="replay-time">0 秒</span></div><p class="small muted">真实仿真记录 · 网页回放采样 2 Hz · 完整动作轨迹由服务器保存</p><div class="row">${job.state === "completed" ? `<button class="button ghost" type="button" data-manifest="${jobId}">下载复现清单</button>` : ""}${job.players.map((p, i) => (state.me.role === "admin" || p?.username === state.me.username ? `<button class="button ghost" type="button" data-log="${i}">选手 ${i + 1} 私有日志</button>` : "")).join("")}</div><pre id="watch-log" hidden></pre><details><summary>裁判事件（最近 300 条）</summary><ul class="timeline" id="watch-events">${eventsHTML(events)}</ul></details>`;
    document.getElementById("replay-slider").addEventListener("input", (event) => {
        state.frameIndex = Number(event.target.value);
        drawFrame();
    });
    document.getElementById("replay-play").addEventListener("click", togglePlay);
    drawFrame();
    dialog.showModal();
}
function watchScores(job) {
    return job.result?.scores
        ? `<div class="score-strip">${job.result.scores.map((score, i) => `<div class="score-cell"><span class="small muted">${esc(job.players[i]?.username)} / 选手 ${i + 1}</span><div class="score-value number">${score} <span class="small">任务分</span></div><span class="small muted">剩余生命 ${job.result.health[i]}</span></div>`).join("")}</div>`
        : "";
}
const eventNames = {
    fall: "倒地",
    self_recovery: "自主起身",
    traffic_collision: "交通碰撞",
    target_completed: "检索完成",
    death: "生命耗尽",
    target_hit: "检索命中",
    miss: "射击失误",
    player_hit: "命中机器人",
    traffic_hit: "交通碰撞",
    fall_reset: "倒地复位",
    fall_started: "倒地",
    respawn: "重生",
    policy_timeout: "策略响应超时",
    policy_error: "策略异常",
    invalid_action: "动作无效",
};
function eventsHTML(events) {
    return events.length
        ? events
              .map(
                  (e) =>
                      `<li><time>${Number(e.time).toFixed(2)} 秒</time>${esc(eventNames[e.type] || e.type)} ${e.player === undefined ? "" : `· 选手 ${e.player + 1}`} ${e.target ? `· ${esc(e.target)}` : ""}${e.message ? `<div class="muted">${esc(e.message)}</div>` : ""}</li>`,
              )
              .join("")
        : '<li class="muted">暂无已保存事件。</li>';
}
function drawFrame() {
    const w = state.watch;
    if (!w) return;
    const frames = w.replay.frames;
    if (!frames.length) return;
    state.frameIndex = Math.max(0, Math.min(state.frameIndex, frames.length - 1));
    const image = document.getElementById("replay-image");
    image.hidden = false;
    image.src = `/api/jobs/${w.id}/frames/${state.frameIndex}`;
    document.getElementById("replay-empty").hidden = true;
    document.getElementById("replay-slider").value = state.frameIndex;
    document.getElementById("replay-time").textContent =
        frames[state.frameIndex].time.toFixed(1) + " 秒";
}
function togglePlay() {
    if (!state.watch?.replay.frames.length) return;
    state.playing = !state.playing;
    document.getElementById("replay-play").textContent = state.playing ? "暂停" : "播放";
    clearInterval(playTimer);
    if (state.playing) {
        if (state.frameIndex >= state.watch.replay.frames.length - 1) state.frameIndex = 0;
        drawFrame();
        playTimer = setInterval(() => {
            if (!state.watch) return;
            if (state.frameIndex < state.watch.replay.frames.length - 1) {
                state.frameIndex++;
                drawFrame();
            } else {
                state.playing = false;
                clearInterval(playTimer);
                document.getElementById("replay-play").textContent = "播放";
            }
        }, 500);
    }
}
async function refreshWatch() {
    const id = state.watch?.id;
    if (!id) return;
    const [job, replay, events] = await Promise.all([
        api("/jobs/" + id),
        api("/jobs/" + id + "/replay"),
        api("/jobs/" + id + "/events"),
    ]);
    if (state.watch?.id !== id) return;
    const wasEmpty = !state.watch.replay.frames.length;
    state.watch = { id, job, replay, events };
    document.getElementById("replay-slider").max = Math.max(0, replay.frames.length - 1);
    document.getElementById("watch-state").innerHTML = statusBadge(job.state);
    document.getElementById("watch-scores").innerHTML = watchScores(job);
    document.getElementById("watch-events").innerHTML = eventsHTML(events);
    if (wasEmpty) drawFrame();
}
function downloadJSON(data, name) {
    const url = URL.createObjectURL(
        new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = name;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
}

document.addEventListener("submit", (event) => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement)) return;
    event.preventDefault();
    if (form.id === "auth-form")
        return formRequest(form, "auth-error", async (data) => {
            state.me = await api(
                state.setup ? "/setup" : state.authMode === "register" ? "/register" : "/login",
                { method: "POST", body: data },
            );
            state.epoch++;
            await enter();
        });
    if (form.id === "upload-form") return upload(form);
    if (form.id === "practice-form")
        return formRequest(form, "practice-error", async (data) => {
            data.opponent_id = data.opponent_id || null;
            await api("/practices", { method: "POST", body: data });
            await sync();
            toast("练习已加入队列。");
        });
    if (form.id === "entry-form")
        return formRequest(form, "entry-error", async (data) => {
            await api("/entries", { method: "POST", body: data });
            await sync();
            toast("本轮报名版本已锁定。");
        });
    if (form.id === "invite-form")
        return formRequest(form, "invite-error", async (data) => {
            data.days = Number(data.days);
            data.uses = Number(data.uses);
            const result = await api("/admin/invites", { method: "POST", body: data });
            const output = document.getElementById("new-invite");
            output.hidden = false;
            output.innerHTML = `<label class="field">请复制完整邀请码<input class="input mono" readonly id="invite-code" value="${esc(result.code)}"></label><p class="small muted">${esc(result.note)}</p><button class="button" type="button" data-action="copy-invite">复制邀请码</button>`;
            await sync();
        });
    if (form.id === "schedule-form")
        return formRequest(form, "schedule-error", async (data) => {
            data.duration = Number(data.duration);
            await api("/admin/matches", { method: "POST", body: data });
            await sync();
            toast("正式场次已加入队列。");
        });
    if (form.id === "dependency-form")
        return formRequest(form, "dependency-error", async (data) => {
            await api("/requests", { method: "POST", body: data });
            form.reset();
            await sync();
            toast("申请已提交给管理员。");
        });
    if (form.id === "reply-form")
        return formRequest(form, "reply-error", async (data) => {
            await api("/admin/requests/" + form.dataset.requestId + "/reply", {
                method: "POST",
                body: data,
            });
            closeDialog();
            await sync();
            toast("回复已保存。");
        });
});
document.addEventListener("click", async (event) => {
    const button = event.target.closest("button,a");
    if (!button) return;
    try {
        if (button.dataset.auth) {
            state.authMode = button.dataset.auth;
            authScreen();
        }
        if (button.dataset.view) setView(button.dataset.view);
        if (button.id === "mobile-menu") {
            const open = app.querySelector(".shell").classList.toggle("menu-open");
            button.setAttribute("aria-expanded", String(open));
        }
        if (button.dataset.adminTab) {
            state.adminTab = button.dataset.adminTab;
            render();
        }
        if (button.dataset.report) {
            state.selectedSubmission = button.dataset.report;
            document.getElementById("submission-report").innerHTML = reportHTML();
            document
                .getElementById("submission-report")
                .scrollIntoView({ block: "center", behavior: "smooth" });
        }
        if (button.dataset.recheck) {
            button.disabled = true;
            const result = await api("/submissions/" + button.dataset.recheck + "/recheck", {
                method: "POST",
            });
            await sync();
            toast(
                result.already_queued ? "该版本已在检查队列中。" : "同一版本已重新加入检查队列。",
            );
        }
        if (button.dataset.practiceVersion) {
            setView("practice");
            document.getElementById("practice-version").value = button.dataset.practiceVersion;
        }
        if (button.dataset.watch) await watch(button.dataset.watch);
        if (button.dataset.cancel) {
            button.disabled = true;
            await api("/jobs/" + button.dataset.cancel + "/cancel", { method: "POST" });
            await sync();
            toast("已取消，执行实例正在清理。");
        }
        if (button.dataset.publish) {
            button.disabled = true;
            await api("/admin/jobs/" + button.dataset.publish + "/publish", { method: "POST" });
            await sync();
            toast("正式成绩和回放已对平台内选手发布。");
        }
        if (button.dataset.disableInvite) {
            await api("/admin/invites/" + button.dataset.disableInvite + "/disable", {
                method: "POST",
            });
            await sync();
            toast("邀请码已停用。");
        }
        if (button.dataset.toggleUser) {
            await api("/admin/users/" + button.dataset.toggleUser + "/toggle", { method: "POST" });
            await sync();
            toast("账号状态已更新，原登录已失效。");
        }
        if (button.dataset.unlock) {
            await api("/admin/entries/" + button.dataset.unlock + "/unlock", { method: "POST" });
            await sync(true);
            toast("报名已解锁，已安排场次仍使用原固定版本。");
        }
        if (button.dataset.reply) {
            const r = state.requests.find((x) => x.id === button.dataset.reply);
            closeDialog();
            document.getElementById("dialog-title").textContent = "回复依赖申请";
            document.getElementById("dialog-body").innerHTML =
                `<p>${esc(r.text)}</p><form id="reply-form" class="stack" data-request-id="${r.id}"><label class="field">处理意见<textarea class="input" name="reply" maxlength="2000" required>${esc(r.reply)}</textarea></label><p class="form-error" id="reply-error" role="alert" hidden></p><button class="button primary" type="submit">保存回复</button></form>`;
            dialog.showModal();
        }
        if (button.dataset.manifest)
            downloadJSON(
                await api("/jobs/" + button.dataset.manifest + "/manifest"),
                "reproduction-" + button.dataset.manifest + ".json",
            );
        if (button.dataset.log !== undefined && state.watch) {
            const result = await api("/jobs/" + state.watch.id + "/logs/" + button.dataset.log);
            const pre = document.getElementById("watch-log");
            pre.textContent = result.text || "没有输出日志。";
            pre.hidden = false;
        }
        if (button.dataset.action === "logout") {
            await api("/logout", { method: "POST" });
            clearSession();
            state.setup = false;
            state.authMode = "login";
            authScreen();
        }
        if (button.dataset.action === "refresh") {
            button.disabled = true;
            await sync();
            toast("状态已更新。");
            button.disabled = false;
        }
        if (button.dataset.action === "toggle-queue") {
            await api("/admin/queue/toggle", { method: "POST" });
            await sync(true);
            toast("练习队列设置已更新。");
        }
        if (button.dataset.action === "refresh-node") {
            button.disabled = true;
            await api("/admin/node/refresh", { method: "POST" });
            await sync();
            button.disabled = false;
            toast("执行环境检测完成。");
        }
        if (button.dataset.action === "deploy-runtime") {
            button.disabled = true;
            state.deployment = await api("/admin/deploy", { method: "POST" });
            await sync();
            toast("部署与通信自检已开始，进度会自动更新。");
        }
        if (button.dataset.action === "copy-invite") {
            const input = document.getElementById("invite-code");
            if (navigator.clipboard) {
                await navigator.clipboard.writeText(input.value);
                toast("邀请码已复制。");
            } else {
                input.select();
                toast("已选中邀请码，请复制。");
            }
        }
    } catch (error) {
        button.disabled = false;
        sessionError(error);
    }
});

(async () => {
    try {
        const status = await api("/status");
        state.setup = status.setup_required;
        if (state.setup) return authScreen();
        try {
            state.me = await api("/me");
        } catch (error) {
            if (error.status !== 401) throw error;
        }
        if (state.me) await enter();
        else authScreen();
    } catch (error) {
        app.innerHTML = `<main class="boot"><h1>暂时无法连接平台</h1><p>${esc(error.message)}</p><button class="button" type="button" id="retry-connection">重新连接</button></main>`;
        document
            .getElementById("retry-connection")
            .addEventListener("click", () => location.reload());
    }
})();
