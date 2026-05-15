# AI Assistant Browser Full Acceptance 20260514200905

- API: http://127.0.0.1:18741/api
- Web: http://127.0.0.1:8894
- DB: E:\GraduationProject\backend\data\browser_full_acceptance_20260514200905.db
- Memory: E:\GraduationProject\backend\data\browser_full_acceptance_memory_20260514200905
- Summary: 2 passed, 1 failed, 0 tracked, 3 total

| ID | Status | Title | Evidence / Error |
|---|---|---|---|
| BAI-P0-001 | PASS | 明确日程创建必须先提案 | pending proposals=1 |
| BAI-P0-002 | FAIL | 单 proposal 自然语言确认执行 | Error: confirmed event not created<br>    at assert (file:///E:/GraduationProject/scripts/assistant_browser_full_acceptance.mjs:359:25)<br>    at file:///E:/GraduationProject/scripts/assistant_browser_full_acceptance.mjs:533:5<br>    at process.processTicksAndRejections (node:internal/process/task_queues:103:5)<br>    at async file:///E:/GraduationProject/scripts/assistant_browser_full_acceptance.mjs:376:7<br>    at async withTimeout (file:///E:/GraduationProject/scripts/assistant_browser_full_acceptance.mjs:391:10)<br>    at async record (file:///E:/GraduationProject/scripts/assistant_browser_full_acceptance.mjs:373:5)<br>    at async runScenarios (file:///E:/GraduationProject/scripts/assistant_browser_full_acceptance.mjs:529:3)<br>    at async main (file:///E:/GraduationProject/scripts/assistant_browser_full_acceptance.mjs:476:3) |
| BAI-P0-003 | PASS | 重复确认幂等 | repeat confirm kept one event |
