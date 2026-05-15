# AI Assistant Browser Full Acceptance 20260514200720

- API: http://127.0.0.1:18741/api
- Web: http://127.0.0.1:8894
- DB: E:\GraduationProject\backend\data\browser_full_acceptance_20260514200720.db
- Memory: E:\GraduationProject\backend\data\browser_full_acceptance_memory_20260514200720
- Summary: 0 passed, 1 failed, 0 tracked, 1 total

| ID | Status | Title | Evidence / Error |
|---|---|---|---|
| BAI-P0-001 | FAIL | 明确日程创建必须先提案 | Error: UI did not show proposal wording<br>    at assert (file:///E:/GraduationProject/scripts/assistant_browser_full_acceptance.mjs:319:25)<br>    at file:///E:/GraduationProject/scripts/assistant_browser_full_acceptance.mjs:484:5<br>    at process.processTicksAndRejections (node:internal/process/task_queues:103:5)<br>    at async file:///E:/GraduationProject/scripts/assistant_browser_full_acceptance.mjs:336:7<br>    at async withTimeout (file:///E:/GraduationProject/scripts/assistant_browser_full_acceptance.mjs:351:10)<br>    at async record (file:///E:/GraduationProject/scripts/assistant_browser_full_acceptance.mjs:333:5)<br>    at async runScenarios (file:///E:/GraduationProject/scripts/assistant_browser_full_acceptance.mjs:479:3)<br>    at async main (file:///E:/GraduationProject/scripts/assistant_browser_full_acceptance.mjs:436:3) |
