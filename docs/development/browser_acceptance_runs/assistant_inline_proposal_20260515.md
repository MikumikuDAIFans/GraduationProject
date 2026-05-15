# AI Assistant Inline Proposal Browser Acceptance - 2026-05-15

## Environment

- Branch: `codex/assistant-browser-acceptance`
- Date: `2026-05-15 22:23 +08:00`
- Backend: `http://127.0.0.1:8014`
- Frontend: `http://127.0.0.1:8890`
- SQLite DB: `E:\GraduationProject\backend\data\browser_inline_20260515.db`
- Browser: Chromium via Playwright MCP

## Fix Under Test

- File changed: `frontend/src/components/AssistantPanel.vue`
- Problem: after clicking an inline proposal option or reject-all button, the inline card remained visible and still looked actionable.
- Fix: after submitting an inline proposal prompt, the current frontend session hides the corresponding inline proposal block by `proposal_id`.

Superseded note:

- The 2026-05-16 product decision changed the desired behavior. Inline proposal cards should no longer disappear after accept/reject. They should remain in the original assistant bubble, become grey, show the terminal status, and be disabled.
- Historical sections below that mention a card disappearing describe the earlier acceptance target. The current target and latest verification are recorded in `2026-05-16 Inline Card Terminal-State Retention`.

## Results

### INLINE-P0-001 Single Option Accept Hides Inline Card

Status: passed.

Browser sequence:

1. Created a new assistant session.
2. Sent `后天下午2点到3点去学校开会`.
3. Browser displayed inline `AI 方案` card inside the assistant message bubble.
4. Clicked the inline option card `A. 按建议创建日程`.

Evidence:

- User protocol message appeared in chat: `接受 P1 方案A`.
- Assistant replied: `已按这个方案确认并执行。`
- The inline proposal card disappeared from the current chat view immediately after clicking.
- Frontend build passed after the fix.

SQLite evidence:

```text
events = 2
proposal id 3 status = executed
proposal id 3 selected_option_id = A
latest user protocol message includes 接受 P1 方案A
```

### INLINE-P0-004 Fuzzy Time Auto-Arrange

Status: failed, fixed, retested passed.

Initial failure:

- Browser input: `下午我想去图书馆`
- Actual before fix: generated a single option at `05-15 15:00-16:00`.
- Expected: broad afternoon request should produce multiple time options.

Fix:

- `backend/app/assistant_agents/specialists/understanding.py`
  - Added `broad_time_period` slot detection for messages such as `下午我想去图书馆`.
- `backend/app/assistant_agents/specialists/planning.py`
  - Added broad-period event option generation.
  - For `afternoon`, generated A/B/C time options: `14:00`, `15:30`, `17:00`.
- `backend/tests/test_assistant_conductor.py`
  - Added `test_conductor_broad_afternoon_destination_event_proposes_time_options`.

Retest sequence:

1. Restarted backend `8014` against `browser_inline_20260515.db`.
2. Created a new assistant session.
3. Sent `下午我想去图书馆`.
4. Browser displayed inline options:
   - A: `下午早些时候`, `05-15 14:00-15:00`
   - B: `下午中段`, `05-15 15:30-16:30`
   - C: `下午晚些时候`, `05-15 17:00-18:00`
5. Clicked option B.

SQLite evidence:

```text
proposal id 7 status = executed
proposal id 7 selected_option_id = B
created event = 去图书馆, 2026-05-15 15:30:00 - 16:30:00, location 图书馆
assistant_messages contains user message 接受 P1 方案B
```

### INLINE-P0-005 Task Split Three Options

Status: failed, fixed, retested passed.

Initial failure:

- Browser input: `这周帮我安排复习英语`
- Actual before fix: generated a single `task_creation` option only:
  - `P1：建议先创建任务“这周帮我安排复习”，进入待排程/待跟进状态`
  - Option A only: `创建任务并等待后续排程`
- Expected: task arrangement should produce at least three meaningfully different options, and accepting one option should create the task plus the selected schedule slices.

Fix:

- `backend/app/services/assistant_runtime_text.py`
  - Improved task content extraction for schedule-style study tasks so `这周帮我安排复习英语` resolves to `复习英语`.
- `backend/app/assistant_agents/specialists/understanding.py`
  - Added `schedule_window` and `wants_schedule_options` slots for new task arrangement requests.
- `backend/app/assistant_agents/specialists/planning.py`
  - Added three executable task split options for new task arrangement requests.
  - Each option uses `create_task_with_events`, so confirmation atomically creates the task and its selected focus blocks.
- `backend/tests/test_assistant_conductor.py`
  - Added `test_conductor_task_arrangement_request_proposes_three_split_options`.

Validation:

```powershell
cd E:\GraduationProject\backend
.\.venv312\Scripts\python.exe -m pytest tests/test_assistant_conductor.py::test_conductor_task_arrangement_request_proposes_three_split_options tests/test_assistant_conductor.py::test_conductor_proposes_clear_task_with_orchestration_reply tests/test_assistant_conductor.py::test_conductor_builds_task_schedule_plan_for_task_continuation_request -q
```

Result:

```text
3 passed
```

Retest sequence:

1. Restarted backend `8014` against `browser_inline_20260515.db`.
2. Created a new assistant session.
3. Sent `这周帮我安排复习英语`.
4. Browser displayed inline options inside the assistant message bubble:
   - A: `分散稳步推进`, 3 focus blocks.
   - B: `集中两段完成`, 2 focus blocks.
   - C: `前轻后重冲刺`, 3 focus blocks.
5. Clicked option B.

Browser evidence:

- User protocol message appeared in chat: `接受 P1 方案B`.
- Assistant replied: `已按这个方案确认并执行。`
- The inline proposal card disappeared after clicking option B.
- Workspace counters changed from `5 日历 / 0 任务` to `7 日历 / 1 任务`.
- Task panel showed `复习英语`, `已安排`, `240 min scheduled`.
- Screenshot captured: `inline-p0-005-task-split-passed.png`.

SQLite evidence:

```text
proposal id 9 status = executed
proposal id 9 selected_option_id = B
proposal id 9 option_count = 3
created task id 1 = 复习英语, status scheduled, estimated_duration_minutes 240, can_split 1
created event id 6 = 复习英语（第1/2段）, 2026-05-15 14:00:00 - 16:00:00, linked_task_id 1, event_type focus_block
created event id 7 = 复习英语（第2/2段）, 2026-05-17 14:00:00 - 16:00:00, linked_task_id 1, event_type focus_block
```

### INLINE-P0-002 Reject-All Hides Inline Card And Does Not Write Event

Status: passed.

Browser sequence:

1. Created a new assistant session.
2. Sent `5月22号下午4点到5点去图书馆自习`.
3. Browser displayed inline `AI 方案` card inside the assistant message bubble.
4. Clicked `拒绝全部方案`.

Evidence:

- User protocol message appeared in chat: `拒绝 P1 全部方案`.
- Assistant replied: `已暂不安排这个方案，没有执行任何写入。`
- The inline proposal card disappeared from the current chat view immediately after clicking.

SQLite evidence:

```text
events = 2
proposal id 4 status = rejected
proposal id 4 selected_option_id = null
assistant_messages contains user message 拒绝 P1 全部方案
assistant_messages contains assistant render_blocks_json for the original inline proposal
```

### INLINE-P0-003 Multi-Option Single-Select Locking

Status: passed.

Browser sequence:

1. Switched back to the session containing a pending conflict proposal.
2. Browser displayed inline proposal `P2` with option A, option B, and `拒绝全部方案`.
3. Clicked option B: `维持原时间并提示处理冲突`.

Evidence:

- User protocol message appeared in chat: `接受 P2 方案B`.
- Assistant replied: `已按这个方案确认并执行。`
- The inline proposal card disappeared from the current chat view immediately after clicking option B.
- Because the whole inline block was hidden after submission, option A and reject-all were no longer clickable in the current view.

SQLite evidence:

```text
proposal id 2 status = executed
proposal id 2 selected_option_id = B
events = 3
latest user protocol message includes 接受 P2 方案B
```

### INLINE-P0-006 Conflict Multi-Option Proposal

Status: passed.

Browser evidence:

- Conflict proposal `P2` displayed more than one option:
  - A: `后移新日程以避开当前时段`
  - B: `维持原时间并提示处理冲突`
- The assistant text explicitly stated the conflict with the existing `去学校开会` event.
- Clicking option B executed only option B and recorded `selected_option_id = B`.

### INLINE-P0-007 Refresh Recovery For Pending Inline Proposal

Status: passed.

Browser sequence:

1. Created a new assistant session.
2. Sent `5月23号上午9点到10点去学校办手续`.
3. Browser displayed a pending inline `AI 方案` card.
4. Refreshed `http://127.0.0.1:8890/`.
5. The same historical assistant message still rendered the inline card.
6. Clicked option A after the refresh.

Evidence:

- The refreshed card was visible and clickable.
- User protocol message appeared in chat: `接受 P1 方案A`.
- Assistant replied: `已按这个方案确认并执行。`
- The inline card disappeared from the current chat view after clicking.

SQLite evidence:

```text
proposal id 5 status = executed
proposal id 5 selected_option_id = A
events = 4
latest user protocol message includes 接受 P1 方案A
```

## Validation Commands

Frontend:

```powershell
cd E:\GraduationProject\frontend
npm run build
```

Result:

```text
passed
```

## Remaining Inline Proposal Gaps

- `INLINE-P0-003`, `INLINE-P0-004`, `INLINE-P0-005`, `INLINE-P0-006`, and `INLINE-P0-007` passed in the current browser run, but should be repeated in a fresh clean DB before final sign-off.
- Final full-function browser acceptance must run after all P0/P1 inline proposal cases pass.

## Fresh Clean DB P0 Rerun

Status: passed for `INLINE-P0-001` through `INLINE-P0-008`.

Environment:

- Backend: `http://127.0.0.1:8014`
- Frontend: `http://127.0.0.1:8890`
- SQLite DB: `E:\GraduationProject\backend\data\browser_inline_clean_20260515.db`
- Browser: Chromium via Playwright MCP

Setup note:

- A fresh SQLite file needed explicit table initialization before browser testing. The first attempt failed with `no such table: user_profile`; after initializing `Base.metadata` with `app.models` imported, the clean DB had empty tables and the browser rerun restarted.

Browser results:

| Case | Status | Browser Evidence |
|---|---|---|
| `INLINE-P0-001` | passed | `明天下午3点到4点去学校开会` rendered option A; click generated `接受 P1 方案A`; assistant replied `已按这个方案确认并执行。` |
| `INLINE-P0-002` | passed | `5月22号下午4点到5点去图书馆自习` rendered option A; click `拒绝全部方案` generated `拒绝 P1 全部方案`; assistant replied no-write rejection text. |
| `INLINE-P0-003` | passed | `下午我想去图书馆` rendered A/B/C; after clicking B, no A/B/C option buttons remained visible in the current message. |
| `INLINE-P0-004` | passed | `下午我想去图书馆` rendered three time options; B executed as `15:30-16:30`. |
| `INLINE-P0-005` | passed | `这周帮我安排复习英语` rendered A/B/C split options; B executed and created task plus two focus blocks. |
| `INLINE-P0-006` | passed | Existing `05-16 15:00-16:00 去学校开会` remained; same-time `去学校讨论项目` rendered conflict A/B options; clicking B selected only B. |
| `INLINE-P0-007` | passed | Pending `5月23号上午9点到10点去学校办手续` survived page reload; option A remained clickable after refresh and executed. |
| `INLINE-P0-008` | passed | Network capture did not show direct `/api/assistant/proposals/.../confirm` or `/reject`; clicks produced user protocol messages in chat. |

SQLite evidence after clean rerun:

```text
assistant_sessions = 7
assistant_messages = 24
assistant_proposals = 6
events = 6
tasks = 1

proposal 1: event_creation executed, selected A, related_event_id 1
proposal 2: event_creation rejected, selected null, related_event_id null
proposal 3: event_creation executed, selected B, option_count 3, related_event_id 2
proposal 4: task_creation executed, selected B, option_count 3, related_task_id 1, related_event_id 3
proposal 5: event_creation executed, selected B, option_count 2, related_event_id 5
proposal 6: event_creation executed, selected A, related_event_id 6

created task: 复习英语, status scheduled, estimated_duration_minutes 240, can_split 1, linked_event_id 3

protocol messages:
接受 P1 方案A
拒绝 P1 全部方案
接受 P1 方案B
接受 P1 方案B
接受 P1 方案B
接受 P1 方案A
```

Network evidence:

```text
inline-p0-clean-network-all.md contains no direct confirm/reject proposal endpoint requests.
Visible click outcomes were submitted as assistant chat protocol messages.
```

Remaining after clean P0 rerun:

- Run `INLINE-P1-001` through `INLINE-P1-005`.
- After P1 passes, run the separate final full-function browser acceptance on another clean DB.

## P1 Browser Acceptance

### INLINE-P1-001 Multi-Target Compound Request

Status: failed, fixed, retested passed.

Initial failure:

- Browser input: `明天下午3点去学校开会，晚上8点提醒我复习英语`
- Actual before fix: only one pending proposal was generated for `去学校开会`; the second target `晚上8点提醒我复习英语` was silently dropped.
- Expected: compound request must not silently drop any target; each target should be separately accept/reject-able.

Fix:

- `backend/app/services/assistant.py`
  - Added deterministic compound-event proposal handling before single timed-reminder/event short-circuits.
  - Split compound messages by punctuation/connectors, inherited leading date context, and generated one pending proposal per recognized target.
  - Queued one inline `proposal_options` render block per generated proposal.
- `backend/tests/test_assistant_service.py`
  - Added `test_deterministic_compound_event_request_creates_separate_inline_proposals`.

Validation:

```powershell
cd E:\GraduationProject\backend
.\.venv312\Scripts\python.exe -m pytest tests/test_assistant_service.py::test_deterministic_compound_event_request_creates_separate_inline_proposals -q
```

Result:

```text
1 passed
```

Retest sequence:

1. Restarted backend `8014` against `browser_inline_clean_20260515.db`.
2. Created a new assistant session.
3. Sent `明天下午3点去学校开会，晚上8点提醒我复习英语`.
4. Browser rendered two inline proposal blocks in the assistant message:
   - `P1`: `去学校开会`, conflict-aware A/B options.
   - `P2`: `复习英语`, option A at `05-16 19:00-20:00`.
5. Clicked `拒绝全部方案` on P1.
6. Browser generated user protocol message `拒绝 P1 全部方案`; P1 card disappeared while P2 stayed visible.
7. Clicked P2 option A.
8. Browser generated user protocol message `接受 P2 方案A` and assistant replied `已按这个方案确认并执行。`

SQLite evidence:

```text
proposal id 8 status = rejected, protocol_label = P1, source = deterministic_compound_event
proposal id 9 status = executed, protocol_label = P2, selected_option_id = A, source = deterministic_compound_event
created event id 7 = 复习英语, 2026-05-16 19:00:00 - 20:00:00
assistant_messages contains 拒绝 P1 全部方案
assistant_messages contains 接受 P2 方案A
```

Remaining P1:

- `INLINE-P1-005` 移动端渲染。

### INLINE-P1-002 Revise A Proposal

Status: failed, fixed, retested passed.

Initial failure:

- Browser setup: generated a pending proposal, then sent `把方案B改成晚上8点` from the main input.
- Actual before fix: backend created a revised pending proposal in SQLite, but the assistant reply only said `我已根据你的修改生成新的待确认方案，旧方案不会再执行。`; the new revised proposal card was not rendered inline in the chat.
- Expected: the revised pending proposal must appear as an inline card in the assistant reply, so the user can accept/reject it without leaving the conversation flow.

Fix:

- `backend/app/services/assistant.py`
  - In proposal text protocol `revise` branch, queue the revised proposal as an inline `proposal_options` render block.
- `backend/tests/test_assistant_text_protocol.py`
  - Extended `test_proposal_revision_can_target_visible_global_pending_proposal` to assert a render block is queued for the revised proposal.

Validation:

```powershell
cd E:\GraduationProject\backend
.\.venv312\Scripts\python.exe -m pytest tests/test_assistant_text_protocol.py::test_proposal_revision_can_target_visible_global_pending_proposal tests/test_assistant_proposal_revise.py::test_revise_event_creation_inherits_afternoon_context_for_bare_hour -q
```

Result:

```text
2 passed
```

Retest sequence:

1. Restarted backend `8014` against `browser_inline_clean_20260515.db`.
2. Created a new assistant session.
3. Sent `后天下午去图书馆`.
4. Browser rendered pending inline A/B proposal.
5. Sent `把方案B改成晚上8点` from the main input.
6. Browser displayed assistant reply `我已根据你的修改生成新的待确认方案，旧方案不会再执行。`
7. Browser rendered a new inline proposal card in that reply with revised time `05-17 20:00-21:00`.

SQLite evidence:

```text
proposal id 12 status = superseded, protocol_label = P1
proposal id 13 status = pending, protocol_label = P1
proposal id 13 revision = event_payload_update, 2026-05-17T20:00:00 - 21:00:00
```

Ambiguous multi-pending retest:

1. Created another session with compound input `明天下午3点去学校开会，晚上8点提醒我复习英语`.
2. Browser rendered P1 and P2 pending proposals.
3. Sent `把方案B改成晚上8点`.
4. Assistant replied: `我不确定你指的是哪个待确认方案。请直接说“按 P1”或“把 P2 改到明天上午”。`

Result: passed; multi-pending ambiguous revision did not silently choose a target.

### INLINE-P1-003 Change Mind / Reject By Natural Phrase

Status: failed, fixed, retested passed.

Initial failure:

- Browser setup: one pending proposal for `5月24号下午2点到3点去图书馆看书`.
- User input from main box: `算了，不选了`
- Actual before fix: assistant treated it as an event-cancel intent and asked for the concrete event to cancel.
- Expected: with a single pending proposal, this phrase should reject the pending proposal and not write any event.

Fix:

- `backend/app/services/assistant.py`
  - Added `算了，不选了` and `不选了` to proposal rejection protocol detection.
- `backend/tests/test_assistant_text_protocol.py`
  - Added rejection protocol assertions for these phrases.

Validation:

```powershell
cd E:\GraduationProject\backend
.\.venv312\Scripts\python.exe -m pytest tests/test_assistant_text_protocol.py::test_proposal_rejection_protocol_phrases -q
```

Result:

```text
1 passed
```

Retest sequence:

1. Restarted backend `8014` against `browser_inline_clean_20260515.db`.
2. Returned to the single-pending proposal session for `5月24号下午2点到3点去图书馆看书`.
3. Sent `算了，不选了` from the main input.
4. Assistant replied `已暂不安排这个方案，没有执行任何写入。`

SQLite evidence:

```text
proposal id 16 status = rejected, protocol_label = P1
assistant_messages contains user content 算了，不选了
```

Multi-pending check:

- In a session with P1 and P2 pending proposals, the same input `算了，不选了` did not auto-reject one proposal; assistant asked the user to clarify which pending proposal to operate on.

### INLINE-P1-004 Execution Failed Retry

Status: passed.

Browser setup:

- Created a fresh assistant session in `browser_inline_clean_20260515.db`.
- Seeded one `execution_failed` proposal for that session:
  - `protocol_label = P1`
  - `selected_option_id = A`
  - payload action: valid `create_event` for `重试测试`, `2026-05-25 10:00-11:00`
  - `execution_error = seeded failure for browser retry`

Browser sequence:

1. Refreshed the frontend so the session and failed proposal context were current.
2. Sent `重试 P1` from the main assistant input.
3. Assistant replied `已通过助手消息重试这个方案。`
4. Calendar list showed new event `重试测试`.

Validation:

```powershell
cd E:\GraduationProject\backend
.\.venv312\Scripts\python.exe -m pytest tests/test_assistant_text_protocol.py::test_proposal_retry_text_protocol_targets_failed_proposal tests/test_assistant_proposal_manager.py::test_execution_failure_is_recorded_and_retry_executes_again -q
```

Result:

```text
2 passed
```

SQLite evidence:

```text
proposal id 17 status = executed
proposal id 17 selected_option_id = A
proposal id 17 related_event_id = 8
proposal id 17 execution.retry_count = 1
created event id 8 = 重试测试, 2026-05-25 10:00:00 - 11:00:00
assistant_messages contains user content 重试 P1
assistant_messages contains assistant content 已通过助手消息重试这个方案。
```

### INLINE-P1-005 Mobile Rendering

Status: failed once, fixed, retested passed.

Initial mobile failure:

- Browser viewport: `390x844`.
- Actual before fix: the assistant session selector used a `1fr auto` grid track; the select kept its intrinsic width and pushed the `新对话` button outside the viewport.
- Expected: session controls and inline proposal cards must stay inside the mobile viewport and remain clickable.

Fix:

- `frontend/src/components/AssistantPanel.vue`
  - Changed the session control grid to `grid-cols-[minmax(0,1fr)_auto]`.
  - Added `min-w-0 w-full` to the session select and `shrink-0` to the new chat button.
  - Strengthened message auto-scroll with `nextTick` and post-flush watchers so long inline proposal replies settle near the actionable card area after refresh/tab switch.
  - Reset local inline proposal submission locks when switching sessions.

Validation:

```powershell
cd E:\GraduationProject\frontend
npm run build
```

Result:

```text
passed
```

Retest sequence:

1. Set viewport to `390x844`, opened the mobile bottom tab `助手`.
2. Confirmed the session select stayed within the viewport and `新对话` was visible at `x=308..374`.
3. Created a new session and sent `5月26号上午10点到11点去学校开会`.
4. Browser rendered one inline option card in the assistant bubble; visible overflow scan returned `[]`.
5. Clicked option A.
6. Browser generated user protocol message `接受 P1 方案A`, hid the inline card, and assistant replied `已按这个方案确认并执行。`
7. Created another session and sent `这周帮我安排复习数学`.
8. Browser rendered A/B/C task split cards plus `拒绝全部方案` in a vertical mobile layout.
9. Refreshed, returned to the mobile assistant tab, and confirmed the message area scrolled to the actionable inline cards instead of staying at the top.
10. Clicked option B.
11. Browser generated user protocol message `接受 P1 方案B`, hid the inline card, and assistant replied `已按这个方案确认并执行。`

SQLite evidence:

```text
proposal id 18 status = executed, selected_option_id = A, related_event_id = 9, protocol_label = P1
created event id 9 = 去学校开会, 2026-05-26 10:00:00 - 11:00:00

proposal id 19 status = executed, selected_option_id = B, related_task_id = 2, related_event_id = 10, protocol_label = P1
created task id 2 = 复习数学, status = scheduled
created event id 10 = 复习数学（第1/2段）, 2026-05-15 14:00:00 - 16:00:00
created event id 11 = 复习数学（第2/2段）, 2026-05-17 14:00:00 - 16:00:00
assistant_messages contains user content 接受 P1 方案A
assistant_messages contains user content 接受 P1 方案B
```

## Final Full Browser Acceptance

Status: passed.

Environment:

- Backend: `http://127.0.0.1:8014`
- Frontend: `http://127.0.0.1:8890`
- SQLite DB: `E:\GraduationProject\backend\data\browser_inline_final_20260515.db`
- Backend health confirmed `database_path = E:\GraduationProject\backend\data\browser_inline_final_20260515.db`
- Browser: Chromium via Playwright MCP

Browser sequence:

1. Started from a new clean DB with zero events and zero tasks.
2. Sent `5月27号上午9点到10点去学校办手续`, clicked inline option A, and confirmed the assistant sent `接受 P1 方案A` then created the event.
3. Sent `5月28号下午2点到3点去图书馆看书`, clicked `拒绝全部方案`, and confirmed the assistant sent `拒绝 P1 全部方案` without creating an event.
4. Sent `这周帮我安排复习物理`, clicked inline option C, and confirmed the assistant created one scheduled task plus three focus blocks.
5. Sent `后天下午去图书馆`, then `把方案A改成晚上8点`; the assistant rendered a revised inline card for `20:00-21:00`, and clicking option A created the revised event.
6. Sent `明天下午3点去学校开会，晚上8点提醒我复习英语`; the assistant rendered separate P1/P2 proposals. P1 was rejected via inline `拒绝全部方案`, P2 was accepted via option A.
7. Sent `5月29号上午10点到11点去学校开会`, refreshed the page before accepting, confirmed the pending inline card recovered from persisted data, then clicked option A successfully.
8. Switched to `390x844` mobile viewport and opened the bottom `助手` tab. Confirmed session controls stayed in view, inline proposal state was readable, and the executed reply remained visible without horizontal overflow.

SQLite evidence:

```text
assistant_sessions = 6
assistant_messages = 28
assistant_proposals = 8
events = 7
tasks = 1

proposal 1 executed selected A related_event_id 1 protocol_label P1
proposal 2 rejected selected None protocol_label P1
proposal 3 executed selected C related_task_id 1 related_event_id 2 protocol_label P1
proposal 4 superseded protocol_label P1
proposal 5 executed selected A related_event_id 5 protocol_label P1
proposal 6 rejected protocol_label P1
proposal 7 executed selected A related_event_id 6 protocol_label P2
proposal 8 executed selected A related_event_id 7 protocol_label P1

event 1 = 去学校办手续, 2026-05-27 09:00-10:00
event 2 = 复习物理（第1/3段）, 2026-05-15 17:00-18:00
event 3 = 复习物理（第2/3段）, 2026-05-16 17:00-18:30
event 4 = 复习物理（第3/3段）, 2026-05-17 17:00-19:00
event 5 = 去图书馆, 2026-05-17 20:00-21:00
event 6 = 复习英语, 2026-05-16 19:00-20:00
event 7 = 去学校开会, 2026-05-29 10:00-11:00
task 1 = 复习物理, status scheduled

user protocol messages:
接受 P1 方案A
拒绝 P1 全部方案
接受 P1 方案C
把方案A改成晚上8点
接受 P1 方案A
拒绝 P1 全部方案
接受 P2 方案A
接受 P1 方案A
```

Validation after final browser acceptance:

```powershell
cd E:\GraduationProject\backend
.\.venv312\Scripts\python.exe -m pytest tests/test_assistant_text_protocol.py tests/test_assistant_conductor.py tests/test_assistant_proposal_revise.py tests/test_assistant_service.py -q
```

Result:

```text
188 passed
```

```powershell
cd E:\GraduationProject\frontend
npm run build
```

Result:

```text
passed
```

Residual notes:

- The browser automation timeout during final refresh recovery was caused by a Playwright text selector matching a hidden session `<option>`; manual page inspection showed the recovered inline card visible and clickable, and the follow-up click executed successfully.
- Backend error log `browser-inline-final-8014.err.log` was empty during the final run.

## 2026-05-16 Inline Card Terminal-State Retention

Status: passed.

Reason for change:

- User feedback: after a proposal is selected, removing the inline option card leaves only plain text and makes the conversation visually poor.
- Updated expected behavior: after accepting or rejecting a proposal, keep the inline card inside the assistant bubble, disable all options, and render the card in a grey terminal state.

Fix:

- `frontend/src/components/AssistantPanel.vue`
  - Removed the render-block filter that hid submitted inline proposal cards.
  - Kept the card visible after click and marked it locally as selected/rejected until the backend status refresh arrives.
  - Rendered terminal-state cards with grey styling and disabled option/reject buttons.
  - Preserved the selected option marker for accepted/executed proposals.
- `frontend/src/stores/assistant.ts`
  - Included terminal statuses (`executed`, `rejected`, `expired`, `superseded`) when refreshing assistant proposals.
  - Added `session_id` to proposal refresh requests and raised the limit to `100`, so historical inline cards can recover their true terminal status after page refresh.

Validation:

```powershell
cd E:\GraduationProject\frontend
npm run build
```

Result:

```text
passed
```

Browser retest:

1. Opened the real frontend at `http://127.0.0.1:8890`.
2. Created a new assistant session.
3. Sent `6月1号上午10点到11点去学校开会`.
4. Before click:
   - inline `AI 方案` card was visible.
   - option A was visible and enabled.
5. Clicked option A.
6. After click:
   - inline `AI 方案` card was still visible.
   - option A was still rendered but disabled.
   - user protocol message `接受 P1 方案A` appeared.
   - assistant reply `已按这个方案确认并执行。` appeared.
7. Refreshed the page.
8. After refresh:
   - inline `AI 方案` card was still visible.
   - option A was visible and disabled.
   - terminal status text `已执行` was visible.
9. Created another session.
10. Sent `6月2号下午2点到3点去图书馆看书`.
11. Clicked `拒绝全部方案`.
12. After reject:
   - inline `AI 方案` card was still visible.
   - option A and `拒绝全部方案` were visible but disabled.
   - terminal status text `已拒绝` was visible.
   - user protocol message `拒绝 P1 全部方案` appeared.
   - assistant reply `已暂不安排这个方案，没有执行任何写入。` appeared.

Browser evidence summary:

```text
accept before: optionCount=1, optionDisabled=false, aiCardVisible=true
accept after: optionCount=1, optionDisabled=true, aiCardVisible=true, protocol=true, reply=true
accept after refresh: aiCardVisible=true, optionVisible=true, optionDisabled=true, statusText=已执行

reject after: aiCardVisible=true, optionDisabled=true, rejectDisabled=true, protocol=true, reply=true, statusText=已拒绝
```

## 2026-05-16 Final Coverage Addendum

Status: passed.

Scope:

- Verified that the latest terminal-state retention behavior supersedes the earlier hide-after-click behavior.
- Rechecked the remaining full-function browser acceptance gaps on the clean final database.
- Re-ran the backend and frontend verification commands after the terminal-state UI change.

Clean DB:

```text
E:\GraduationProject\backend\data\browser_inline_final_20260515.db
assistant_sessions = 13
assistant_messages = 56
assistant_proposals = 16
events = 12
tasks = 1
```

Browser-level evidence:

```text
normal non-scheduling request:
- input: 你是谁？
- result: assistant asked for the desired output instead of creating a proposal.
- evidence: no matching assistant_proposals row was created for the request.

fuzzy time multi-option request:
- proposal 9, session 7
- status: executed
- selected option: B
- options: A/B/C
- created event 8: 去图书馆, 2026-05-16 15:30-16:30

conflict request:
- existing event 9: 去学校开会, 2026-05-30 15:00-16:00
- input: 5月30号下午3点到4点去学校讨论项目
- proposal 11 status: executed
- selected option: B
- options: A/B
- diagnostics.direct_conflicts included event 9.
- created event 10: 去学校讨论项目，去学校开会, 2026-05-30 15:00-16:00

ambiguous confirmation with multiple pending proposals:
- input: 可以
- result: assistant clarified which pending proposal was intended.
- assistant reply: 我不确定你指的是哪个待确认方案。请直接说“按 P1”或“把 P2 改到明天上午”。

execution-failed retry:
- seeded proposal 16 with status execution_failed.
- browser input: 重试 P1
- result: proposal 16 status became executed.
- execution.retry_count = 1
- created event 12: 终验重试, 2026-06-03 10:00-11:00
- assistant reply: 已通过助手消息重试这个方案。

inline terminal-state UI:
- accept: option card remains visible, option disabled, status recovers to 已执行 after refresh.
- reject: option card remains visible, option and reject-all disabled, status shows 已拒绝.
```

Regression verification:

```powershell
cd E:\GraduationProject\backend
.\.venv312\Scripts\python.exe -m pytest tests/test_assistant_text_protocol.py tests/test_assistant_conductor.py tests/test_assistant_proposal_revise.py tests/test_assistant_service.py -q
```

Result:

```text
188 passed
```

```powershell
cd E:\GraduationProject\frontend
npm run build
```

Result:

```text
passed
```
