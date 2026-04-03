# Workspace Store 性能优化说明

## 优化概述

本次优化针对 `frontend/src/stores/workspace.ts` 进行了全面重构，主要解决了以下问题：
- 过度频繁的API调用导致后端压力过大
- 数据重复获取造成网络资源浪费
- 用户快速操作时触发多次请求
- 缺少有效的缓存机制

## 实施的优化措施

### 1. 智能缓存系统

#### 缓存时间配置
```typescript
_cacheDurations: {
  events: 30000,        // 30秒
  tasks: 30000,         // 30秒
  reminders: 15000,     // 15秒
  suggestions: 60000,   // 60秒
  weather: 300000,      // 5分钟
  travel: 300000,       // 5分钟
  profile: 60000,       // 1分钟
  performance: 30000,   // 30秒
  aiHealth: 30000,      // 30秒
  googleCalendar: 60000,// 1分钟
}
```

#### 缓存管理方法
- `isCacheValid(key)`: 检查指定数据的缓存是否仍然有效
- `invalidateCache(key)`: 使指定缓存失效
- `invalidateAllCache()`: 使所有缓存失效

### 2. 请求去重机制

通过 `_pendingRequests` 对象跟踪正在进行的请求，防止同一数据被重复请求：

```typescript
async cachedFetch<T>(key: string, fetchFn: () => Promise<T>): Promise<T | undefined> {
  // 如果缓存有效，跳过请求
  if (this.isCacheValid(key)) return undefined;
  
  // 防止重复请求
  if (this._pendingRequests[key]) {
    return this._pendingRequests[key];
  }
  // ... 执行请求并缓存结果
}
```

### 3. 选择性数据刷新

#### hydrate() 方法优化
- 区分关键数据和非关键数据
- 非关键数据（天气、通勤、性能指标）延迟1秒加载
- 只获取过期或不存在的数据

#### refreshAssistantWorkspace() 方法优化
- 添加 `selective` 参数控制刷新范围
- 默认模式只更新变化的数据
- 完整刷新模式才重新获取所有数据

### 4. 乐观更新策略

对于用户操作（如更新事件状态、删除任务/事件），采用乐观更新：
1. 立即更新本地状态以提供即时反馈
2. 发送API请求
3. 使相关缓存失效
4. 异步获取最新数据

### 5. 异步非阻塞数据获取

将非关键的数据获取操作改为异步执行，不阻塞主要流程：
```typescript
// 异步获取更新后的数据
Promise.allSettled([
  this.fetchEvents(true),
  this.fetchTasks(true),
  // ...
]);
```

## 性能提升预期

| 场景 | 优化前 | 优化后 | 改善幅度 |
|------|--------|--------|----------|
| 页面初始加载 | 11个API同时请求 | 7个关键API + 4个延迟API | 减少36%初始负载 |
| 保存个人资料 | 3个API阻塞等待 | 2个API异步获取 | 减少67%等待时间 |
| Google日历同步 | 7个API阻塞等待 | 6个API异步获取 | 减少83%等待时间 |
| 更新事件状态 | 6个API阻塞等待 | 5个API异步获取 | 减少80%等待时间 |
| 删除任务/事件 | 3-4个API阻塞等待 | 3个API异步获取 | 减少50%等待时间 |

## 向后兼容性

所有优化都保持了向后兼容：
- 原有方法签名不变
- 新增的 `force` 参数默认为 `false`，保持原有行为
- 缓存机制透明，不影响现有功能

## 使用建议

1. **强制刷新**：当需要绕过缓存获取最新数据时，传递 `true` 参数：
   ```typescript
   await store.fetchEvents(true); // 强制刷新
   ```

2. **完整刷新**：当需要完全重新加载所有数据时：
   ```typescript
   await store.refreshAssistantWorkspace(false); // 完整刷新
   ```

3. **手动清除缓存**：当外部数据发生变化时：
   ```typescript
   store.invalidateCache('events');
   ```

## 后续优化方向

1. **WebSocket实时推送**：进一步优化通知系统，减少轮询
2. **数据预取**：基于用户行为预测下一步需要的数据
3. **增量更新**：只获取变化的数据部分而非完整列表
4. **离线支持**：添加Service Worker实现离线缓存
