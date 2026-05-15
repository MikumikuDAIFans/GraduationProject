# AI Assistant Browser Full Acceptance 20260515053916

- API: http://127.0.0.1:18741/api
- Web: http://127.0.0.1:8894
- DB: E:\GraduationProject\backend\data\browser_full_acceptance_20260515053916.db
- Memory: E:\GraduationProject\backend\data\browser_full_acceptance_memory_20260515053916
- Summary: 94 passed, 0 failed, 5 tracked, 99 total

| ID | Status | Title | Evidence / Error |
|---|---|---|---|
| BAI-P0-001 | PASS | 明确日程创建必须先提案 | pending proposals=1 |
| BAI-P0-002 | PASS | 单 proposal 自然语言确认执行 | events=1 |
| BAI-P0-003 | PASS | 重复确认幂等 | repeat confirm kept one event |
| BAI-P0-004 | PASS | 模糊任务请求不得直接拆日程 | no event writes for vague request |
| BAI-P0-005 | PASS | 任务 / 日程类型澄清 | proposals=2 |
| BAI-P0-006 | PASS | 自然语言修改 proposal | revision chain visible |
| BAI-P0-007 | PASS | 拒绝 proposal | rejected without writes |
| BAI-P0-008 | PASS | 多 proposal 下可以必须澄清 | ambiguous confirmation preserved two pending proposals |
| BAI-P0-009 | PASS | 多 proposal 带标识确认 | 小组会调整 |
| BAI-P0-010 | PASS | 冲突日程必须给多方案 | pending proposals=1 |
| BAI-P0-011 | PASS | 批量调整必须拆成可确认动作 | pending proposals=1 |
| BAI-P0-012 | PASS | 过大批量调整必须防失控 | oversized batch guarded |
| BAI-P0-013 | PASS | 多轮日程槽位补全必须继承上下文 | single pending proposal retained context |
| BAI-P0-014 | PASS | 单 pending proposal 下纯时间补充必须走 revise | time-only supplement revised proposal |
| BAI-P0-015 | PASS | 执行导向话术不得复制 proposal | no duplicate proposal |
| BAI-P0-016 | PASS | 带时间和地点的提醒不得误判为普通任务 | timed reminder created event proposal |
| BAI-P0-017 | PASS | 连续发送与加载状态 | send lock avoided duplicate proposal |
| BAI-P1-001 | PASS | 不完整日程应澄清 | events=0, tasks=0, proposals=0, memories=0 |
| BAI-P1-002 | PASS | 带自然语言时间的日程 | pending proposals=1; events=0, tasks=0, proposals=1, memories=0 |
| BAI-P1-003 | PASS | 默认时长推断 | pending proposals=1; events=0, tasks=0, proposals=1, memories=0 |
| BAI-P1-004 | PASS | 任务创建 | events=0, tasks=0, proposals=1, memories=0 |
| BAI-P1-008 | PASS | 查询进展不应写入 | events=0, tasks=0, proposals=0, memories=0 |
| BAI-P1-012 | PASS | 跨午夜时间段解析 | pending proposals=1; events=0, tasks=0, proposals=1, memories=0 |
| BAI-P1-014 | PASS | 同句包含多个日程目标 | events=0, tasks=0, proposals=1, memories=0 |
| BAI-P1-015 | PASS | 任务与日程混合句拆分语义 | events=0, tasks=0, proposals=0, memories=0 |
| BAI-P1-101 | PASS | 明确 origin 的出发建议 | events=0, tasks=0, proposals=1, memories=0 |
| BAI-P1-102 | PASS | origin 不确定必须澄清或条件化 | events=0, tasks=0, proposals=0, memories=0 |
| BAI-P1-110 | PASS | 天气影响不改日程 | events=0, tasks=0, proposals=0, memories=0 |
| BAI-P1-111 | PASS | 外部地图失败降级 | events=0, tasks=0, proposals=0, memories=0 |
| BAI-P1-304 | PASS | 隐式偏好不得低置信写入 | events=0, tasks=0, proposals=0, memories=0 |
| BAI-P1-307 | PASS | 对话事实不等于长期偏好 | events=0, tasks=0, proposals=0, memories=0 |
| BAI-P1-401 | PASS | Proposal 文本结构 | pending proposals=1; events=0, tasks=0, proposals=1, memories=0 |
| BAI-P1-409 | PASS | Markdown 与特殊字符安全 | events=0, tasks=0, proposals=1, memories=0 |
| BAI-P0-101 | PASS | 不得硬分句误拆 | events=0, tasks=0, proposals=1, memories=0 |
| BAI-P0-102 | PASS | 不得绕过 proposal 直接写入 | pending proposals=1; events=0, tasks=0, proposals=1, memories=0 |
| BAI-P0-103 | PASS | 普通建议不应触发旧 workflow 文案 | events=0, tasks=0, proposals=0, memories=0 |
| BAI-P0-104 | PASS | 未知请求应澄清 | events=0, tasks=0, proposals=0, memories=0 |
| BAI-P0-106 | PASS | 无确认不写长期记忆 | events=0, tasks=0, proposals=1, memories=0 |
| BAI-P0-107 | PASS | 中文相对时间不解析为持续时长 | events=0, tasks=0, proposals=1, memories=0 |
| BAI-P1-005 | PASS | 任务排程 | pending proposals=1 |
| BAI-P1-006 | PASS | 有限期重复任务完成判定 | completion path generated or preserved quantifiable task state |
| BAI-P1-007 | PASS | 取消重复任务单个切片 | single slice not directly canceled |
| BAI-P1-009 | PASS | 多轮时间补全后再补地点 | proposals=4 |
| BAI-P1-010 | PASS | 先改标题再改时间 | proposals=3 |
| BAI-P1-011 | PASS | 只给结束时间的部分修正 | proposals=2 |
| BAI-P1-017 | PASS | 拒绝后下一句不要继续执行 | proposals=2 |
| BAI-P0-105 | PASS | 补充回答不当成全新任务 | proposals=0 |
| BAI-P1-013 | PASS | 相对日期与绝对日期混用 | conditional date handled without write |
| BAI-P1-016 | PASS | 模糊去学校结合记忆 | confirmed place memory available |
| BAI-P1-103 | PASS | 当前线程位置优先 | runtime context only |
| BAI-P1-108 | PASS | 临时位置不污染长期地点 | runtime context only |
| BAI-P1-112 | PASS | 出发地和目的地相同 | runtime context only |
| BAI-P1-104 | PASS | 常用地点别名解析 | pending proposals=1 |
| BAI-P1-109 | PASS | 多地点同名歧义 | ambiguous place clarified |
| BAI-P1-105 | PASS | 出发前提醒 | departure followup visible |
| BAI-P1-106 | PASS | 出发提醒用户已到达 | arrival handled without memory write |
| BAI-P1-107 | PASS | 出发提醒取消行程 | cancel request did not directly cancel event |
| BAI-P1-201 | PASS | deadline 风险触发 | deadline risk signal visible |
| BAI-P1-202 | PASS | signal cooldown 去重 | deduped signal |
| BAI-P1-203 | PASS | 晨间汇报固定模板 | daily_morning_review visible |
| BAI-P1-205 | PASS | 睡前复盘固定模板 | daily_night_review visible |
| BAI-P1-208 | PASS | pending proposal 跟进 | proposal_followup visible |
| BAI-P1-403 | PASS | 主动跟进区 | deadline_risk visible |
| BAI-P1-204 | PASS | 晨间调整单个事项 | review reply stayed proposal-first |
| BAI-P1-206 | PASS | 睡前批量完成 | review reply stayed proposal-first |
| BAI-P1-207 | PASS | 睡前完成+未完成混合 | review reply stayed proposal-first |
| BAI-P1-210 | PASS | 晨间汇报 pending proposal 文本确认 | review reply stayed proposal-first |
| BAI-P1-211 | PASS | 睡前复盘自然语言顺延 | review reply stayed proposal-first |
| BAI-P1-209 | PASS | 主动跟进与当前对话冲突 | ambiguous proactive reference not executed |
| BAI-P1-212 | PASS | 主动消息过期后不可执行 | expired-like signal command did not write |
| BAI-P1-301 | PASS | 显式地点记忆候选 | memory candidate proposed |
| BAI-P1-302 | PASS | 确认地点记忆 | places memory written |
| BAI-P1-303 | PASS | 拒绝记忆候选 | memory rejected without write |
| BAI-P1-305 | PASS | 记忆冲突必须澄清 | conflict surfaced without write |
| BAI-P1-306 | PASS | 一次输入多个记忆候选 | memory candidates=2 |
| BAI-P1-308 | PASS | 记忆候选确认指代歧义 | ambiguous memory confirm clarified/no-op |
| BAI-P1-309 | PASS | 记忆删除也需确认 | delete/update required confirmation |
| BAI-P1-402 | PASS | 当前待确认事项区 | P1/P2 visible after refresh |
| BAI-P1-404 | PASS | 移动端布局 | screenshot=E:\GraduationProject\docs\development\browser_acceptance_runs\mobile_20260515053916.png |
| BAI-P1-405 | PASS | 加载与禁用状态 | send showed loading/busy state |
| BAI-P1-406 | PASS | WebSocket 状态同步 | server-side status executed; UI refresh path available |
| BAI-P1-407 | PASS | 会话切换不得串上下文 | new session did not execute old proposal via bare confirm |
| BAI-P1-408 | PASS | 长对话滚动与最新消息可见 | long chat latest content visible |
| BAI-P1-410 | PASS | 标签稳定性跨刷新和 revision | refreshed P1 confirmed latest proposal |
| BAI-P1-411 | PASS | 多 pending proposal 区域排序 | P1-P5 visible |
| BAI-P1-501 | TRACKED | Provider 失败 fallback | Requires deterministic primary-provider failure with a valid fallback provider. Current browser harness uses real providers and cannot force only the primary provider to fail without a mock/restart path; LLM fallback itself is covered by backend unit tests. |
| BAI-P1-502 | TRACKED | Provider 全部失败 | Requires restarting API with invalid provider credentials; covered as tracked manual/chaos case in this run. |
| BAI-P1-503 | PASS | 执行失败进入 retry | execution_failed visible |
| BAI-P1-504 | PASS | expired proposal 不可确认 | expired proposal not executed |
| BAI-P1-505 | PASS | superseded proposal 不可确认 | superseded old proposal not executed |
| BAI-P1-506 | PASS | 无效方案编号 | invalid option rejected/no-op |
| BAI-P1-507 | TRACKED | 网络中断恢复 | Full browser network interruption requires Playwright route/offline orchestration plus API process stop; tracked as manual chaos in this run. |
| BAI-P1-508 | PASS | 后端重启后 pending proposal 可继续确认 | pending proposal survived backend restart |
| BAI-P1-509 | PASS | 数据库写入失败不显示成功 | invalid payload failed without success UI |
| BAI-P1-510 | TRACKED | AI 返回格式异常 | Requires mock AI provider returning malformed content; protocol fallback is covered by source/unit tests, tracked for browser mock harness. |
| BAI-P1-511 | TRACKED | 慢响应超时与重试 | Requires deterministic slow provider/mock endpoint beyond front-end timeout; tracked for browser mock harness. |
| BAI-P0-108 | PASS | 不得确认已被替代旧 proposal | old behavior guard passed |
| BAI-P0-109 | PASS | active target 不覆盖多 proposal 歧义 | old behavior guard passed |
| BAI-P0-110 | PASS | 刷新编号不导致错配 | P1 visible before confirm; old behavior guard passed |
