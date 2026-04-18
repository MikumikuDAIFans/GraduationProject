"""Prompt模板管理"""

# 意图识别Prompt
INTENT_DETECTION_TEMPLATE = """你是一个个人事务助手的意图识别模块。请分析用户的输入，识别其意图并提取相关信息。

支持的意图类型：
- create_event: 创建日程/事件
- create_task: 创建任务
- update_event: 更新日程
- delete_event: 删除日程
- query_events: 查询日程
- query_tasks: 查询任务
- chat: 闲聊/其他

请严格按照以下JSON格式返回结果：
{{
    "intent": "意图类型",
    "slots": {{
        // 根据意图提取的槽位信息
    }},
    "confidence": 0.0-1.0之间的置信度
}}

对于create_event意图，slots应包含：
{{
    "title": "事件标题",
    "start_time": "开始时间（ISO格式或自然语言）",
    "end_time": "结束时间（可选）",
    "duration_minutes": "持续时间（分钟，可选）",
    "location": "地点（可选）",
    "description": "描述（可选）",
    "priority": "优先级 0-3（可选）",
    "energy_level": "所需能量水平 high/medium/low（可选）"
}}

对于create_task意图，slots应包含：
{{
    "title": "任务标题",
    "due_date": "截止日期（可选）",
    "estimated_minutes": "预估时间（分钟，可选）",
    "priority": "优先级 0-3（可选）",
    "description": "描述（可选）"
}}

用户输入：{user_message}

请返回JSON："""

# 槽位补全Prompt
SLOT_FILLING_TEMPLATE = """用户想要{intent}，但信息不完整。

当前已获取的信息：
{filled_slots}

缺失的信息：
{missing_slots}

请根据上下文，生成一个自然的问题来询问用户缺失的信息。
只返回问题文本，不要返回JSON。

示例：
- 如果缺少time，问："请问你希望安排在什么时间呢？"
- 如果缺少title，问："请问这个事件的名称是什么？"

你的问题："""

# 冲突解释Prompt
CONFLICT_EXPLANATION_TEMPLATE = """检测到以下时间冲突：
{conflicts}

请用简洁、友好的中文向用户解释冲突，并提供建议。
不要使用技术术语。

你的回复："""

# 习惯提示Prompt
HABIT_HINT_TEMPLATE = """根据用户的历史习惯，以下模式可能相关：
{habits}

请在回复中自然地提及这些习惯，帮助用户做出更好的决策。

你的回复："""

# 回复渲染Prompt
RESPONSE_RENDER_TEMPLATE = """你是一个个人事务助手。请根据以下信息生成回复：

意图：{intent}
执行的动作：{actions}
检测到的冲突：{conflicts}
建议：{suggestions}
相关习惯：{habits}
天气信息：{weather}
交通信息：{traffic}

要求：
1. 使用简洁、友好的中文
2. 如果有冲突，清楚地解释问题并提供替代方案
3. 如果有相关习惯，自然地提及它们
4. 如果有天气/交通信息，适当地提醒用户
5. 保持回复简短，不超过3段

你的回复："""
