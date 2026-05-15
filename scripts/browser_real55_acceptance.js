const { chromium } = require('playwright');
const { execFileSync } = require('child_process');

const DB_PATH = process.env.ACCEPTANCE_DB_PATH || 'E:/GraduationProject/backend/data/browser_prod_real55_20260515_v3.db';
const PYTHON = process.env.ACCEPTANCE_PYTHON || 'E:/GraduationProject/backend/.venv312/Scripts/python.exe';
const FRONTEND_URL = process.env.ACCEPTANCE_FRONTEND_URL || 'http://127.0.0.1:8890';
const TARGET_COUNT = Number(process.env.ACCEPTANCE_TARGET_COUNT || 55);

function query(sql, params = []) {
  const script = `
import json, sqlite3, sys
db_path = ${JSON.stringify(DB_PATH)}
sql = ${JSON.stringify(sql)}
params = json.loads(${JSON.stringify(JSON.stringify(params))})
con = sqlite3.connect(db_path)
con.row_factory = sqlite3.Row
rows = [dict(row) for row in con.execute(sql, params).fetchall()]
con.close()
print(json.dumps(rows, ensure_ascii=False))
`;
  let lastError;
  for (let attempt = 0; attempt < 5; attempt += 1) {
    try {
      const output = execFileSync(PYTHON, ['-c', script], { encoding: 'utf8' });
      return Promise.resolve(JSON.parse(output));
    } catch (error) {
      lastError = error;
      execFileSync(PYTHON, ['-c', `import time; time.sleep(${0.2 + attempt * 0.2})`]);
    }
  }
  throw lastError;
}

function pad(n) {
  return String(n).padStart(2, '0');
}

function makeRequest(i) {
  const d = i <= 31 ? new Date(2026, 4, 20 + i) : new Date(2026, 5, i - 31);
  const m = d.getMonth() + 1;
  const day = d.getDate();
  const slot = (i - 1) % 8;
  const hour = 8 + slot;
  const next = hour + 1;
  const title = `真实逐条日程${pad(i)}`;
  const loc = `真实地点${((i - 1) % 7) + 1}`;
  const patterns = [
    `${m}月${day}号 ${pad(hour)}:00-${pad(next)}:00 在${loc}处理${title}`,
    `${m}月${day}日 ${pad(hour)}:00到${pad(next)}:00 去${loc}参加${title}`,
    `请帮我安排${title}，时间是${m}月${day}号 ${pad(hour)}:00-${pad(next)}:00，地点${loc}`,
    `${m}/${day} ${pad(hour)}:00到${pad(next)}:00 在${loc}开${title}`,
    `${m}月${day}号 ${pad(hour)}:00-${pad(next)}:00 去${loc}做${title}`,
  ];
  return patterns[i % patterns.length];
}

async function pendingLabel() {
  const rows = await query(
    "select id, payload_json from assistant_proposals where status='pending' order by id desc limit 1",
  );
  if (!rows.length) return null;
  const payload = JSON.parse(rows[0].payload_json || '{}');
  return { id: rows[0].id, label: payload.protocol_label || null };
}

async function eventCount() {
  const rows = await query('select count(*) as count from events');
  return rows[0].count;
}

async function eventByTitleFragment(fragment) {
  const rows = await query(
    "select id, title, start_time, end_time, location_name from events where title like ? order by id limit 1",
    [`%${fragment}%`],
  );
  return rows[0] || null;
}

async function proposalStatusCounts() {
  return query("select status, count(*) as count from assistant_proposals group by status order by status");
}

async function send(page, text) {
  const input = page.getByRole('textbox', { name: '输入你想安排的事情、任务或问题…' });
  await input.fill(text);
  await page.waitForFunction(() => {
    return [...document.querySelectorAll('button')].some(
      (button) => button.textContent?.trim() === '发送' && !button.disabled,
    );
  }, { timeout: 30000 });
  await page.getByRole('button', { name: '发送' }).click();
}

async function waitForPendingAfter(previousMaxProposalId) {
  const deadline = Date.now() + 90000;
  let latestSeen = null;
  while (Date.now() < deadline) {
    const latest = await pendingLabel();
    latestSeen = latest || latestSeen;
    if (latest && latest.id > previousMaxProposalId && latest.label) {
      return latest.label;
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`Timed out waiting for pending proposal after id ${previousMaxProposalId}; latest=${JSON.stringify(latestSeen)}`);
}

async function waitForEventCountAtLeast(count) {
  const deadline = Date.now() + 45000;
  while (Date.now() < deadline) {
    if ((await eventCount()) >= count) return;
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`Timed out waiting for event count >= ${count}; current=${await eventCount()}`);
}

async function waitForEventUpdate(fragment, predicate) {
  const deadline = Date.now() + 45000;
  while (Date.now() < deadline) {
    const event = await eventByTitleFragment(fragment);
    if (event && predicate(event)) return event;
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  const event = await eventByTitleFragment(fragment);
  throw new Error(`Timed out waiting for update on ${fragment}; current=${JSON.stringify(event)}`);
}

const modifications = [
  {
    fragment: '真实逐条日程10',
    message: '把真实逐条日程10改到6月20号16:00到17:00，地点改到最终测试地点A',
    expectedStart: '2026-06-20 16:00:00.000000',
    expectedEnd: '2026-06-20 17:00:00.000000',
    expectedLocation: '最终测试地点A',
  },
  {
    fragment: '真实逐条日程21',
    message: '把真实逐条日程21改到6月21号早上9点到10点，地点改到最终测试地点B',
    expectedStart: '2026-06-21 09:00:00.000000',
    expectedEnd: '2026-06-21 10:00:00.000000',
    expectedLocation: '最终测试地点B',
  },
  {
    fragment: '真实逐条日程32',
    message: '把真实逐条日程32改到6月22号下午2点到3点，地点改到最终测试地点C',
    expectedStart: '2026-06-22 14:00:00.000000',
    expectedEnd: '2026-06-22 15:00:00.000000',
    expectedLocation: '最终测试地点C',
  },
  {
    fragment: '真实逐条日程43',
    message: '把真实逐条日程43改到6月23号晚上7点到8点，地点改到最终测试地点D',
    expectedStart: '2026-06-23 19:00:00.000000',
    expectedEnd: '2026-06-23 20:00:00.000000',
    expectedLocation: '最终测试地点D',
  },
  {
    fragment: '真实逐条日程52',
    message: '把真实逐条日程52改到6月24号17:00到18:00，地点改到最终测试地点E',
    expectedStart: '2026-06-24 17:00:00.000000',
    expectedEnd: '2026-06-24 18:00:00.000000',
    expectedLocation: '最终测试地点E',
  },
];

async function main() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  const failures = [];
  page.on('console', (message) => {
    if (message.type() === 'error') failures.push({ type: 'console', text: message.text() });
  });
  page.on('pageerror', (error) => failures.push({ type: 'pageerror', message: error.message }));
  page.on('requestfailed', (request) => failures.push({ type: 'requestfailed', url: request.url(), failure: request.failure()?.errorText }));
  page.on('response', (response) => {
    if (response.status() >= 400) failures.push({ type: 'http', url: response.url(), status: response.status() });
  });

  await page.goto(FRONTEND_URL);
  const existingPending = await pendingLabel();
  if (existingPending?.label) {
    const expectedNextCount = (await eventCount()) + 1;
    await send(page, `确认 ${existingPending.label} 方案A`);
    await waitForEventCountAtLeast(expectedNextCount);
    console.log(`confirmed existing pending via ${existingPending.label}`);
  }

  const startCount = await eventCount();
  for (let i = startCount + 1; i <= TARGET_COUNT; i++) {
    const beforeProposalRows = await query('select coalesce(max(id), 0) as id from assistant_proposals');
    await send(page, makeRequest(i));
    const label = await waitForPendingAfter(beforeProposalRows[0].id);
    await send(page, `确认 ${label} 方案A`);
    await waitForEventCountAtLeast(i);
    console.log(`confirmed ${i} via ${label}`);
  }

  if (TARGET_COUNT >= 55) {
    for (const change of modifications) {
      const existing = await eventByTitleFragment(change.fragment);
      if (existing?.start_time === change.expectedStart && existing?.end_time === change.expectedEnd) {
        console.log(`already updated ${change.fragment}: ${existing.start_time}-${existing.end_time} ${existing.location_name}`);
        continue;
      }
      const beforeProposalRows = await query('select coalesce(max(id), 0) as id from assistant_proposals');
      await send(page, change.message);
      const label = await waitForPendingAfter(beforeProposalRows[0].id);
      await send(page, `确认 ${label} 方案A`);
      const updated = await waitForEventUpdate(change.fragment, (event) => (
        event.start_time === change.expectedStart
        && event.end_time === change.expectedEnd
      ));
      console.log(`updated ${change.fragment} via ${label}: ${updated.start_time}-${updated.end_time} ${updated.location_name}`);
    }
  }

  const summary = {
    events: await eventCount(),
    proposalStatusCounts: await proposalStatusCounts(),
    range: await query('select min(start_time) as min_start, max(start_time) as max_start from events'),
    modified: await Promise.all(modifications.map((item) => eventByTitleFragment(item.fragment))),
  };
  console.log(JSON.stringify(summary, null, 2));

  await browser.close();
  if (failures.length) {
    console.error(JSON.stringify(failures, null, 2));
    process.exit(2);
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
