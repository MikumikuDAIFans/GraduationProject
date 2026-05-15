# AI Assistant Intelligence P0 Browser Acceptance - 2026-05-15

## Environment

- Branch: `codex/assistant-browser-acceptance`
- Commit at run start: `31ad8e6`
- Date: `2026-05-15 20:43:13 +08:00`
- Backend ports used: `8019`, `8020`, `8021`
- Frontend ports used: `8897`, `8898`, `8899`
- SQLite DBs:
  - `backend/data/browser_int_p0_007_20260515.db`
  - `backend/data/browser_int_p0_008_20260515.db`
  - `backend/data/browser_int_p0_010_20260515.db`

## Results

### INT-P0-007 Targeted Reschedule Matching

Status: passed.

Browser sequence:

1. `请帮我安排处理真实逐条日程10，时间是5月18号上午10点到11点，地点测试地点10`
2. Click confirm, which sent `确认 P1 方案A`.
3. `请帮我安排真实逐条日程52，时间是6月20号上午10点到11点，地点测试地点52`
4. Click confirm, which sent `确认 P2 方案A`.
5. `把真实逐条日程10改到6月20号16:00到17:00，地点改到最终测试地点A`

Evidence:

- Browser displayed pending `P3`: `建议把日程“处理真实逐条日程10”改到 06-20 16:00-17:00，地点：最终测试地点A`.
- SQLite:
  - Event `1`: `处理真实逐条日程10`, original time still `2026-05-18 10:00-11:00`.
  - Event `2`: `真实逐条日程52`, `2026-06-20 10:00-11:00`.
  - Proposal `3`: `pending`, `event_reschedule`, `related_event_id=1`.

### INT-P0-008 Multiple Pending Confirmation Must Clarify

Status: passed.

Browser sequence:

1. `明天下午3点去图书馆自习`
2. `后天晚上8点复习英语`
3. `可以`

Evidence:

- Browser displayed two pending proposals:
  - `P1`: `去图书馆自习`, `05-16 15:00-16:00`, location `图书馆`.
  - `P2`: `复习英语`, `05-17 20:00-21:00`.
- Assistant replied: `我不确定你指的是哪个待确认方案。请直接说“按 P1”或“把 P2 改到明天上午”。`
- SQLite:
  - `events=0`.
  - Proposals `1` and `2` both remained `pending`.

Fix added during this run:

- `后天晚上8点复习英语` no longer inherits the previous `图书馆自习` title/location.
- Added regression: `test_conductor_does_not_merge_independent_timed_study_with_previous_library_request`.

### INT-P0-009 Departure-To-School Event Creation

Status: passed.

Browser input:

- `5月21号下午1点出发去学校`

Evidence:

- Browser displayed pending `P3`: `建议创建日程“去学校”：05-21 13:00-14:00，地点：学校`.
- Assistant stated default 1 hour and that it would not write before confirmation.
- SQLite:
  - `events=0`.
  - Proposal `3`: `pending`, `event_creation`.
  - Payload action: `title=去学校`, `start_time=2026-05-21T13:00:00`, `end_time=2026-05-21T14:00:00`, `location_name=学校`.

### INT-P0-010 Real Sequential 55 Event Pressure Test

Status: passed.

Tool:

- `scripts/browser_real55_acceptance.js`
- Environment:
  - `ACCEPTANCE_DB_PATH=E:/GraduationProject/backend/data/browser_int_p0_010_20260515.db`
  - `ACCEPTANCE_FRONTEND_URL=http://127.0.0.1:8899`
  - `ACCEPTANCE_TARGET_COUNT=55`

Browser behavior:

- 55 natural-language event creation requests were sent one by one through the real frontend.
- Each creation produced a pending proposal and was confirmed by sending `确认 Pn 方案A` through the assistant.
- 5 natural-language reschedules were then sent and confirmed through proposals:
  - `真实逐条日程10` -> `2026-06-20 16:00-17:00`, `最终测试地点A`
  - `真实逐条日程21` -> `2026-06-21 09:00-10:00`, `最终测试地点B`
  - `真实逐条日程32` -> `2026-06-22 14:00-15:00`, `最终测试地点C`
  - `真实逐条日程43` -> `2026-06-23 19:00-20:00`, `最终测试地点D`
  - `真实逐条日程52` -> `2026-06-24 17:00-18:00`, `最终测试地点E`

SQLite final evidence:

```text
events = 55
event range = 2026-05-21 08:00:00.000000 to 2026-06-24 17:00:00.000000
assistant_proposals by status = executed: 60
pending/execution_failed proposals = 0
```

Modified event evidence:

```text
10|真实逐条日程10|2026-06-20 16:00:00.000000|2026-06-20 17:00:00.000000|最终测试地点A
21|真实逐条日程21|2026-06-21 09:00:00.000000|2026-06-21 10:00:00.000000|最终测试地点B
32|真实逐条日程32|2026-06-22 14:00:00.000000|2026-06-22 15:00:00.000000|最终测试地点C
43|真实逐条日程43|2026-06-23 19:00:00.000000|2026-06-23 20:00:00.000000|最终测试地点D
52|真实逐条日程52|2026-06-24 17:00:00.000000|2026-06-24 18:00:00.000000|最终测试地点E
```

## Automated Regression

Backend:

```powershell
cd E:\GraduationProject\backend
.\.venv312\Scripts\python.exe -m pytest tests/test_assistant_conductor.py tests/test_assistant_text_protocol.py tests/test_assistant_proposal_revise.py tests/test_assistant_service.py tests/test_assistant_memory_capture.py tests/test_llm_client.py -q
```

Result:

```text
200 passed in 60.26s
```

Frontend:

```powershell
cd E:\GraduationProject\frontend
npm run build
```

Result: passed.

## Notes

- User-visible proposal buttons send assistant messages such as `确认 P1 方案A` and `P1 先不要安排`; they do not bind direct proposal confirm/reject API calls in `AssistantPanel`.
- Pending proposal cards and memory candidate cards are hidden locally immediately after their button prompt is submitted to prevent repeat clicks.
- LLM message understanding now has Pydantic schema validation; invalid or low-confidence LLM understanding falls back to deterministic understanding instead of entering business decisions.
