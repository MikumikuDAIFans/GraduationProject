# API 可用性测试记录

## 测试时间

- Date: 2026-03-25
- Timezone: Asia/Shanghai

## 测试范围

1. Gemini 文本生成
2. 高德地图 Web 服务
3. 和风天气 API
4. Google OAuth 凭据有效性
5. Google Client Secret JSON 与环境变量一致性

## 测试结果

### 1. Gemini

- Status: pass
- Test: 调用 `generateContent`
- Result: 成功返回预期文本 `GEMINI_OK`
- Conclusion: 当前 `GEMINI_API_KEY` 可正常使用；同时已额外验证稳定模型 `models/gemini-2.5-flash` 可用，后续建议统一采用稳定模型

### 2. 高德地图

- Status: pass
- Test: 调用地理编码接口查询“北京市天安门”
- Result: 返回 `info=OK`，成功得到坐标
- Conclusion: 当前 `MAP_API_KEY` 可正常使用

### 3. 和风天气

- Status: pass
- Test: 调用实时天气接口
- Result: 返回 `code=200`，成功得到天气与温度
- Conclusion: 当前 `QWEATHER_API_KEY` 与 `QWEATHER_API_HOST` 可正常使用

### 4. Google OAuth

- Status: pass
- Test: 使用真实 `client_id/client_secret` 调用 token 端点，故意提交伪造 code
- Result: 返回 `invalid_grant`
- Conclusion: 这说明客户端凭据本身有效，失败原因是测试 code 无效，属于预期结果

### 5. Google Client Secret JSON

- Status: pass
- Test: 校验 JSON 文件存在且 `client_id` 与环境变量一致
- Result: 文件存在，类型为 `web`，`client_id` 匹配
- Conclusion: 当前 Google OAuth 配置文件与环境变量一致

## 结论

当前用于开发的核心外部能力已经通过基础可用性测试：

1. Gemini
2. 高德地图
3. 和风天气
4. Google OAuth 配置

## 当前限制

1. Google Calendar 的真正读写测试仍需要后续完成用户授权流程
2. Redis 尚未安装，因此 Redis/Celery 相关运行验证尚未开始

## 下一步建议

开始搭建后端代码骨架，并优先完成：

1. SQLite 数据模型
2. Redis 安装与接入
3. FastAPI 基础工程
4. 事件、任务、提醒基础表
