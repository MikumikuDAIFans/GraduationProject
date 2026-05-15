# AI Assistant Browser Full Acceptance 20260514200313

- API: http://127.0.0.1:18741/api
- Web: http://127.0.0.1:8894
- DB: E:\GraduationProject\backend\data\browser_full_acceptance_20260514200313.db
- Memory: E:\GraduationProject\backend\data\browser_full_acceptance_memory_20260514200313
- Summary: 0 passed, 1 failed, 0 tracked, 1 total

| ID | Status | Title | Evidence / Error |
|---|---|---|---|
| BAI-P0-001 | FAIL | 明确日程创建必须先提案 | locator.click: Timeout 30000ms exceeded.<br>Call log:<br>[2m  - waiting for getByText('助手', { exact: true }).first()[22m<br>[2m    - locator resolved to <button type="button" class="relative flex flex-1 flex-col items-center justify-center gap-0.5 text-[10px] font-semibold transition-colors text-ink-3">…</button>[22m<br>[2m  - attempting click action[22m<br>[2m    2 × waiting for element to be visible, enabled and stable[22m<br>[2m      - element is not visible[22m<br>[2m    - retrying click action[22m<br>[2m    - waiting 20ms[22m<br>[2m    2 × waiting for element to be visible, enabled and stable[22m<br>[2m      - element is not visible[22m<br>[2m    - retrying click action[22m<br>[2m      - waiting 100ms[22m<br>[2m    58 × waiting for element to be visible, enabled and stable[22m<br>[2m       - element is not visible[22m<br>[2m     - retrying click action[22m<br>[2m       - waiting 500ms[22m<br><br>    at clickAssistantTab (E:\GraduationProject\scripts\assistant_browser_full_acceptance.mjs:275:24)<br>    at async gotoApp (E:\GraduationProject\scripts\assistant_browser_full_acceptance.mjs:269:3)<br>    at async file:///E:/GraduationProject/scripts/assistant_browser_full_acceptance.mjs:324:7<br>    at async withTimeout (E:\GraduationProject\scripts\assistant_browser_full_acceptance.mjs:340:10)<br>    at async record (E:\GraduationProject\scripts\assistant_browser_full_acceptance.mjs:322:5)<br>    at async runScenarios (E:\GraduationProject\scripts\assistant_browser_full_acceptance.mjs:468:3)<br>    at async main (E:\GraduationProject\scripts\assistant_browser_full_acceptance.mjs:425:3) |
