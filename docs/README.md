# MA-IPAAS 项目文档中心

本目录包含 MA-IPAAS（Multi-Agent Intelligent Personal Affairs Assistant System）项目的开发、测试、项目管理、学术与用户文档。

## 当前文档状态

- 当前代码库已明显超出早期 V3/V4 阶段。
- 项目**主体实现已推进到 V6 施工期**：V6 相关数据模型、服务、测试与前端 Store 拆分已经进入代码库。
- 项目**已混入少量 V7 优化**：如助手流式输出、部分外部上下文按需/并行获取、部分超时优化。
- 但 **V7 的 LangGraph++ 工作流重构尚未真正接管主流程**，因此不能认定为“已到 V7 完成态”。

建议先阅读：

- [CURRENT_IMPLEMENTATION_STATUS.md](./development/CURRENT_IMPLEMENTATION_STATUS.md) - 当前实现状态审计（2026-04-18）
- [TASK_BOOK.md](./project-management/TASK_BOOK.md) - 当前任务书与推进台账
- [IMPLEMENTATION_STATUS_REVIEW.md](./project-management/STATUS_REVIEWS/IMPLEMENTATION_STATUS_REVIEW.md) - V6/V7 版本审查结论

## 文档分类

### 开发文档 `development/`

- [ARCHITECTURE.md](./development/ARCHITECTURE.md) - 架构设计方案
- [TECHNICAL_SPEC.md](./development/TECHNICAL_SPEC.md) - 技术规格说明
- [IMPLEMENTATION_PLAN_V3.md](./development/IMPLEMENTATION_PLAN_V3.md) - V3 实施计划
- [IMPLEMENTATION_PLAN_V4.md](./development/IMPLEMENTATION_PLAN_V4.md) - V4 实施计划
- [IMPLEMENTATION_PLAN_V5.md](./development/IMPLEMENTATION_PLAN_V5.md) - V5 实施计划
- [IMPLEMENTATION_PLAN_V6.md](./development/IMPLEMENTATION_PLAN_V6.md) - V6 实施计划
- [IMPLEMENTATION_PLAN_V7.md](./development/IMPLEMENTATION_PLAN_V7.md) - V7 实施计划
- [CURRENT_IMPLEMENTATION_STATUS.md](./development/CURRENT_IMPLEMENTATION_STATUS.md) - 当前实现状态审计
- [MA-IPAAS_SYSTEM_DOC.md](./development/MA-IPAAS_SYSTEM_DOC.md) - 系统完整说明
- [WORKSPACE_OPTIMIZATION.md](./development/WORKSPACE_OPTIMIZATION.md) - 工作区优化说明
- [API_KEY_REFERENCES.txt](./development/API_KEY_REFERENCES.txt) - API 密钥参考清单

### 测试文档 `testing/`

- [API_AVAILABILITY_TEST_REPORT.md](./testing/API_AVAILABILITY_TEST_REPORT.md) - API 可用性测试
- [BUGFIX_SUMMARY.md](./testing/BUGFIX_SUMMARY.md) - Bug 修复总结
- [FRONTEND_BUTTON_TEST_REPORT.md](./testing/FRONTEND_BUTTON_TEST_REPORT.md) - 前端按钮测试
- [TEST_ALL_BUTTONS.md](./testing/TEST_ALL_BUTTONS.md) - 按钮全量测试
- [V6_NEW_FEATURES_REPORT.md](./testing/V6_NEW_FEATURES_REPORT.md) - V6 功能测试草案

### 项目管理 `project-management/`

- [TASK_BOOK.md](./project-management/TASK_BOOK.md) - 当前任务书
- [STATUS_REVIEWS/IMPLEMENTATION_STATUS_REVIEW.md](./project-management/STATUS_REVIEWS/IMPLEMENTATION_STATUS_REVIEW.md) - 当前版本审查
- [CHECKLISTS/EXTERNAL_PREPARATION_CHECKLIST.md](./project-management/CHECKLISTS/EXTERNAL_PREPARATION_CHECKLIST.md) - 外部准备检查清单

### 学术文档 `academic/`

- [REFERENCES.md](./academic/REFERENCES.md) - 参考资料表
- [INTRODUCTION_TXT.txt](./academic/INTRODUCTION_TXT.txt) - 项目介绍
- [PROPOSAL_SUMMARY.txt](./academic/PROPOSAL_SUMMARY.txt) - 开题摘要
- [THESIS_MATERIALS/PROJECT_SPEC.md](./academic/THESIS_MATERIALS/PROJECT_SPEC.md) - 论文素材规格
- [THESIS_MATERIALS/PRACTICAL_SIMPLE_ASSISTANT_PLAN.md](./academic/THESIS_MATERIALS/PRACTICAL_SIMPLE_ASSISTANT_PLAN.md) - 实用化方案草稿

### 用户指南 `user-guide/`

- [USER_GUIDE.md](./user-guide/USER_GUIDE.md) - 用户指南
- [MOBILE_SETUP.md](./user-guide/MOBILE_SETUP.md) - 移动端设置

### 贡献指南 `contributing/`

- [CONTRIBUTING.md](./contributing/CONTRIBUTING.md) - 贡献规范

## 维护约定

1. 实施计划文档保留历史版本，不直接覆盖旧版本含义。
2. 与“当前实现状态”有关的判断，以 `CURRENT_IMPLEMENTATION_STATUS.md` 与 `project-management/` 中最新台账为准。
3. 当代码处于大规模未提交改动阶段时，文档必须明确区分：
   - 已接入主流程
   - 仅存在于代码库但尚未接通
   - 仅存在于测试或方案中

---

最后更新时间：2026-04-18
