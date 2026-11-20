"use strict";

function tournamentBoardsHTML() {
    const rows = state.tournaments || [];
    return rows
        .map(
            (t) =>
                `<section class="panel stack"><div class="row between"><h2>${esc(t.name)}</h2><span class="badge ${t.published ? "good" : "wait"}">${t.published ? "总榜已发布" : "验收与比赛进行中"}</span></div><p>${t.scene === "cyber_city" ? "城市检索" : "房间检索"} · ${t.rounds} 组布局 · 每组交换出生位置 · 已完成 ${t.standings.completed}/${t.standings.total} 场</p><p class="small muted">${esc(t.standings.rule)}</p><div class="table-wrap"><table class="table"><thead><tr><th>排名</th><th>选手 / 版本</th><th>积分</th><th>胜 / 平 / 负</th><th>任务净分</th><th>任务总分</th></tr></thead><tbody>${t.standings.rows.map((r) => `<tr><td>${r.rank}</td><td>${esc(r.username)} / V${String(r.revision).padStart(3, "0")}</td><td>${r.points}</td><td>${r.wins} / ${r.draws} / ${r.losses}</td><td>${r.score_difference}</td><td>${r.task_score}</td></tr>`).join("")}</tbody></table></div>${state.me.role === "admin" && !t.published ? `<button class="button primary" type="button" data-tournament-publish="${t.id}" ${t.standings.completed !== t.standings.total ? "disabled" : ""}>发布赛事总榜与回放</button>` : ""}</section>`,
        )
        .join("");
}
function leagueHTML() {
    const boards = tournamentBoardsHTML();
    const form =
        state.me.role === "admin"
            ? `<section class="panel stack"><h2>创建公平循环赛</h2><p class="muted">每组选手使用相同布局进行两场比赛，交换出生位置。创建后固定所有参赛版本。</p><form id="tournament-form" class="stack"><label class="field">赛事名称<input class="input" name="name" maxlength="60" required></label><div class="split"><label class="field">重复布局数<input class="input" name="rounds" type="number" min="1" max="5" value="2" required></label><label class="field">每局仿真秒数<input class="input" name="duration" type="number" min="1" max="120" value="60" required></label></div><label class="field">场景<select class="input" name="scene"><option value="cyber_city">城市检索</option><option value="room">房间检索</option></select></label><fieldset><legend>已报名选手（至少两人，必须使用同一环境）</legend>${state.entries.map((e) => `<label class="check-row"><input type="checkbox" name="entrant" value="${e.user_id}"> ${esc(e.username)} / ${version(e)}</label>`).join("") || "<p>暂无报名选手</p>"}</fieldset><button class="button primary" type="submit">生成循环赛程</button><p id="tournament-error" class="form-error" role="alert" hidden></p></form></section>`
            : "";
    return (
        heading("赛事与总排行榜", "多布局、交换出生位置，以固定版本比较策略表现。") +
        `<div class="stack" id="league-content">${form}<div class="stack" id="tournament-boards">${boards || empty("暂无已发布赛事", "管理员完成全部场次并发布后，可在这里查看总榜。")}</div></div>`
    );
}

function starterHTML() {
    return `<section class="panel stack section-space"><span class="step-label">从可运行的机器人开始</span><h2>G1 入门行走包</h2><p>包含固定开源行走权重、29 关节适配和简单深度避障。前两秒站立，再按配置行走；可将 speed 设为 0 测试站立。搜索、瞄准和自主起身由选手继续实现。</p><a class="button primary" href="/api/template?kind=walking">下载行走与避障示例</a><p class="small muted">离线权重与上游许可随包提供。接口检查通过后，建议先做房间练习。</p></section>`;
}

function runtimeHTML() {
    const data = state.runtimes || { published: [], profiles: [] };
    return `<section class="panel stack section-space"><h2>模型运行环境</h2><p>选手在 submission.json 中选择已发布的环境。双方环境一致才能比赛，环境镜像固定后不覆盖。</p>${data.published.map((r) => `<div class="row between"><code>${esc(r.id)}</code><span class="badge neutral">${r.gpu ? "GPU" : "CPU"}</span><span class="small muted">${esc(r.status)}</span><a class="button ghost" href="/api/template?kind=walking&environment=${encodeURIComponent(r.id)}">下载该环境示例</a></div>`).join("")}${
        state.me.role === "admin"
            ? `<form id="runtime-form" class="stack"><label class="field">准备新的推理环境<select class="input" name="environment">${data.profiles
                  .filter((p) => !data.published.some((r) => r.id === p.id && r.image_id))
                  .map(
                      (p) =>
                          `<option value="${p.id}">${esc(p.id)} · ${p.gpu ? "需要 NVIDIA GPU" : "CPU"}</option>`,
                  )
                  .join(
                      "",
                  )}</select></label><button class="button" type="submit" ${data.building ? "disabled" : ""}>${data.building ? "正在准备 " + esc(data.building) : "构建、验证并发布环境"}</button><p class="small muted">PyTorch 和 CUDA 环境首次下载较大。GPU 环境必须实际执行设备推理后才能发布；显存目前不提供硬配额。</p><p id="runtime-error" class="form-error" role="alert" ${data.error ? "" : "hidden"}>${esc(data.error || "")}</p></form>`
            : ""
    }</section>`;
}

function operationsHTML() {
    const o = state.operations || {};
    return (
        heading("后台维护", "自动保存账号与原始提交，保留比赛成绩，管理可回收的练习文件。") +
        `<div class="stack" id="operations-content"><section class="panel stack"><h2>备份与保留</h2><p>最近成功备份：${date(o.last_backup)} · 可用磁盘：${o.free_gb ?? "—"} GB</p><p>每天备份数据库和提交原包，保留最近 ${o.backup_keep || 7} 份。练习画面与日志保留 ${o.practice_retention_days || 30} 天；正式比赛与成绩保留。</p><p class="small muted">备份存放在本机数据目录，建议另做异地备份。回放文件不包含在快照中。恢复命令只写入全新目录，避免覆盖现有数据。</p><div class="row"><button class="button primary" type="button" data-release-action="backup">立即备份</button><button class="button" type="button" data-release-action="maintenance">执行到期清理</button></div></section><section class="panel stack"><h2>待处理告警</h2>${(o.alerts || []).map((a) => `<article class="job"><p>${esc(a.message)}</p><div class="row between"><span class="small muted">${date(a.created)}</span><button class="button ghost" type="button" data-resolve-alert="${a.id}">标记已处理</button></div></article>`).join("") || '<p class="muted">暂无待处理告警</p>'}</section></div>`
    );
}

function compareHTML() {
    const jobs = state.jobs.filter((j) => j.kind === "practice" && j.state === "completed");
    const options = (selected) =>
        jobs
            .map(
                (j, i) =>
                    `<option value="${j.id}" ${i === selected ? "selected" : ""}>${esc(j.players[0]?.name || "练习")} · ${date(j.finished)}</option>`,
            )
            .join("");
    return `<section class="panel stack section-space"><h2>比较两次练习</h2><form id="compare-form" class="stack"><div class="split"><label class="field">第一次运行<select class="input" name="first" required>${options(0)}</select></label><label class="field">第二次运行<select class="input" name="second" required>${options(1)}</select></label></div><button class="button" type="submit" ${jobs.length < 2 ? "disabled" : ""}>比较成绩与耗时</button><p class="small muted">选择相同场景与时长更便于比较。不同随机布局的单局分数可能存在波动。</p><p id="compare-error" class="form-error" role="alert" hidden></p></form><div id="compare-result"></div></section>`;
}

function lineChart(timeline, field, player, label) {
    const values = timeline.map((r) => Number(r[field + "_" + player])).filter(Number.isFinite);
    if (values.length < 2) return "";
    const max = Math.max(1, ...values);
    const points = values
        .map(
            (v, i) =>
                `${((i / (values.length - 1)) * 520).toFixed(1)},${(100 - (v / max) * 90).toFixed(1)}`,
        )
        .join(" ");
    return `<figure><figcaption class="small muted">${esc(label)} · 最大值 ${max.toFixed(1)}</figcaption><svg viewBox="0 0 520 110" role="img" aria-label="${esc(label)}随时间变化"><polyline points="${points}" stroke="#83e2d8" stroke-width="2" fill="none"/></svg></figure>`;
}

async function showDiagnostics(id) {
    const data = await api("/jobs/" + id + "/diagnostics");
    closeDialog();
    document.getElementById("dialog-title").textContent = "运行诊断";
    document.getElementById("dialog-body").innerHTML =
        `<p>${data.message ? esc(data.message) : "真实运行统计 · 响应耗时包含通信与等待"}</p>${data.players
            .map(
                (p) =>
                    `<section class="panel section-space"><h3>选手 ${p.player + 1}</h3><p>有效响应 ${p.calls} 次 · 平均 ${p.mean_ms} ms · 95% 响应不超过 ${p.p95_ms} ms · 最大 ${p.max_ms} ms</p><p class="small">${
                        Object.entries(data.event_counts?.[p.player] || {})
                            .map(([k, v]) => `${esc(eventNames[k] || k)} ${v} 次`)
                            .join(" · ") || "暂无裁判异常事件"
                    }</p>${lineChart(data.timeline, "health", p.player, "生命值")}${lineChart(data.timeline, "latency", p.player, "响应耗时 ms")}</section>`,
            )
            .join("")}`;
    dialog.showModal();
}

document.addEventListener("submit", (event) => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement)) return;
    if (form.id === "tournament-form")
        return formRequest(form, "tournament-error", async (data) => {
            data.users = [...form.querySelectorAll('[name="entrant"]:checked')].map((x) => x.value);
            delete data.entrant;
            data.duration = Number(data.duration);
            data.rounds = Number(data.rounds);
            await api("/admin/tournaments", { method: "POST", body: data });
            await sync(true);
            toast("固定版本的公平赛程已生成。");
        });
    if (form.id === "runtime-form")
        return formRequest(form, "runtime-error", async (data) => {
            await api("/admin/runtimes", { method: "POST", body: data });
            await sync(true);
            toast("环境准备已开始，可在此查看结果。");
        });
    if (form.id === "compare-form")
        return formRequest(form, "compare-error", async (data) => {
            if (data.first === data.second) throw new Error("请选择两次不同的练习。");
            const rows = await api("/compare?" + new URLSearchParams(data));
            document.getElementById("compare-result").innerHTML =
                `<div class="table-wrap"><table class="table"><thead><tr><th>运行</th><th>机器人</th><th>任务分</th><th>剩余生命</th><th>实际秒数</th></tr></thead><tbody>${rows.map((r) => `<tr><td>${r.job === data.first ? "第一次" : "第二次"}</td><td>${r.player + 1}</td><td>${r.score}</td><td>${r.health}</td><td>${r.wall_seconds}</td></tr>`).join("")}</tbody></table></div>`;
        });
});
document.addEventListener("click", async (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    try {
        if (button.dataset.tournamentPublish) {
            await api("/admin/tournaments/" + button.dataset.tournamentPublish + "/publish", {
                method: "POST",
            });
            await sync(true);
            toast("赛事总榜与回放已发布。");
        }
        if (button.dataset.diagnostics) await showDiagnostics(button.dataset.diagnostics);
        if (button.dataset.retry) {
            await api("/jobs/" + button.dataset.retry + "/retry", { method: "POST" });
            await sync();
            toast("原版本与布局已重新排队。");
        }
        if (button.dataset.releaseAction) {
            button.disabled = true;
            const result = await api("/admin/" + button.dataset.releaseAction, { method: "POST" });
            await sync(true);
            toast(
                result.snapshot
                    ? "备份完成：" + result.snapshot
                    : "已清理 " + result.expired_practices + " 场过期练习文件。",
            );
        }
        if (button.dataset.resolveAlert) {
            await api("/admin/alerts/" + button.dataset.resolveAlert + "/resolve", {
                method: "POST",
            });
            await sync(true);
        }
    } catch (error) {
        button.disabled = false;
        sessionError(error);
    }
});

function updateComparisonOptions() {
    const form = document.getElementById("compare-form");
    if (!form) return;
    const jobs = state.jobs.filter((j) => j.kind === "practice" && j.state === "completed");
    for (const [index, name] of ["first", "second"].entries()) {
        const select = form.elements[name];
        if (document.activeElement === select) continue;
        const ids = jobs.map((j) => j.id).join(",");
        if ([...select.options].map((o) => o.value).join(",") !== ids) {
            const previous = select.value;
            select.innerHTML = jobs
                .map(
                    (j) =>
                        `<option value="${j.id}">${esc(j.players[0]?.name || "练习")} · ${date(j.finished)}</option>`,
                )
                .join("");
            select.value = jobs.some((j) => j.id === previous)
                ? previous
                : jobs[index]?.id || jobs[0]?.id || "";
        }
    }
    form.querySelector('button[type="submit"]').disabled = jobs.length < 2;
}
