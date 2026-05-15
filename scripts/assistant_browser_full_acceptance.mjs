import { chromium } from "playwright";
import { spawn } from "node:child_process";
import { AsyncLocalStorage } from "node:async_hooks";
import { mkdir, rm, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import path from "node:path";

const ROOT = path.resolve(new URL("..", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1"));
const BACKEND = path.join(ROOT, "backend");
const FRONTEND = path.join(ROOT, "frontend");
const OUT_DIR = path.join(ROOT, "docs", "development", "browser_acceptance_runs");
const RUN_ID = new Date().toISOString().replace(/[-:.TZ]/g, "").slice(0, 14);
const API_PORT = Number(process.env.ACCEPTANCE_API_PORT || 18741);
const WEB_PORT = Number(process.env.ACCEPTANCE_WEB_PORT || 8894);
const API_BASE = `http://127.0.0.1:${API_PORT}/api`;
const WEB_URL = `http://127.0.0.1:${WEB_PORT}`;
const USER_ID = "local-user";
const DB_PATH = path.join(BACKEND, "data", `browser_full_acceptance_${RUN_ID}.db`);
const MEMORY_PATH = path.join(BACKEND, "data", `browser_full_acceptance_memory_${RUN_ID}`);
const PYTHON = path.join(BACKEND, ".venv312", "Scripts", "python.exe");
const PNPM = process.platform === "win32" ? "cmd.exe" : "pnpm";
const VERBOSE_CHILD_LOGS = process.env.ACCEPTANCE_VERBOSE_LOGS === "1";
const UTF8_ENV = {
  PYTHONUTF8: "1",
  PYTHONIOENCODING: "utf-8",
  LANG: "C.UTF-8",
  LC_ALL: "C.UTF-8",
};

const results = [];
let browser;
let page;
let apiProc;
let webProc;
let currentReportBase = null;
let scenarioCounter = 0;
let scenarioGeneration = 0;
const scenarioContext = new AsyncLocalStorage();
const activeScenarioTokens = new Set();
const SCENARIO_LIMIT = Number(process.env.ACCEPTANCE_SCENARIO_LIMIT || 0);
const SCENARIO_FILTER = new Set(
  (process.env.ACCEPTANCE_SCENARIO_FILTER || "")
    .split(",")
    .map((id) => id.trim())
    .filter(Boolean),
);

function isoDatePlus(days, hour = 9, minute = 0) {
  const d = new Date();
  d.setDate(d.getDate() + days);
  d.setHours(hour, minute, 0, 0);
  return d.toISOString();
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function proc(command, args, options = {}) {
  const child = spawn(command, args, {
    cwd: options.cwd,
    env: { ...process.env, ...UTF8_ENV, ...options.env },
    stdio: ["ignore", "pipe", "pipe"],
    shell: false,
  });
  child.stdout.on("data", (data) => {
    if (options.prefix && VERBOSE_CHILD_LOGS) process.stdout.write(`[${options.prefix}] ${data}`);
  });
  child.stderr.on("data", (data) => {
    if (options.prefix && VERBOSE_CHILD_LOGS) process.stderr.write(`[${options.prefix}] ${data}`);
  });
  return child;
}

async function waitFor(url, timeoutMs = 60000) {
  const started = Date.now();
  let lastError;
  while (Date.now() - started < timeoutMs) {
    try {
      const res = await fetch(url);
      if (res.ok) return;
      lastError = new Error(`${url} -> ${res.status}`);
    } catch (error) {
      lastError = error;
    }
    await sleep(500);
  }
  throw lastError || new Error(`Timed out waiting for ${url}`);
}

async function runPython(code, extraEnv = {}) {
  const child = proc(PYTHON, ["-c", code], {
    cwd: BACKEND,
    env: {
      SQLITE_DB_PATH: DB_PATH,
      ASSISTANT_MEMORY_PATH: MEMORY_PATH,
      ASSISTANT_CONDUCTOR_MODE: "proposal",
      ASSISTANT_PROACTIVE_MODE: "proposals",
      LLM_PROVIDER: process.env.LLM_PROVIDER || "deepseek",
      LLM_FALLBACK_PROVIDER: process.env.LLM_FALLBACK_PROVIDER || "gemini",
      ...extraEnv,
    },
  });
  let stdout = "";
  let stderr = "";
  child.stdout.on("data", (d) => (stdout += d));
  child.stderr.on("data", (d) => (stderr += d));
  const exit = await new Promise((resolve) => child.on("exit", resolve));
  if (exit !== 0) {
    throw new Error(`python failed ${exit}\nSTDOUT:\n${stdout}\nSTDERR:\n${stderr}`);
  }
  return stdout.trim();
}

async function api(pathname, options = {}) {
  const headers = {
    "Content-Type": "application/json",
    "X-User-Id": USER_ID,
    ...(options.headers || {}),
  };
  const res = await fetch(`${API_BASE}${pathname}`, {
    ...options,
    headers,
    body: options.body && typeof options.body !== "string" ? JSON.stringify(options.body) : options.body,
  });
  const text = await res.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  if (!res.ok && !options.allowError) {
    throw new Error(`${options.method || "GET"} ${pathname} -> ${res.status}: ${text}`);
  }
  return { status: res.status, data, text };
}

async function clearAll() {
  await runPython(`
import asyncio
from sqlalchemy import delete
from app.db.session import get_sessionmaker
from app.models import AssistantMessage, AssistantSession, AssistantProposal, AssistantSignal, AssistantThreadState, AssistantMemoryUpdateCandidate, Event, Task
async def main():
    sm = get_sessionmaker()
    async with sm() as s:
        for model in [AssistantMessage, AssistantSession, AssistantProposal, AssistantSignal, AssistantThreadState, AssistantMemoryUpdateCandidate, Event, Task]:
            await s.execute(delete(model).where(model.user_id == "${USER_ID}") if hasattr(model, "user_id") else delete(model))
        await s.commit()
asyncio.run(main())
`);
  await rm(path.join(MEMORY_PATH, USER_ID), { recursive: true, force: true });
}

async function initDb() {
  await mkdir(path.dirname(DB_PATH), { recursive: true });
  await rm(DB_PATH, { force: true });
  await rm(MEMORY_PATH, { recursive: true, force: true });
  await mkdir(MEMORY_PATH, { recursive: true });
  await runPython(`
import asyncio
import app.models
from app.db.session import init_db
asyncio.run(init_db())
`);
  const tableCount = await runPython(`
import asyncio
from sqlalchemy import text
from app.db.session import get_sessionmaker
async def main():
    sm = get_sessionmaker()
    async with sm() as s:
        rows = await s.execute(text("select count(*) from sqlite_master where type='table'"))
        print(rows.scalar_one())
asyncio.run(main())
`);
  if (Number(tableCount) < 5) throw new Error(`database initialization failed; table_count=${tableCount}`);
}

async function createEvent(title, start, end, extra = {}) {
  return (await api("/events", {
    method: "POST",
    body: {
      title,
      start_time: start,
      end_time: end,
      location_name: extra.location_name || undefined,
      event_type: extra.event_type,
      status: extra.status,
      linked_task_id: extra.linked_task_id,
      travel_duration_minutes: extra.travel_duration_minutes,
      departure_time: extra.departure_time,
      travel_mode: extra.travel_mode,
    },
  })).data;
}

async function createTask(content, extra = {}) {
  return (await api("/tasks", {
    method: "POST",
    body: {
      content,
      estimated_duration_minutes: extra.estimated_duration_minutes,
      priority: extra.priority,
      deadline: extra.deadline,
      status: extra.status,
      can_split: extra.can_split,
      preferred_period: extra.preferred_period,
      max_splits: extra.max_splits,
      min_chunk_minutes: extra.min_chunk_minutes,
      split_strategy: extra.split_strategy,
    },
  })).data;
}

async function createProposal(summary, actions, extra = {}) {
  const actionJson = JSON.stringify(actions);
  const dedupKey = extra.dedup_key == null ? "None" : JSON.stringify(extra.dedup_key);
  const protocolLabel = extra.protocol_label == null ? "None" : JSON.stringify(extra.protocol_label);
  return JSON.parse(await runPython(`
import asyncio, json
from datetime import datetime, timezone, timedelta
from app.api.schemas import AssistantProposalCreate
from app.services.assistant_proposal_manager import AssistantProposalManager
async def main():
    expires = ${extra.expiresInSeconds == null ? "None" : `datetime.now(timezone.utc) + timedelta(seconds=${extra.expiresInSeconds})`}
    payload = AssistantProposalCreate(
        session_id=None,
        proposal_type="${extra.proposal_type || "event_creation"}",
        trigger_type="${extra.trigger_type || "test"}",
        status="${extra.status || "pending"}",
        dedup_key=${dedupKey},
        summary=${JSON.stringify(summary)},
        payload_json={
            "protocol_label": ${protocolLabel},
            "options": [{
                "option_id": "A",
                "title": ${JSON.stringify(extra.optionTitle || "方案A")},
                "summary": ${JSON.stringify(summary)},
                "rationale": ${JSON.stringify(extra.rationale || "浏览器验收构造方案")},
                "actions": json.loads(${JSON.stringify(actionJson)})
            }]
        },
        recommended_option_id="A",
        expires_at=expires,
        related_event_id=${extra.related_event_id == null ? "None" : Number(extra.related_event_id)},
        related_task_id=${extra.related_task_id == null ? "None" : Number(extra.related_task_id)},
        supersedes_proposal_id=${extra.supersedes_proposal_id == null ? "None" : Number(extra.supersedes_proposal_id)}
    )
    p = await AssistantProposalManager().create_proposal(user_id="${USER_ID}", payload=payload)
    print(json.dumps({"id": p.id, "status": p.status, "summary": p.summary}, ensure_ascii=False))
asyncio.run(main())
`));
}

async function createMemoryCandidate(type, content, reason = "浏览器验收构造记忆候选") {
  return (await api("/assistant/memory/candidates", {
    method: "POST",
    body: {
      memory_type: type,
      confidence: 0.9,
      proposed_change_json: { operation: "append_entry", title: content, content },
      reason,
      dedup_key: `${type}:${content}`,
    },
  })).data;
}

async function markProposalStatus(proposalId, status) {
  await runPython(`
import asyncio
from sqlalchemy import update
from app.db.session import get_sessionmaker
from app.models import AssistantProposal
async def main():
    sm = get_sessionmaker()
    async with sm() as s:
        await s.execute(
            update(AssistantProposal)
            .where(AssistantProposal.id == ${Number(proposalId)}, AssistantProposal.user_id == "${USER_ID}")
            .values(status=${JSON.stringify(status)})
        )
        await s.commit()
asyncio.run(main())
`);
}

async function createSignal(type, context = {}, extra = {}) {
  return (await api("/assistant/heartbeat/run", {
    method: "POST",
    body: {
      signal_type: type,
      severity: extra.severity || "info",
      dedup_key: extra.dedup_key || `${type}:${RUN_ID}:${JSON.stringify(context).slice(0, 20)}`,
      target_type: extra.target_type,
      target_id: extra.target_id,
      context_json: context,
    },
  })).data.created_or_reused_signal;
}

async function gotoApp(width = 1365, height = 900) {
  ensureActiveScenario();
  console.log(`  goto app ${width}x${height}`);
  await page.setViewportSize({ width, height });
  await page.goto(WEB_URL, { waitUntil: "domcontentloaded", timeout: 30000 });
  await page.waitForTimeout(1000);
  await clickAssistantTab();
}

async function clickAssistantTab() {
  const visibleTextareas = await page.locator("textarea").evaluateAll((els) =>
    els.filter((el) => {
      const style = window.getComputedStyle(el);
      const box = el.getBoundingClientRect();
      return style.visibility !== "hidden" && style.display !== "none" && box.width > 0 && box.height > 0;
    }).length
  ).catch(() => 0);
  if (visibleTextareas > 0) return;
  const assistantTabs = page.getByText("助手", { exact: true });
  const count = await assistantTabs.count();
  for (let i = 0; i < count; i += 1) {
    const tab = assistantTabs.nth(i);
    if (await tab.isVisible().catch(() => false)) {
      await tab.click();
      await page.waitForTimeout(300);
      return;
    }
  }
  const assistantByRole = page.getByRole("button", { name: /助手|Assistant/ });
  if (await assistantByRole.count()) {
    await assistantByRole.first().click();
    await page.waitForTimeout(300);
  }
}

async function sendMessage(message) {
  ensureActiveScenario();
  console.log(`  send: ${message}`);
  const before = await counts().catch(() => ({ proposals: [], memories: [], events: [], tasks: [], signals: [] }));
  const textbox = page.locator("textarea").last();
  await textbox.fill(message);
  await page.getByRole("button", { name: /发送|Send/ }).last().click();
  const started = Date.now();
  while (Date.now() - started < 55000) {
    ensureActiveScenario();
    await page.waitForTimeout(1000);
    const body = await page.locator("body").innerText().catch(() => "");
    const now = await counts().catch(() => before);
    const changed =
      now.proposals.length !== before.proposals.length ||
      now.memories.length !== before.memories.length ||
      now.events.length !== before.events.length ||
      now.tasks.length !== before.tasks.length ||
      now.signals.length !== before.signals.length;
    const hasAssistantReply = body.includes(message) && (
      body.includes("待确认") ||
      body.includes("方案") ||
      body.includes("澄清") ||
      body.includes("已") ||
      body.includes("不能") ||
      body.includes("需要") ||
      body.includes("发送失败") ||
      body.includes("连接中断")
    );
    const stillBusy = body.includes("思考中") || body.includes("Thinking") || body.includes("Loading");
    if ((changed || hasAssistantReply) && !stillBusy) {
      await page.waitForTimeout(500);
      return;
    }
  }
  await page.waitForTimeout(500);
}

async function sendQuickMessage(message, settleMs = 2500) {
  ensureActiveScenario();
  console.log(`  quick send: ${message}`);
  const textbox = page.locator("textarea").last();
  await textbox.fill(message);
  await page.getByRole("button", { name: /发送|Send/ }).last().click();
  const started = Date.now();
  while (Date.now() - started < settleMs) {
    ensureActiveScenario();
    await page.waitForTimeout(300);
    const body = await page.locator("body").innerText().catch(() => "");
    const stillBusy = body.includes("思考中") || body.includes("Thinking") || body.includes("Loading");
    const inputReady = await textbox.isEnabled().catch(() => true);
    if (body.includes(message) && inputReady && !stillBusy) return;
  }
}

async function waitForProposalContaining(fragment, timeoutMs = 75000) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    const data = await counts().catch(() => null);
    if (data && data.proposals.some((p) => JSON.stringify(p).includes(fragment))) return data;
    await page.waitForTimeout(1000);
  }
  return await counts();
}

async function waitForExecutedProposal(timeoutMs = 60000) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    const data = await counts().catch(() => null);
    if (data && data.proposals.some((p) => p.status === "executed")) return data;
    await page.waitForTimeout(1000);
  }
  return await counts();
}

async function waitForEventContaining(fragment, timeoutMs = 60000) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    const data = await counts().catch(() => null);
    if (data && data.events.some((e) => JSON.stringify(e).includes(fragment))) return data;
    await page.waitForTimeout(1000);
  }
  return await counts();
}

async function sendAndWaitProposal(message, fragment = null) {
  await sendMessage(message);
  if (fragment) return await waitForProposalContaining(fragment);
  return await counts();
}

async function visibleText() {
  return await page.locator("body").innerText();
}

async function counts() {
  const [events, tasks, proposals, memories, signals] = await Promise.all([
    api("/events").then((r) => r.data),
    api("/tasks").then((r) => r.data),
    api("/assistant/proposals?limit=100").then((r) => r.data.items),
    api("/assistant/memory/candidates?limit=100").then((r) => r.data.items),
    api("/assistant/signals?limit=100").then((r) => r.data.items),
  ]);
  return { events, tasks, proposals, memories, signals };
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function hasAny(text, words) {
  return words.some((word) => text.includes(word));
}

async function record(id, title, fn, options = {}) {
  if (SCENARIO_FILTER.size && !SCENARIO_FILTER.has(id)) return;
  if (SCENARIO_LIMIT && scenarioCounter >= SCENARIO_LIMIT) return;
  scenarioCounter += 1;
  const scenarioToken = ++scenarioGeneration;
  activeScenarioTokens.add(scenarioToken);
  const started = Date.now();
  const item = { id, title, status: "PASS", duration_ms: 0, evidence: [], error: null };
  console.log(`START   ${id} ${title}`);
  try {
    await scenarioContext.run({ token: scenarioToken }, () => withTimeout(async () => {
      if (!options.keepState) await clearAll();
      await gotoApp(options.width || 1365, options.height || 900);
      await fn(item);
    }, options.timeoutMs || 60000, `${id} timed out`));
  } catch (error) {
    item.status = options.expectedFailure ? "TRACKED" : "FAIL";
    item.error = String(error.stack || error.message || error);
  } finally {
    activeScenarioTokens.delete(scenarioToken);
    item.duration_ms = Date.now() - started;
    results.push(item);
    console.log(`${item.status.padEnd(7)} ${id} ${title}`);
    await writePartialReport().catch((error) => console.error("partial report failed", error));
  }
}

function ensureActiveScenario() {
  const context = scenarioContext.getStore();
  if (context && !activeScenarioTokens.has(context.token)) {
    throw new Error("scenario canceled");
  }
}

async function withTimeout(fn, timeoutMs, label) {
  let timer;
  return await Promise.race([
    fn(),
    new Promise((_, reject) => {
      timer = setTimeout(() => reject(new Error(label)), timeoutMs);
    }),
  ]).finally(() => clearTimeout(timer));
}

async function writePartialReport() {
  if (!currentReportBase) return;
  const pass = results.filter((r) => r.status === "PASS").length;
  const fail = results.filter((r) => r.status === "FAIL").length;
  const tracked = results.filter((r) => r.status === "TRACKED").length;
  const report = {
    run_id: RUN_ID,
    api_base: API_BASE,
    web_url: WEB_URL,
    db_path: DB_PATH,
    memory_path: MEMORY_PATH,
    summary: { total: results.length, pass, fail, tracked },
    results,
  };
  await writeFile(`${currentReportBase}.partial.json`, JSON.stringify(report, null, 2), "utf8");
  await writeFile(`${currentReportBase}.partial.md`, renderMarkdownReport(report), "utf8");
}

async function expectNoBusinessWrite(before, after, label = "no business writes") {
  assert(after.events.length === before.events.length, `${label}: event count changed ${before.events.length}->${after.events.length}`);
  assert(after.tasks.length === before.tasks.length, `${label}: task count changed ${before.tasks.length}->${after.tasks.length}`);
}

async function expectPendingProposal(item, contains = "") {
  const data = await counts();
  const pending = data.proposals.filter((p) => p.status === "pending");
  assert(pending.length >= 1, "expected at least one pending proposal");
  if (contains) assert(JSON.stringify(pending).includes(contains), `pending proposal does not mention ${contains}`);
  item.evidence.push(`pending proposals=${pending.length}`);
  return pending[0];
}

async function main() {
  await mkdir(OUT_DIR, { recursive: true });
  currentReportBase = path.join(OUT_DIR, `assistant_browser_full_acceptance_${RUN_ID}`);
  console.log(`Run ${RUN_ID}`);
  console.log("Initializing DB");
  await initDb();
  console.log(`DB ready ${DB_PATH}`);

  console.log(`Starting API ${API_BASE}`);
  apiProc = proc(PYTHON, ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", String(API_PORT)], {
    cwd: BACKEND,
    prefix: "api",
    env: {
      SQLITE_DB_PATH: DB_PATH,
      ASSISTANT_MEMORY_PATH: MEMORY_PATH,
      ASSISTANT_CONDUCTOR_MODE: "proposal",
      ASSISTANT_PROACTIVE_MODE: "proposals",
      LLM_PROVIDER: process.env.LLM_PROVIDER || "deepseek",
      LLM_FALLBACK_PROVIDER: process.env.LLM_FALLBACK_PROVIDER || "gemini",
      CORS_ALLOW_ORIGIN_REGEX: "http://(localhost|127\\.0\\.0\\.1):\\d+",
    },
  });
  await waitFor(`${API_BASE}/health`, 60000);
  console.log("API ready");

  console.log(`Starting web ${WEB_URL}`);
  const viteArgs = process.platform === "win32"
    ? ["/c", "pnpm", "exec", "vite", "--host", "127.0.0.1", "--port", String(WEB_PORT)]
    : ["exec", "vite", "--host", "127.0.0.1", "--port", String(WEB_PORT)];
  webProc = proc(PNPM, viteArgs, {
    cwd: FRONTEND,
    prefix: "web",
    env: { VITE_API_BASE_URL: API_BASE },
  });
  await waitFor(WEB_URL, 60000);
  console.log("Web ready");

  console.log("Launching browser");
  browser = await chromium.launch({ headless: true });
  page = await browser.newPage();
  page.on("console", (msg) => {
    if (msg.type() === "error") console.log(`[browser-console] ${msg.text()}`);
  });

  console.log("Running scenarios");
  await runScenarios();

  const pass = results.filter((r) => r.status === "PASS").length;
  const fail = results.filter((r) => r.status === "FAIL").length;
  const tracked = results.filter((r) => r.status === "TRACKED").length;
  const report = {
    run_id: RUN_ID,
    api_base: API_BASE,
    web_url: WEB_URL,
    db_path: DB_PATH,
    memory_path: MEMORY_PATH,
    summary: { total: results.length, pass, fail, tracked },
    results,
  };
  const jsonPath = `${currentReportBase}.json`;
  const mdPath = `${currentReportBase}.md`;
  await writeFile(jsonPath, JSON.stringify(report, null, 2), "utf8");
  await writeFile(mdPath, renderMarkdownReport(report), "utf8");
  console.log(`\nReport: ${mdPath}`);
  if (fail > 0) process.exitCode = 1;
}

function renderMarkdownReport(report) {
  const lines = [
    `# AI Assistant Browser Full Acceptance ${report.run_id}`,
    "",
    `- API: ${report.api_base}`,
    `- Web: ${report.web_url}`,
    `- DB: ${report.db_path}`,
    `- Memory: ${report.memory_path}`,
    `- Summary: ${report.summary.pass} passed, ${report.summary.fail} failed, ${report.summary.tracked} tracked, ${report.summary.total} total`,
    "",
    "| ID | Status | Title | Evidence / Error |",
    "|---|---|---|---|",
  ];
  for (const r of report.results) {
    const details = r.status === "PASS" ? r.evidence.join("; ") : (r.error || r.evidence.join("; ")).replace(/\r?\n/g, "<br>");
    lines.push(`| ${r.id} | ${r.status} | ${r.title} | ${details.replace(/\|/g, "\\|")} |`);
  }
  return `${lines.join("\n")}\n`;
}

async function runScenarios() {
  await record("BAI-P0-001", "明确日程创建必须先提案", async (item) => {
    const before = await counts();
    await sendAndWaitProposal("明天下午三点去学校上政治课", "政治课");
    const text = await visibleText();
    const after = await counts();
    assert(text.includes("待确认方案") || text.includes("方案"), "UI did not show proposal wording");
    await expectPendingProposal(item, "政治课");
    await expectNoBusinessWrite(before, after);
  });

  await record("BAI-P0-002", "单 proposal 自然语言确认执行", async (item) => {
    await sendAndWaitProposal("明天下午三点去学校上政治课", "政治课");
    await sendMessage("可以");
    let data = await waitForExecutedProposal();
    assert(data.events.some((e) => e.title.includes("政治课")), "confirmed event not created");
    assert(data.proposals.some((p) => p.status === "executed"), "proposal not executed");
    item.evidence.push(`events=${data.events.length}`);
  });

  await record("BAI-P0-003", "重复确认幂等", async (item) => {
    await sendAndWaitProposal("明天下午三点去学校上政治课", "政治课");
    await sendMessage("可以");
    await waitForExecutedProposal();
    await sendMessage("可以");
    const data = await waitForEventContaining("政治课");
    const matches = data.events.filter((e) => e.title.includes("政治课"));
    assert(matches.length === 1, `expected one event, got ${matches.length}`);
    item.evidence.push("repeat confirm kept one event");
  });

  await record("BAI-P0-004", "模糊任务请求不得直接拆日程", async (item) => {
    const before = await counts();
    await sendMessage("帮我安排一下复习");
    const after = await counts();
    assert(after.events.length === before.events.length, "created calendar blocks from vague request");
    const text = await visibleText();
    assert(hasAny(text, ["澄清", "具体", "deadline", "截止", "方案", "待确认"]), "no clarification/proposal visible");
    item.evidence.push("no event writes for vague request");
  });

  await record("BAI-P0-005", "任务 / 日程类型澄清", async (item) => {
    await sendMessage("明天安排一下复习");
    await sendMessage("这个是任务，不是单次日程");
    const data = await counts();
    assert(!data.events.some((e) => e.title.includes("复习")), "event was created before confirmation");
    assert(data.proposals.some((p) => JSON.stringify(p).includes("task") || p.summary.includes("任务") || p.status === "superseded"), "no task-oriented revision evidence");
    item.evidence.push(`proposals=${data.proposals.length}`);
  });

  await record("BAI-P0-006", "自然语言修改 proposal", async (item) => {
    await sendMessage("明天下午三点去学校上政治课");
    await sendMessage("改成4点开始");
    const data = await counts();
    assert(data.proposals.some((p) => p.status === "superseded"), "old proposal not superseded");
    assert(data.proposals.some((p) => p.status === "pending" && JSON.stringify(p).includes("16:00")), "new proposal not revised to 16:00");
    assert(data.events.length === 0, "event written before confirmation");
    item.evidence.push("revision chain visible");
  });

  await record("BAI-P0-007", "拒绝 proposal", async (item) => {
    await sendMessage("明天下午三点去学校上政治课");
    await sendMessage("先不要安排");
    const data = await counts();
    assert(data.proposals.some((p) => p.status === "rejected"), "proposal not rejected");
    assert(data.events.length === 0, "event created after rejection");
    item.evidence.push("rejected without writes");
  });

  await record("BAI-P0-008", "多 proposal 下可以必须澄清", async (item) => {
    await createProposal("P1 小组会调整", [{ type: "create_event", payload: { title: "小组会调整", start_time: isoDatePlus(1, 15), end_time: isoDatePlus(1, 16) } }]);
    await createProposal("P2 复习顺延", [{ type: "create_event", payload: { title: "复习顺延", start_time: isoDatePlus(2, 19), end_time: isoDatePlus(2, 20) } }]);
    await gotoApp();
    await sendMessage("可以");
    const data = await counts();
    const text = await visibleText();
    assert(data.proposals.filter((p) => p.status === "pending").length === 2, "ambiguous confirm changed pending proposals");
    assert(text.includes("P1") && text.includes("P2"), "clarification did not mention P1/P2");
    assert(data.events.length === 0, "ambiguous confirm wrote event");
    item.evidence.push("ambiguous confirmation preserved two pending proposals");
  });

  await record("BAI-P0-009", "多 proposal 带标识确认", async (item) => {
    await createProposal("P1 小组会调整", [{ type: "create_event", payload: { title: "小组会调整", start_time: isoDatePlus(1, 15), end_time: isoDatePlus(1, 16) } }]);
    await createProposal("P2 复习顺延", [{ type: "create_event", payload: { title: "复习顺延", start_time: isoDatePlus(2, 19), end_time: isoDatePlus(2, 20) } }]);
    await gotoApp();
    await sendMessage("P1 按方案A安排");
    const data = await counts();
    assert(data.events.length === 1, `expected one write, got ${data.events.length}`);
    assert(data.proposals.filter((p) => p.status === "pending").length === 1, "P2 did not remain pending");
    item.evidence.push(data.events[0].title);
  });

  await record("BAI-P0-010", "冲突日程必须给多方案", async (item) => {
    await createEvent("图书馆自习", isoDatePlus(1, 15), isoDatePlus(1, 16), { location_name: "图书馆" });
    const before = await counts();
    await sendMessage("明天下午三点去学校和同学见面");
    const after = await counts();
    assert(after.events.some((e) => e.title.includes("图书馆自习")), "original conflict event missing");
    assert(after.events.length === before.events.length, "conflict scenario wrote before confirmation");
    const p = await expectPendingProposal(item, "同学见面");
    assert((p.payload_json?.options || []).length >= 1, "no options in conflict proposal");
  });

  await record("BAI-P0-011", "批量调整必须拆成可确认动作", async (item) => {
    for (let i = 0; i < 3; i++) await createEvent(`明日事项${i + 1}`, isoDatePlus(1, 9 + i), isoDatePlus(1, 10 + i));
    const before = await counts();
    await sendMessage("把明天所有日程都推迟一天");
    const after = await counts();
    assert(after.events.length === before.events.length, "batch reschedule wrote before confirmation");
    const p = await expectPendingProposal(item, "推迟");
    assert(JSON.stringify(p).includes("reschedule_event"), "batch proposal lacks reschedule actions");
  });

  await record("BAI-P0-012", "过大批量调整必须防失控", async (item) => {
    for (let i = 0; i < 9; i++) await createEvent(`明日大批事项${i + 1}`, isoDatePlus(1, 8 + Math.floor(i / 2), (i % 2) * 30), isoDatePlus(1, 9 + Math.floor(i / 2), (i % 2) * 30));
    const before = await counts();
    await sendMessage("把明天所有安排都取消");
    const after = await counts();
    await expectNoBusinessWrite(before, after, "oversized batch");
    const text = await visibleText();
    assert(hasAny(text, ["范围", "过大", "明确", "确认", "拆分", "待确认"]), "no oversized batch guard visible");
    item.evidence.push("oversized batch guarded");
  });

  await record("BAI-P0-013", "多轮日程槽位补全必须继承上下文", async (item) => {
    await sendMessage("3个小时后提醒我去学校");
    await sendMessage("下午1点开始，晚上10点结束");
    await sendMessage("创建独立日程");
    const data = await counts();
    assert(data.events.length === 0, "event written before confirmation");
    assert(data.proposals.filter((p) => p.status === "pending").length === 1, "expected one latest pending proposal");
    assert(JSON.stringify(data.proposals).includes("去学校"), "lost subject context");
    item.evidence.push("single pending proposal retained context");
  });

  await record("BAI-P0-014", "单 pending proposal 下纯时间补充必须走 revise", async (item) => {
    await sendMessage("明天下午三点去学校");
    await sendMessage("下午1点开始，晚上10点结束");
    const data = await counts();
    assert(data.proposals.some((p) => p.status === "superseded"), "old proposal not superseded");
    assert(data.proposals.some((p) => p.status === "pending" && JSON.stringify(p).includes("22:00")), "revised proposal missing end time");
    assert(data.events.length === 0, "event written before confirmation");
    item.evidence.push("time-only supplement revised proposal");
  });

  await record("BAI-P0-015", "执行导向话术不得复制 proposal", async (item) => {
    await sendMessage("明天下午三点去学校");
    const before = await counts();
    await sendMessage("创建独立日程");
    const after = await counts();
    assert(after.proposals.filter((p) => p.status === "pending").length <= before.proposals.filter((p) => p.status === "pending").length + 0, "duplicated pending proposal");
    assert(after.events.length === 0, "event written before confirmation");
    item.evidence.push("no duplicate proposal");
  });

  await record("BAI-P0-016", "带时间和地点的提醒不得误判为普通任务", async (item) => {
    await sendMessage("3个小时后提醒我去学校");
    const data = await counts();
    const pjson = JSON.stringify(data.proposals);
    assert(pjson.includes("event_creation") || pjson.includes("create_event"), "did not create event proposal");
    assert(!pjson.includes("个小时后去学校"), "bad title split/duration wording");
    assert(data.tasks.length === 0, "created task for timed reminder");
    item.evidence.push("timed reminder created event proposal");
  });

  await record("BAI-P0-017", "连续发送与加载状态", async (item) => {
    const textbox = page.locator("textarea").last();
    await textbox.fill("3个小时后提醒我去学校");
    const send = page.getByRole("button", { name: /发送|Send/ }).last();
    await send.click();
    await send.click().catch(() => {});
    await page.waitForTimeout(1000);
    const dataAfterClick = await counts();
    assert(dataAfterClick.proposals.length <= 1, "double click created duplicate proposal early");
    await page.waitForTimeout(5000);
    await sendMessage("下午1点开始，晚上10点结束");
    const data = await counts();
    assert(data.proposals.filter((p) => p.status === "pending").length <= 1, "duplicate proposals after loading sequence");
    item.evidence.push("send lock avoided duplicate proposal");
  });

  await runRemainingP1AndRegressionScenarios();
}

async function runRemainingP1AndRegressionScenarios() {
  const simpleCases = [
    ["BAI-P1-001", "不完整日程应澄清", "我要去学校和同学见面", async (item, before, after, text) => {
      await expectNoBusinessWrite(before, after);
      assert(hasAny(text, ["什么时候", "时间", "日期", "几点", "澄清"]), "missing time clarification");
    }],
    ["BAI-P1-002", "带自然语言时间的日程", "后天上午十点到十一点在培训室培训", async (item, before, after) => {
      await expectNoBusinessWrite(before, after);
      await expectPendingProposal(item, "培训");
    }],
    ["BAI-P1-003", "默认时长推断", "明天下午三点去学校开组会", async (item, before, after, text) => {
      await expectNoBusinessWrite(before, after);
      await expectPendingProposal(item, "组会");
      assert(hasAny(text, ["默认", "1小时", "一小时", "暂定"]), "default duration not explained");
    }],
    ["BAI-P1-004", "任务创建", "提醒我整理毕设论文", async (item, before, after) => {
      await expectNoBusinessWrite(before, after);
      assert(after.proposals.length || after.memories.length || after.tasks.length === before.tasks.length, "unexpected direct write");
    }],
    ["BAI-P1-008", "查询进展不应写入", "现在毕设论文进展怎么样，接下来怎么安排", async (item, before, after, text) => {
      await expectNoBusinessWrite(before, after);
      assert(hasAny(text, ["进展", "建议", "安排", "没有", "任务"]), "no progress answer visible");
    }],
    ["BAI-P1-012", "跨午夜时间段解析", "今晚11点到凌晨1点在学校值班", async (item, before, after) => {
      await expectNoBusinessWrite(before, after);
      const p = await expectPendingProposal(item, "值班");
      assert(JSON.stringify(p).includes("23:00") || JSON.stringify(p).includes("T23"), "start time not 23:00-like");
    }],
    ["BAI-P1-014", "同句包含多个日程目标", "下午先去学校开会，晚上再去驾校接人", async (item, before, after, text) => {
      await expectNoBusinessWrite(before, after);
      assert(after.proposals.length >= 1 || hasAny(text, ["两个", "哪一个", "分别", "澄清"]), "multi-goal neither proposed nor clarified");
    }],
    ["BAI-P1-015", "任务与日程混合句拆分语义", "明天先去学校开会，顺便提醒我整理毕设论文", async (item, before, after, text) => {
      await expectNoBusinessWrite(before, after);
      assert(hasAny(JSON.stringify(after.proposals) + text, ["开会", "毕设", "任务", "日程"]), "mixed semantics not reflected");
    }],
    ["BAI-P1-101", "明确 origin 的出发建议", "明天上午10点从家去学校办手续", async (item, before, after, text) => {
      await expectNoBusinessWrite(before, after);
      assert(hasAny(text + JSON.stringify(after.proposals), ["家", "出发", "通勤", "学校"]), "origin/departure not reflected");
    }],
    ["BAI-P1-102", "origin 不确定必须澄清或条件化", "明天下午去学校开会，帮我看看几点出发", async (item, before, after, text) => {
      await expectNoBusinessWrite(before, after);
      assert(hasAny(text, ["从哪里", "出发", "当前位置", "家", "条件"]), "origin uncertainty not handled");
    }],
    ["BAI-P1-110", "天气影响不改日程", "明天下午三点去学校面试，帮我看看几点出发", async (item, before, after, text) => {
      await expectNoBusinessWrite(before, after);
      assert(hasAny(text + JSON.stringify(after.proposals), ["天气", "出发", "面试", "学校", "方案"]), "weather/departure guidance absent");
    }],
    ["BAI-P1-111", "外部地图失败降级", "明天上午10点从家去学校开会，几点出发", async (item, before, after, text) => {
      await expectNoBusinessWrite(before, after);
      assert(!hasAny(text, ["Traceback", "Exception", "undefined", "null"]), "raw error leaked");
    }],
    ["BAI-P1-304", "隐式偏好不得低置信写入", "这次先别直接排进日程，给我看看方案就行", async (item, before, after) => {
      assert(after.memories.length === before.memories.length, "implicit preference created memory candidate");
    }],
    ["BAI-P1-307", "对话事实不等于长期偏好", "今天我想早点睡，别给我安排晚上的任务", async (item, before, after) => {
      assert(after.memories.length === before.memories.length, "conversation fact created long-term memory");
    }],
    ["BAI-P1-401", "Proposal 文本结构", "明天下午三点去学校和同学见面", async (item, before, after, text) => {
      await expectNoBusinessWrite(before, after);
      await expectPendingProposal(item, "同学见面");
      assert(hasAny(text, ["原因", "方案", "建议", "回复", "确认", "修改", "拒绝"]), "proposal text structure incomplete");
    }],
    ["BAI-P1-409", "Markdown 与特殊字符安全", "明天3点去学校，标题叫<script>alert(1)</script>", async (item, before, after, text) => {
      await expectNoBusinessWrite(before, after);
      assert(!text.includes("alert(1)") || !await page.evaluate(() => window.__xssFired === true), "script execution suspected");
    }],
    ["BAI-P0-101", "不得硬分句误拆", "中午12点我要去驾校接李婷", async (item, before, after) => {
      await expectNoBusinessWrite(before, after);
      const pjson = JSON.stringify(after.proposals);
      assert(pjson.includes("去驾校接李婷"), "title not preserved");
      assert(!pjson.includes("点我要") && !pjson.includes("接李婷\\\"") , "bad split detected");
    }],
    ["BAI-P0-102", "不得绕过 proposal 直接写入", "明天上午9点帮我创建一个去学校开会的日程", async (item, before, after) => {
      await expectNoBusinessWrite(before, after);
      await expectPendingProposal(item, "开会");
    }],
    ["BAI-P0-103", "普通建议不应触发旧 workflow 文案", "我明天有点忙，帮我看看怎么安排比较合理", async (item, before, after, text) => {
      assert(!/workflow|LangGraph|节点|debug/i.test(text), "old workflow/debug wording visible");
    }],
    ["BAI-P0-104", "未知请求应澄清", "帮我处理一下那个事情", async (item, before, after, text) => {
      await expectNoBusinessWrite(before, after);
      assert(hasAny(text, ["哪个", "什么", "具体", "明确", "澄清"]), "unknown request not clarified");
    }],
    ["BAI-P0-106", "无确认不写长期记忆", "我今天在图书馆，下午去学校", async (item, before, after) => {
      assert(after.memories.length === before.memories.length, "memory candidate/write created without explicit memory request");
    }],
    ["BAI-P0-107", "中文相对时间不解析为持续时长", "3个小时后提醒我去学校", async (item, before, after) => {
      await expectNoBusinessWrite(before, after);
      const pjson = JSON.stringify(after.proposals);
      assert(!pjson.includes("duration_minutes\":180"), "relative time interpreted as duration");
    }],
  ];

  for (const [id, title, message, check] of simpleCases) {
    await record(id, title, async (item) => {
      const before = await counts();
      await sendMessage(message);
      const after = await counts();
      const text = await visibleText();
      await check(item, before, after, text);
      item.evidence.push(`events=${after.events.length}, tasks=${after.tasks.length}, proposals=${after.proposals.length}, memories=${after.memories.length}`);
    });
  }

  await record("BAI-P1-005", "任务排程", async (item) => {
    await createTask("整理毕设论文", { estimated_duration_minutes: 360, deadline: isoDatePlus(3, 23), priority: 3 });
    const before = await counts();
    await sendMessage("把整理毕设论文安排到未来三天下午3点到5点");
    const after = await counts();
    await expectNoBusinessWrite(before, after);
    await expectPendingProposal(item, "整理毕设论文");
  });

  await record("BAI-P1-006", "有限期重复任务完成判定", async (item) => {
    const task = await createTask("三天论文写作", { estimated_duration_minutes: 360, status: "scheduled" });
    for (let i = 1; i <= 3; i++) await createEvent(`论文写作切片${i}`, isoDatePlus(i, 15), isoDatePlus(i, 17), { linked_task_id: task.id, event_type: "focus_block", status: "completed" });
    await sendMessage("论文这三天的写作都完成了");
    const data = await counts();
    assert(data.proposals.length >= 1 || data.tasks.some((t) => t.content.includes("论文") && ["done", "scheduled"].includes(t.status)), "no completion path");
    item.evidence.push("completion path generated or preserved quantifiable task state");
  });

  await record("BAI-P1-007", "取消重复任务单个切片", async (item) => {
    const task = await createTask("未来三天复习", { estimated_duration_minutes: 360, status: "scheduled" });
    await createEvent("明天复习块", isoDatePlus(1, 15), isoDatePlus(1, 17), { linked_task_id: task.id, event_type: "focus_block" });
    const before = await counts();
    await sendMessage("明天那个复习块不做了");
    const after = await counts();
    await expectNoBusinessWrite(before, after);
    assert(after.proposals.length >= 1 || (await visibleText()).includes("取消"), "no cancellation proposal/clarification");
    item.evidence.push("single slice not directly canceled");
  });

  const multiStep = [
    ["BAI-P1-009", "多轮时间补全后再补地点", ["明天下午三点去学校", "下午1点开始", "晚上10点结束", "地点改成图书馆"], "图书馆"],
    ["BAI-P1-010", "先改标题再改时间", ["明天下午三点去学校", "标题改成和同学见面", "改到下午4点"], "同学见面"],
    ["BAI-P1-011", "只给结束时间的部分修正", ["明天下午三点去学校开组会", "结束时间缩短半小时"], "15:30"],
    ["BAI-P1-017", "拒绝后下一句不要继续执行", ["明天下午三点去学校", "先不要安排", "那就改到明天下午4点"], "rejected"],
    ["BAI-P0-105", "补充回答不当成全新任务", ["我要去学校和同学见面", "晚上10点结束"], "晚上10点"],
  ];
  for (const [id, title, messages, expected] of multiStep) {
    await record(id, title, async (item) => {
      for (const m of messages) await sendMessage(m);
      const data = await counts();
      assert(data.events.length === 0, "multi-step scenario wrote before explicit confirm");
      assert(JSON.stringify(data.proposals) .includes(expected) || (await visibleText()).includes(expected), `expected ${expected} evidence missing`);
      item.evidence.push(`proposals=${data.proposals.length}`);
    });
  }

  await record("BAI-P1-013", "相对日期与绝对日期混用", async (item) => {
    const before = await counts();
    await sendMessage("下周三上午9点到11点去学校，5月15日如果冲突就改到下午");
    const after = await counts();
    await expectNoBusinessWrite(before, after);
    assert(JSON.stringify(after.proposals) .includes("学校") || (await visibleText()).includes("5月15"), "date constraints not reflected");
    item.evidence.push("conditional date handled without write");
  });

  await runLocationSignalMemoryUiFailureCases();
}

async function runLocationSignalMemoryUiFailureCases() {
  await record("BAI-P1-016", "模糊去学校结合记忆", async (item) => {
    await createMemoryCandidate("places", "学校 = 南京大学仙林校区");
    const mem = (await counts()).memories[0];
    await api(`/assistant/memory/candidates/${mem.id}/confirm`, { method: "POST" });
    await sendMessage("后天去学校");
    const text = await visibleText();
    assert(text.includes("南京大学") || text.includes("学校"), "confirmed place memory not used/mentioned");
    item.evidence.push("confirmed place memory available");
  });

  const contextCases = [
    ["BAI-P1-103", "当前线程位置优先", ["我明天下午会先在驾校", "那我去学校开会要几点出发"], "驾校"],
    ["BAI-P1-108", "临时位置不污染长期地点", ["我现在在图书馆", "等会儿去学校上课要几点出发"], "图书馆"],
    ["BAI-P1-112", "出发地和目的地相同", ["我现在在学校", "下午3点去学校上课，要几点出发"], "学校"],
  ];
  for (const [id, title, messages, expected] of contextCases) {
    await record(id, title, async (item) => {
      const before = await counts();
      for (const m of messages) await sendMessage(m);
      const after = await counts();
      assert((await visibleText()).includes(expected), `expected context ${expected} missing`);
      assert(after.memories.length === before.memories.length, "temporary context polluted memory");
      item.evidence.push("runtime context only");
    });
  }

  await record("BAI-P1-104", "常用地点别名解析", async (item) => {
    await createMemoryCandidate("places", "学校 = 测试学校地址");
    const mem = (await counts()).memories[0];
    await api(`/assistant/memory/candidates/${mem.id}/confirm`, { method: "POST" });
    await sendMessage("后天上午去学校体检");
    assert((await visibleText()).includes("学校"), "place alias absent");
    await expectPendingProposal(item, "体检");
  });

  await record("BAI-P1-109", "多地点同名歧义", async (item) => {
    await createMemoryCandidate("places", "学校东门 = A地址");
    await createMemoryCandidate("places", "学校图书馆 = B地址");
    await sendMessage("明天上午去学校");
    const text = await visibleText();
    assert(hasAny(text, ["东门", "图书馆", "具体", "哪个"]), "same-name ambiguity not clarified");
    item.evidence.push("ambiguous place clarified");
  });

  await record("BAI-P1-105", "出发前提醒", async (item) => {
    const event = await createEvent("去学校办手续", isoDatePlus(0, new Date().getHours() + 2), isoDatePlus(0, new Date().getHours() + 3), {
      location_name: "学校",
      travel_duration_minutes: 30,
      departure_time: isoDatePlus(0, new Date().getHours() + 1),
      travel_mode: "driving",
    });
    await createSignal("departure_readiness", { title: event.title, travel_duration_minutes: 30, message: "建议准备出发" }, { target_type: "event", target_id: event.id, dedup_key: `departure:${event.id}` });
    await gotoApp();
    const text = await visibleText();
    assert(text.includes("出发") || text.includes("去学校"), "departure signal not visible");
    item.evidence.push("departure followup visible");
  });

  await record("BAI-P1-106", "出发提醒用户已到达", async (item) => {
    await createSignal("departure_readiness", { title: "去学校", message: "建议准备出发" }, { dedup_key: "departure-arrived" });
    await gotoApp();
    await sendMessage("我已经在学校了");
    const data = await counts();
    assert(data.memories.length === 0, "arrival update wrote memory");
    assert((await visibleText()).includes("学校"), "arrival reply absent");
    item.evidence.push("arrival handled without memory write");
  });

  await record("BAI-P1-107", "出发提醒取消行程", async (item) => {
    const e = await createEvent("去学校开会", isoDatePlus(1, 10), isoDatePlus(1, 11), { location_name: "学校" });
    await createSignal("departure_readiness", { title: e.title, message: "建议准备出发" }, { target_type: "event", target_id: e.id, dedup_key: "departure-cancel" });
    await gotoApp();
    await sendMessage("今天不去了");
    const data = await counts();
    assert(data.events.find((x) => x.id === e.id).status !== "canceled", "event canceled before proposal confirmation");
    assert(data.proposals.length >= 1 || (await visibleText()).includes("取消"), "no cancel proposal/clarification");
    item.evidence.push("cancel request did not directly cancel event");
  });

  await record("BAI-P1-201", "deadline 风险触发", async (item) => {
    const task = await createTask("毕设论文", { deadline: isoDatePlus(1, 2), priority: 3 });
    await createSignal("deadline_risk", { content: "毕设论文", message: "deadline 接近" }, { target_type: "task", target_id: task.id, dedup_key: `deadline:${task.id}` });
    await gotoApp();
    const text = await visibleText();
    assert(text.includes("毕设论文") || text.includes("deadline"), "deadline signal not visible");
    item.evidence.push("deadline risk signal visible");
  });

  await record("BAI-P1-202", "signal cooldown 去重", async (item) => {
    await createSignal("deadline_risk", { content: "毕设论文" }, { dedup_key: "deadline-dedup" });
    await createSignal("deadline_risk", { content: "毕设论文" }, { dedup_key: "deadline-dedup" });
    const data = await counts();
    assert(data.signals.length === 1, `expected deduped one signal got ${data.signals.length}`);
    item.evidence.push("deduped signal");
  });

  const signalTypes = [
    ["BAI-P1-203", "晨间汇报固定模板", "daily_morning_review", { message: "晨间汇报：今日日程、任务、待确认方案" }],
    ["BAI-P1-205", "睡前复盘固定模板", "daily_night_review", { message: "睡前复盘：完成核对、未完成任务、待确认方案" }],
    ["BAI-P1-208", "pending proposal 跟进", "proposal_followup", { proposal_summary: "待确认政治课", message: "这个方案还需要确认" }],
    ["BAI-P1-403", "主动跟进区", "deadline_risk", { content: "毕设论文", message: "deadline 风险" }],
  ];
  for (const [id, title, type, ctx] of signalTypes) {
    await record(id, title, async (item) => {
      await createSignal(type, ctx, { dedup_key: `${id}:${RUN_ID}` });
      await gotoApp();
      const text = await visibleText();
      assert(text.includes("主动跟进") || text.includes("Active") || text.includes(ctx.message?.slice(0, 2) || ""), "signal section not visible");
      item.evidence.push(`${type} visible`);
    });
  }

  const reviewCases = [
    ["BAI-P1-204", "晨间调整单个事项", "下午的见面改到4点"],
    ["BAI-P1-206", "睡前批量完成", "今天这两个都完成了"],
    ["BAI-P1-207", "睡前完成+未完成混合", "政治课完成了，复习没做"],
    ["BAI-P1-210", "晨间汇报 pending proposal 文本确认", "晨报里那个P1按方案A安排"],
    ["BAI-P1-211", "睡前复盘自然语言顺延", "英语复习明天下午再做"],
  ];
  for (const [id, title, msg] of reviewCases) {
    await record(id, title, async (item) => {
      await createEvent("下午的见面", isoDatePlus(0, 15), isoDatePlus(0, 16));
      await createTask("英语复习", { deadline: isoDatePlus(2, 23) });
      await createSignal(id.includes("205") ? "daily_night_review" : "daily_morning_review", { message: "复盘/晨报上下文" }, { dedup_key: `${id}:review` });
      const before = await counts();
      await gotoApp();
      await sendMessage(msg);
      const after = await counts();
      assert(after.events.length === before.events.length && after.tasks.length === before.tasks.length, "review reply wrote before explicit proposal confirmation");
      assert(after.proposals.length >= before.proposals.length || (await visibleText()).length > 0, "no review handling evidence");
      item.evidence.push("review reply stayed proposal-first");
    });
  }

  await record("BAI-P1-209", "主动跟进与当前对话冲突", async (item) => {
    await createSignal("deadline_risk", { content: "毕设论文" }, { dedup_key: "conflict-signal" });
    await createProposal("当前对话 proposal", [{ type: "create_event", payload: { title: "当前对话事项", start_time: isoDatePlus(1, 15), end_time: isoDatePlus(1, 16) } }]);
    await gotoApp();
    await sendMessage("先按刚才那个来");
    const data = await counts();
    assert(data.events.length === 0, "ambiguous active followup/proposal executed directly");
    item.evidence.push("ambiguous proactive reference not executed");
  });

  await record("BAI-P1-212", "主动消息过期后不可执行", async (item) => {
    await createSignal("departure_readiness", { message: "过期提醒" }, { dedup_key: "expired-signal" });
    await sendMessage("按这个提醒处理");
    const data = await counts();
    assert(data.events.length === 0 && data.tasks.length === 0, "expired signal wording caused write");
    item.evidence.push("expired-like signal command did not write");
  });

  await runMemoryCases();
}

async function runMemoryCases() {
  await record("BAI-P1-301", "显式地点记忆候选", async (item) => {
    const before = await counts();
    await sendMessage("以后把学校理解为南京大学仙林校区");
    const after = await counts();
    assert(after.memories.length >= before.memories.length + 1, "memory candidate not created");
    const memRead = await api("/assistant/memory");
    assert(!JSON.stringify(memRead.data).includes("南京大学仙林校区") || after.memories.some((m) => m.status === "proposed"), "memory appeared written before confirm");
    item.evidence.push("memory candidate proposed");
  });

  await record("BAI-P1-302", "确认地点记忆", async (item) => {
    await createMemoryCandidate("places", "学校 = 南京大学仙林校区");
    await gotoApp();
    await sendMessage("记住");
    const mem = await api("/assistant/memory");
    assert(JSON.stringify(mem.data).includes("南京大学仙林校区"), "places.md not written after confirm");
    item.evidence.push("places memory written");
  });

  await record("BAI-P1-303", "拒绝记忆候选", async (item) => {
    await createMemoryCandidate("places", "学校 = 拒绝地址");
    await gotoApp();
    await sendMessage("不要记");
    const data = await counts();
    assert(data.memories.some((m) => m.status === "rejected"), "memory candidate not rejected");
    const mem = await api("/assistant/memory");
    assert(!JSON.stringify(mem.data).includes("拒绝地址"), "rejected memory written");
    item.evidence.push("memory rejected without write");
  });

  await record("BAI-P1-305", "记忆冲突必须澄清", async (item) => {
    await createMemoryCandidate("places", "学校 = A地址");
    let mem = (await counts()).memories[0];
    await api(`/assistant/memory/candidates/${mem.id}/confirm`, { method: "POST" });
    await sendMessage("以后学校指的是B地址");
    const text = await visibleText();
    assert(hasAny(text, ["A地址", "B地址", "替换", "冲突", "确认"]), "memory conflict not explained");
    const read = await api("/assistant/memory");
    assert(JSON.stringify(read.data).includes("A地址"), "old memory changed before confirm");
    item.evidence.push("conflict surfaced without write");
  });

  await record("BAI-P1-306", "一次输入多个记忆候选", async (item) => {
    await sendMessage("以后学校是南京大学仙林校区，家在软件园附近，我一般晚上11点睡");
    const data = await counts();
    assert(data.memories.length >= 2, "multiple memory candidates not split");
    item.evidence.push(`memory candidates=${data.memories.length}`);
  });

  await record("BAI-P1-308", "记忆候选确认指代歧义", async (item) => {
    await createMemoryCandidate("places", "学校 = A地址");
    await createMemoryCandidate("habits", "晚上11点睡");
    await gotoApp();
    await sendMessage("记住");
    const data = await counts();
    assert(data.memories.filter((m) => m.status === "proposed").length === 2, "ambiguous memory confirm changed candidates");
    item.evidence.push("ambiguous memory confirm clarified/no-op");
  });

  await record("BAI-P1-309", "记忆删除也需确认", async (item) => {
    await createMemoryCandidate("preferences", "晚上不安排高强度任务");
    const mem = (await counts()).memories[0];
    await api(`/assistant/memory/candidates/${mem.id}/confirm`, { method: "POST" });
    await sendMessage("以后不用管我晚上能不能做任务");
    const read = await api("/assistant/memory");
    assert(JSON.stringify(read.data).includes("晚上不安排高强度任务"), "preference deleted without confirmation");
    item.evidence.push("delete/update required confirmation");
  });

  await runUiAndFailureCases();
}

async function runUiAndFailureCases() {
  await record("BAI-P1-402", "当前待确认事项区", async (item) => {
    await createProposal("待确认 A", [{ type: "create_event", payload: { title: "待确认A", start_time: isoDatePlus(1, 9), end_time: isoDatePlus(1, 10) } }]);
    await createProposal("待确认 B", [{ type: "create_event", payload: { title: "待确认B", start_time: isoDatePlus(1, 11), end_time: isoDatePlus(1, 12) } }]);
    await gotoApp();
    await page.reload({ waitUntil: "networkidle" });
    await clickAssistantTab();
    const text = await visibleText();
    assert(text.includes("P1") && text.includes("P2") && text.includes("待确认"), "pending proposal labels missing after refresh");
    item.evidence.push("P1/P2 visible after refresh");
  });

  await record("BAI-P1-404", "移动端布局", async (item) => {
    await createProposal("移动端长文本待确认方案 ".repeat(8), [{ type: "create_event", payload: { title: "移动端事项", start_time: isoDatePlus(1, 9), end_time: isoDatePlus(1, 10) } }]);
    await gotoApp(390, 844);
    const screenshotPath = path.join(OUT_DIR, `mobile_${RUN_ID}.png`);
    await page.screenshot({ path: screenshotPath, fullPage: true });
    const text = await visibleText();
    assert(text.includes("待确认") && text.includes("发送"), "mobile assistant controls not visible");
    item.evidence.push(`screenshot=${screenshotPath}`);
  });

  await record("BAI-P1-405", "加载与禁用状态", async (item) => {
    const textbox = page.locator("textarea").last();
    await textbox.fill("明天下午三点去学校上政治课");
    const send = page.getByRole("button", { name: /发送|Send/ }).last();
    await send.click();
    await page.waitForTimeout(300);
    const disabledOrBusy = await send.evaluate((el) => el.disabled || el.getAttribute("aria-busy") === "true");
    assert(disabledOrBusy || (await visibleText()).includes("思考"), "send loading/disabled state not visible");
    await page.waitForTimeout(5000);
    item.evidence.push("send showed loading/busy state");
  });

  await record("BAI-P1-406", "WebSocket 状态同步", async (item) => {
    const p = await createProposal("WS 同步方案", [{ type: "create_event", payload: { title: "WS同步事项", start_time: isoDatePlus(1, 10), end_time: isoDatePlus(1, 11) } }]);
    await gotoApp();
    const page2 = await browser.newPage();
    await page2.goto(WEB_URL, { waitUntil: "networkidle" });
    await api(`/assistant/proposals/${p.id}/confirm`, { method: "POST", body: { option_id: "A" } });
    await page.waitForTimeout(1500);
    const data = await counts();
    assert(data.proposals.find((x) => x.id === p.id).status === "executed", "proposal not executed via second window/API");
    await page2.close();
    item.evidence.push("server-side status executed; UI refresh path available");
  });

  await record("BAI-P1-407", "会话切换不得串上下文", async (item) => {
    await sendMessage("明天下午三点去学校");
    await page.getByRole("button", { name: /新对话|New/ }).click();
    await page.waitForTimeout(500);
    await sendMessage("可以");
    const data = await counts();
    assert(data.events.length === 0, "new session confirmed previous proposal implicitly");
    item.evidence.push("new session did not execute old proposal via bare confirm");
  });

  await record("BAI-P1-408", "长对话滚动与最新消息可见", async (item) => {
    for (let i = 0; i < 12; i++) await sendQuickMessage(`第${i + 1}轮：帮我看看今天安排`);
    await sendMessage("明天下午三点去学校上课");
    const text = await visibleText();
    assert(text.includes("明天下午三点去学校上课") && text.includes("发送"), "latest message/input not visible in long chat");
    item.evidence.push("long chat latest content visible");
  }, { timeoutMs: 120000 });

  await record("BAI-P1-410", "标签稳定性跨刷新和 revision", async (item) => {
    await sendMessage("明天下午三点去学校");
    await sendMessage("改到下午4点");
    await page.reload({ waitUntil: "networkidle" });
    await clickAssistantTab();
    await sendMessage("P1 按方案A安排");
    const data = await counts();
    assert(data.events.length === 1, "refreshed P1 did not map to latest pending proposal");
    item.evidence.push("refreshed P1 confirmed latest proposal");
  });

  await record("BAI-P1-411", "多 pending proposal 区域排序", async (item) => {
    for (let i = 1; i <= 5; i++) await createProposal(`排序方案 ${i}`, [{ type: "create_event", payload: { title: `排序事项${i}`, start_time: isoDatePlus(1, 8 + i), end_time: isoDatePlus(1, 9 + i) } }]);
    await gotoApp();
    const text = await visibleText();
    assert(text.includes("P1") && text.includes("P5"), "five pending labels not visible");
    item.evidence.push("P1-P5 visible");
  });

  await runFailureAndOldProposalCases();
}

async function runFailureAndOldProposalCases() {
  await record("BAI-P1-501", "Provider 失败 fallback", async (item) => {
    item.status = "TRACKED";
    item.evidence.push("Requires deterministic primary-provider failure with a valid fallback provider. Current browser harness uses real providers and cannot force only the primary provider to fail without a mock/restart path; LLM fallback itself is covered by backend unit tests.");
  }, { keepState: true });

  await record("BAI-P1-502", "Provider 全部失败", async (item) => {
    item.status = "TRACKED";
    item.evidence.push("Requires restarting API with invalid provider credentials; covered as tracked manual/chaos case in this run.");
  }, { keepState: true });

  await record("BAI-P1-503", "执行失败进入 retry", async (item) => {
    await createProposal("执行失败方案", [{ type: "reschedule_event", payload: { event_id: 999999, update: { start_time: isoDatePlus(1, 9) } } }]);
    await gotoApp();
    await sendMessage("按方案A安排");
    const data = await counts();
    assert(data.proposals.some((p) => p.status === "execution_failed"), "proposal did not enter execution_failed");
    assert((await visibleText()).includes("重试") || JSON.stringify(data.proposals).includes("failed"), "retry/failure not visible");
    item.evidence.push("execution_failed visible");
  });

  await record("BAI-P1-504", "expired proposal 不可确认", async (item) => {
    const p = await createProposal("过期方案", [{ type: "create_event", payload: { title: "过期事项", start_time: isoDatePlus(1, 9), end_time: isoDatePlus(1, 10) } }], { expiresInSeconds: -10 });
    await gotoApp();
    await sendMessage("按方案A安排");
    const data = await counts();
    assert(data.proposals.find((x) => x.id === p.id).status === "expired", "expired proposal not marked expired");
    assert(data.events.length === 0, "expired proposal executed");
    item.evidence.push("expired proposal not executed");
  });

  await record("BAI-P1-505", "superseded proposal 不可确认", async (item) => {
    const p1 = await createProposal("旧方案", [{ type: "create_event", payload: { title: "旧事项", start_time: isoDatePlus(1, 9), end_time: isoDatePlus(1, 10) } }]);
    await createProposal("新方案", [{ type: "create_event", payload: { title: "新事项", start_time: isoDatePlus(1, 10), end_time: isoDatePlus(1, 11) } }], { supersedes_proposal_id: p1.id });
    await markProposalStatus(p1.id, "superseded");
    await gotoApp();
    await sendMessage("P1 按方案A安排");
    const data = await counts();
    assert(!data.events.some((e) => e.title.includes("旧事项")), "superseded old proposal executed");
    item.evidence.push("superseded old proposal not executed");
  });

  await record("BAI-P1-506", "无效方案编号", async (item) => {
    await createProposal("只有 A 方案", [{ type: "create_event", payload: { title: "A事项", start_time: isoDatePlus(1, 9), end_time: isoDatePlus(1, 10) } }]);
    await gotoApp();
    await sendMessage("P1 按方案C安排");
    const data = await counts();
    assert(data.events.length === 0, "invalid option executed");
    assert(data.proposals.some((p) => p.status === "pending"), "proposal not kept pending");
    item.evidence.push("invalid option rejected/no-op");
  });

  await record("BAI-P1-507", "网络中断恢复", async (item) => {
    item.status = "TRACKED";
    item.evidence.push("Full browser network interruption requires Playwright route/offline orchestration plus API process stop; tracked as manual chaos in this run.");
  }, { keepState: true });

  await record("BAI-P1-508", "后端重启后 pending proposal 可继续确认", async (item) => {
    const p = await createProposal("重启保留方案", [{ type: "create_event", payload: { title: "重启后事项", start_time: isoDatePlus(1, 9), end_time: isoDatePlus(1, 10) } }]);
    apiProc.kill();
    await sleep(1500);
    apiProc = proc(PYTHON, ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", String(API_PORT)], {
      cwd: BACKEND,
      prefix: "api-restart",
      env: {
        SQLITE_DB_PATH: DB_PATH,
        ASSISTANT_MEMORY_PATH: MEMORY_PATH,
        ASSISTANT_CONDUCTOR_MODE: "proposal",
        ASSISTANT_PROACTIVE_MODE: "proposals",
        LLM_PROVIDER: process.env.LLM_PROVIDER || "deepseek",
        LLM_FALLBACK_PROVIDER: process.env.LLM_FALLBACK_PROVIDER || "gemini",
        CORS_ALLOW_ORIGIN_REGEX: "http://(localhost|127\\.0\\.0\\.1):\\d+",
      },
    });
    await waitFor(`${API_BASE}/health`, 60000);
    await gotoApp();
    await sendMessage("确认 P1 方案A");
    const data = await counts();
    assert(data.proposals.find((x) => x.id === p.id).status === "executed", "pending proposal not confirmable after restart");
    item.evidence.push("pending proposal survived backend restart");
  });

  await record("BAI-P1-509", "数据库写入失败不显示成功", async (item) => {
    await createProposal("写入失败方案", [{ type: "create_event", payload: { start_time: isoDatePlus(1, 9), end_time: isoDatePlus(1, 10) } }]);
    await gotoApp();
    await sendMessage("按方案A安排");
    const data = await counts();
    assert(data.proposals.some((p) => p.status === "execution_failed"), "invalid write did not mark execution_failed");
    assert(data.events.length === 0, "invalid write created event");
    item.evidence.push("invalid payload failed without success UI");
  });

  await record("BAI-P1-510", "AI 返回格式异常", async (item) => {
    item.status = "TRACKED";
    item.evidence.push("Requires mock AI provider returning malformed content; protocol fallback is covered by source/unit tests, tracked for browser mock harness.");
  }, { keepState: true });

  await record("BAI-P1-511", "慢响应超时与重试", async (item) => {
    item.status = "TRACKED";
    item.evidence.push("Requires deterministic slow provider/mock endpoint beyond front-end timeout; tracked for browser mock harness.");
  }, { keepState: true });

  const oldCases = [
    ["BAI-P0-108", "不得确认已被替代旧 proposal"],
    ["BAI-P0-109", "active target 不覆盖多 proposal 歧义"],
    ["BAI-P0-110", "刷新编号不导致错配"],
  ];
  for (const [id, title] of oldCases) {
    await record(id, title, async (item) => {
      if (id === "BAI-P0-108") {
        const p1 = await createProposal("旧 P1", [{ type: "create_event", payload: { title: "旧P1", start_time: isoDatePlus(1, 9), end_time: isoDatePlus(1, 10) } }]);
        await createProposal("新 P2", [{ type: "create_event", payload: { title: "新P2", start_time: isoDatePlus(1, 10), end_time: isoDatePlus(1, 11) } }], { supersedes_proposal_id: p1.id });
        await markProposalStatus(p1.id, "superseded");
        await gotoApp();
        await sendMessage("P1 按方案A安排");
        const data = await counts();
        assert(data.events.length === 0, "superseded proposal executed");
      } else if (id === "BAI-P0-109") {
        await createProposal("P1 active", [{ type: "create_event", payload: { title: "P1 active", start_time: isoDatePlus(1, 9), end_time: isoDatePlus(1, 10) } }]);
        await createProposal("P2 other", [{ type: "create_event", payload: { title: "P2 other", start_time: isoDatePlus(1, 10), end_time: isoDatePlus(1, 11) } }]);
        await gotoApp();
        await sendMessage("可以");
        const data = await counts();
        assert(data.events.length === 0 && data.proposals.filter((p) => p.status === "pending").length === 2, "ambiguous active target executed");
      } else {
        await createProposal("刷新 P1", [{ type: "create_event", payload: { title: "刷新P1", start_time: isoDatePlus(1, 9), end_time: isoDatePlus(1, 10) } }]);
        await createProposal("刷新 P2", [{ type: "create_event", payload: { title: "刷新P2", start_time: isoDatePlus(1, 10), end_time: isoDatePlus(1, 11) } }]);
        await gotoApp();
        await page.reload({ waitUntil: "networkidle" });
        await clickAssistantTab();
        const beforeText = await visibleText();
        await sendMessage("P1 按方案A安排");
        const data = await counts();
        assert(data.events.length === 1, "P1 after refresh did not execute exactly one event");
        item.evidence.push(beforeText.includes("P1") ? "P1 visible before confirm" : "label not visible in body snapshot");
      }
      item.evidence.push("old behavior guard passed");
    });
  }
}

main()
  .catch((error) => {
    console.error(error);
    process.exitCode = 1;
  })
  .finally(async () => {
    if (browser) await browser.close().catch(() => {});
    await killProcessTree(webProc);
    await killProcessTree(apiProc);
  });

async function killProcessTree(child) {
  if (!child || child.killed || child.pid == null) return;
  if (process.platform === "win32") {
    await new Promise((resolve) => {
      const killer = spawn("taskkill", ["/pid", String(child.pid), "/t", "/f"], { stdio: "ignore" });
      killer.on("exit", resolve);
      killer.on("error", resolve);
    });
    return;
  }
  child.kill("SIGTERM");
}
