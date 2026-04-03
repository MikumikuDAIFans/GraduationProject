# MA-IPAAS 功能补全执行方案 V4

> 本文档为项目功能补全的详细落地执行方案，面向 AI 编码助手设计，要求接手后可一次性完成所有代码修改、单元测试编写和整体测试验证。

---

## 目录

- [一、现状总结与差距分析](#一现状总结与差距分析)
- [二、执行优先级与任务清单](#二执行优先级与任务清单)
- [三、P0 — 毕业答辩前必须完成](#三p0--毕业答辩前必须完成)
  - [P0-1: Tauri 2 桌面端封装](#p0-1-tauri-2-桌面端封装)
  - [P0-2: Capacitor 移动端封装](#p0-2-capacitor-移动端封装)
- [四、P1 — 功能深化](#四p1--功能深化)
  - [P1-1: 地图服务深度集成](#p1-1-地图服务深度集成)
  - [P1-2: 天气服务深度集成](#p1-2-天气服务深度集成)
- [五、P2 — 语音功能实现](#五p2--语音功能实现)
  - [P2-1: 语音输入适配器实现](#p2-1-语音输入适配器实现)
  - [P2-2: 语音输出适配器实现](#p2-2-语音输出适配器实现)
- [六、P3 — PWA 与优化](#六p3--pwa-与优化)
  - [P3-1: PWA 离线支持](#p3-1-pwa-离线支持)
  - [P3-2: 性能优化与打包](#p3-2-性能优化与打包)
- [七、单元测试规范](#七单元测试规范)
- [八、整体测试验证清单](#八整体测试验证清单)

---

## 一、现状总结与差距分析

### 已有架构概况

| 层级 | 现状 |
|------|------|
| 前端 | Vue 3 + TS + Vite + TailwindCSS + FullCalendar + Pinia，单 Store 架构 (`workspace.ts`)，WebSocket 驱动快照更新 |
| 后端 | FastAPI + SQLAlchemy 2 (async) + Alembic + Celery + Redis + SQLite |
| 分层 | `api/routes → services → repositories → models` |
| 数据库 | 7 张核心表均已建模完成 |
| 容器化 | Docker Compose 运行 API + Worker + Beat + Redis |
| 跨平台 | ❌ 未实现 |

### V3 完成情况回顾

| 优先级 | 任务编号 | 任务名称 | 状态 |
|--------|----------|----------|------|
| **P0** | P0-1 | 冲突检测 buffer 规则引擎 | ✅ 已完成 |
| **P0** | P0-2 | Celery Beat 高频提醒扫描（4 种频率） | ✅ 已完成 |
| **P0** | P0-3 | 前端提醒 Toast 弹窗 | ✅ 已完成 |
| **P1** | P1-1 | 后台主动任务跟进 Inbox 生成 | ✅ 已完成 |
| **P1** | P1-2 | 冲突时推荐替代时段 | ✅ 已完成 |
| **P1** | P1-3 | WebSocket `/ws/assistant` 流式输出 | ✅ 已完成 |
| **P2** | P2-1 | 语音输入/输出适配器接口预留 | ✅ 已完成（仅接口） |

### 与原始设计书（IMPLEMENTABLE_TECHNICAL_SPEC_V2.md）差距汇总

#### 已完全实现（✅）

| # | 功能 | 设计书章节 |
|---|------|------------|
| 1 | 技术栈（FastAPI + Vue 3 + SQLAlchemy 2） | §3.1, §3.2 |
| 2 | 7 张核心数据表 | §4.1 |
| 3 | 分层架构（api → services → repositories → models） | §3.3 |
| 4 | 调度引擎核心算法 | §8.2 |
| 5 | Assistant 工作流 | §8.1 |
| 6 | 工具层封装 | §8.3 |
| 7 | 4 种频率主动提醒 | §9.1 |
| 8 | Google Calendar 双向同步 | §10.2 |
| 9 | 完整测试覆盖 | §12 |

#### 部分实现（⚠️）

| # | 功能 | 当前状态 | 差距 | 设计书章节 |
|---|------|----------|------|------------|
| 10 | 语音输入/输出 | 仅预留 `inputAdapters/` / `outputAdapters/` 接口 | 缺少实际 STT/TTS 实现 | §11.3 |
| 11 | 地图服务 | 基础位置字段已存在 | 缺少路径时间计算、POI 推荐 | §10.4 |
| 12 | 天气服务 | 基础 weather 字段已存在 | 缺少实时获取、影响评估 | §10.5 |

#### 未实现（❌）

| # | 功能 | 设计书要求 | 设计书章节 |
|---|------|------------|------------|
| 13 | Capacitor 移动端封装 | Android APK + iOS IPA | §13.2 |
| 14 | Tauri 2 桌面端封装 | Windows EXE + macOS APP + 桌面通知 | §13.1 |
| 15 | PWA 离线支持 | Service Worker + 离线缓存 | §13.3 |

> 注：V4 计划聚焦于功能补全，跨平台封装（#13, #14）作为重点，PWA（#15）作为可选优化。

---

## 二、执行优先级与任务清单

| 优先级 | 任务编号 | 任务名称 | 预计涉及文件数 | 预计工时 |
|--------|----------|----------|----------------|----------|
| **P0** | P0-1 | Tauri 2 桌面端封装 | 8 | 3-5 天 |
| **P0** | P0-2 | Capacitor 移动端封装 | 10 | 5-7 天 |
| **P1** | P1-1 | 地图服务深度集成 | 6 | 2-3 天 |
| **P1** | P1-2 | 天气服务深度集成 | 5 | 1-2 天 |
| **P2** | P2-1 | 语音输入适配器实现 | 4 | 1-2 天 |
| **P2** | P2-2 | 语音输出适配器实现 | 4 | 1-2 天 |
| **P3** | P3-1 | PWA 离线支持 | 5 | 2-3 天 |
| **P3** | P3-2 | 性能优化与打包 | 6 | 1-2 天 |

---

## 三、P0 — 毕业答辩前必须完成

### P0-1: Tauri 2 桌面端封装

#### 目标

将现有 Web 应用封装为桌面应用（Windows EXE + macOS APP），支持系统级桌面通知、系统托盘、全局快捷键等功能。

#### 涉及文件

1. `frontend/package.json` — 新增 Tauri 依赖
2. `frontend/src-tauri/` — Tauri 配置目录（新建）
3. `frontend/src-tauri/Cargo.toml` — Rust 依赖配置
4. `frontend/src-tauri/tauri.conf.json` — Tauri 配置文件
5. `frontend/src-tauri/build.rs` — 构建脚本
6. `frontend/src-tauri/src/main.rs` — Rust 入口
7. `frontend/src-tauri/src/lib.rs` — Rust 库
8. `frontend/src/main.ts` — 适配 Tauri API

#### 详细实现步骤

##### 步骤 1：安装 Tauri CLI 和依赖

在 `frontend/package.json` 中新增依赖：

```json
{
  "devDependencies": {
    "@tauri-apps/cli": "^2.0.0",
    "@tauri-apps/api": "^2.0.0"
  }
}
```

运行安装命令：
```bash
cd frontend
pnpm install
```

##### 步骤 2：初始化 Tauri 项目

在项目根目录运行：
```bash
cd frontend
pnpm tauri init
```

配置项：
- App name: `ma-ipaas-desktop`
- Window title: `MA-IPAAS 智能事务助手`
- Dev server URL: `http://localhost:8888`

##### 步骤 3：配置 `tauri.conf.json`

**文件**: `frontend/src-tauri/tauri.conf.json`

```json
{
  "$schema": "https://schema.tauri.app/config/2",
  "productName": "ma-ipaas-desktop",
  "version": "1.0.0",
  "identifier": "com.ma-ipaas.desktop",
  "build": {
    "beforeDevCommand": "pnpm dev",
    "devUrl": "http://localhost:8888",
    "beforeBuildCommand": "pnpm build",
    "frontendDist": "../dist"
  },
  "app": {
    "withGlobalTauri": true,
    "windows": [
      {
        "title": "MA-IPAAS 智能事务助手",
        "width": 1400,
        "height": 900,
        "resizable": true,
        "fullscreen": false,
        "center": true
      }
    ],
    "security": {
      "csp": null
    }
  },
  "bundle": {
    "active": true,
    "targets": ["msi", "nsis", "dmg"],
    "icon": [
      "icons/32x32.png",
      "icons/128x128.png",
      "icons/icon.ico"
    ]
  }
}
```

##### 步骤 4：实现桌面通知功能

**文件**: `frontend/src-tauri/src/main.rs`

```rust
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use tauri_plugin_notification::NotificationExt;

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_notification::init())
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
```

在 `frontend/src-tauri/Cargo.toml` 中添加：
```toml
[dependencies]
tauri-plugin-notification = "2.0"
```

##### 步骤 5：在前端调用桌面通知

**文件**: `frontend/src/stores/workspace.ts`

在现有的 `showToast()` 方法基础上，新增 `sendDesktopNotification()` 方法：

```typescript
import { invoke } from '@tauri-apps/api/core'
import { sendNotification } from '@tauri-apps/plugin-notification'

export const useWorkspaceStore = defineStore('workspace', () => {
  // ... existing code ...

  const sendDesktopNotification = async (title: string, body: string) => {
    if ('__TAURI_INTERNALS__' in window) {
      // Tauri 环境
      await sendNotification({ title, body })
    } else {
      // Web 环境，降级为浏览器通知
      if ('Notification' in window && Notification.permission === 'granted') {
        new Notification(title, { body })
      }
    }
  }

  return {
    // ... existing exports ...
    sendDesktopNotification,
  }
})
```

在提醒触发时调用：
```typescript
// 在收到 WebSocket 提醒消息时
workspaceStore.sendDesktopNotification('新提醒', reminder.content)
```

##### 步骤 6：添加系统托盘图标

**文件**: `frontend/src-tauri/tauri.conf.json`

在 `app` 节点下添加：
```json
"systemTray": {
  "iconPath": "icons/tray-icon.png",
  "iconAsTemplate": true
}
```

**文件**: `frontend/src-tauri/src/main.rs`

```rust
use tauri::{CustomMenuItem, SystemTray, SystemTrayMenu, SystemTrayEvent};
use tauri_plugin_shell::ShellExt;

fn main() {
    let tray_menu = SystemTrayMenu::new()
        .add_item(CustomMenuItem::new("show", "显示"))
        .add_item(CustomMenuItem::new("quit", "退出"));

    tauri::Builder::default()
        .plugin(tauri_plugin_notification::init())
        .system_tray(SystemTray::new().with_menu(tray_menu))
        .on_system_tray_event(|app, event| match event {
            SystemTrayEvent::LeftClick { .. } => {
                let window = app.get_webview_window("main").unwrap();
                window.show().unwrap();
                window.set_focus().unwrap();
            }
            _ => {}
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
```

##### 步骤 7：构建桌面应用

开发模式运行：
```bash
cd frontend
pnpm tauri dev
```

生产构建：
```bash
cd frontend
pnpm tauri build
```

构建产物位于：
- Windows: `frontend/src-tauri/target/release/bundle/msi/` 或 `nsis/`
- macOS: `frontend/src-tauri/target/release/bundle/dmg/`

##### 步骤 8：单元测试

**文件**: `frontend/tests/tauri.test.ts`（新建）

```typescript
import { describe, it, expect } from 'vitest'
import { sendNotification } from '@tauri-apps/plugin-notification'

describe('Tauri Desktop Features', () => {
  it('should send desktop notification', async () => {
    // Mock notification test
    expect(sendNotification).toBeDefined()
  })

  it('should have system tray', () => {
    // Tray icon presence test
    expect(window.__TAURI_INTERNALS__).toBeDefined()
  })
})
```

---

### P0-2: Capacitor 移动端封装

#### 目标

将现有 Web 应用封装为移动应用（Android APK + iOS IPA），支持原生通知、相机、地理位置等移动设备功能。

#### 涉及文件

1. `frontend/package.json` — 新增 Capacitor 依赖
2. `frontend/capacitor.config.ts` — Capacitor 配置文件
3. `frontend/android/` — Android 项目目录（自动生成）
4. `frontend/ios/` — iOS 项目目录（自动生成）
5. `frontend/src/plugins/capacitor.ts` — Capacitor 插件封装
6. `frontend/src/stores/workspace.ts` — 适配移动端通知
7. `public/icons/` — 应用图标资源
8. `public/splashscreens/` — 启动屏资源
9. `scripts/mobile-build.sh` — 构建脚本
10. `README_MOBILE.md` — 移动端使用说明

#### 详细实现步骤

##### 步骤 1：安装 Capacitor 核心包

在 `frontend/package.json` 中新增依赖：

```json
{
  "dependencies": {
    "@capacitor/core": "^6.0.0",
    "@capacitor/app": "^6.0.0",
    "@capacitor/haptics": "^6.0.0",
    "@capacitor/keyboard": "^6.0.0",
    "@capacitor/status-bar": "^6.0.0",
    "@capacitor/push-notifications": "^6.0.0",
    "@capacitor/geolocation": "^6.0.0",
    "@capacitor/camera": "^6.0.0"
  },
  "devDependencies": {
    "@capacitor/cli": "^6.0.0",
    "@capacitor/assets": "^3.0.0"
  }
}
```

运行安装：
```bash
cd frontend
pnpm install
```

##### 步骤 2：初始化 Capacitor

创建配置文件 `frontend/capacitor.config.ts`：

```typescript
import type { CapacitorConfig } from '@capacitor/core'

const config: CapacitorConfig = {
  appId: 'com.ma-ipaas.mobile',
  appName: 'MA-IPAAS',
  webDir: 'dist',
  server: {
    androidScheme: 'https'
  },
  plugins: {
    PushNotifications: {
      presentationOptions: ['badge', 'sound', 'alert']
    },
    StatusBar: {
      style: 'dark',
      backgroundColor: '#ffffff'
    }
  }
}

export default config
```

##### 步骤 3：添加 Android 和 iOS 平台

```bash
cd frontend
npx cap add android
npx cap add ios
```

##### 步骤 4：实现移动端通知

**文件**: `frontend/src/plugins/capacitor.ts`（新建）

```typescript
import { PushNotifications } from '@capacitor/push-notifications'
import { LocalNotifications } from '@capacitor/local-notifications'

export class MobileNotificationService {
  static async registerPushNotifications(): Promise<void> {
    await PushNotifications.requestPermissions()
    await PushNotifications.register()

    PushNotifications.addListener('registration', token => {
      console.log('Push registration success, token:', token.value)
      // TODO: 保存 token 到后端用于推送
    })

    PushNotifications.addListener('pushNotificationReceived', notification => {
      console.log('Push notification received:', notification)
    })

    PushNotifications.addListener('pushNotificationActionPerformed', notification => {
      console.log('Push notification action performed:', notification.actionId)
    })
  }

  static async scheduleLocalReminder(
    id: number,
    title: string,
    body: string,
    scheduledAt: Date
  ): Promise<void> {
    await LocalNotifications.schedule({
      notifications: [
        {
          id,
          title,
          body,
          sound: 'beep.wav',
          attachments: [],
          actionTypeId: '',
          extra: null,
          schedule: { at: scheduledAt }
        }
      ]
    })
  }
}
```

##### 步骤 5：在 Store 中集成移动端通知

**文件**: `frontend/src/stores/workspace.ts`

修改现有的通知方法：

```typescript
import { MobileNotificationService } from '@/plugins/capacitor'

export const useWorkspaceStore = defineStore('workspace', () => {
  // ... existing code ...

  const showMobileNotification = async (reminder: ReminderRead) => {
    const scheduledTime = new Date(reminder.remind_at)
    
    await MobileNotificationService.scheduleLocalReminder(
      reminder.id,
      `📢 ${reminder.title}`,
      reminder.content,
      scheduledTime
    )
  }

  return {
    // ... existing exports ...
    showMobileNotification,
  }
})
```

##### 步骤 6：添加应用图标和启动屏

准备资源文件：
- `public/icons/icon-512.png` (512x512)
- `public/icons/icon-192.png` (192x192)
- `public/splashscreens/splash-2732x2732.png`

运行资源生成：
```bash
npx @capacitor/assets generate --iconSrc public/icons/icon-512.png --splashSrc public/splashscreens/splash-2732x2732.png
```

##### 步骤 7：同步代码到原生项目

每次前端构建后同步：
```bash
cd frontend
pnpm build
npx cap sync
```

##### 步骤 8：Android 构建

使用 Android Studio 打开：
```bash
npx cap open android
```

在 Android Studio 中：
1. 选择 `Build > Build Bundle(s) / APK(s) > Build APK(s)`
2. APK 输出位置：`frontend/android/app/build/outputs/apk/debug/app-debug.apk`

或使用命令行：
```bash
cd frontend/android
./gradlew assembleDebug
```

##### 步骤 9：iOS 构建

使用 Xcode 打开：
```bash
npx cap open ios
```

在 Xcode 中：
1. 选择签名团队
2. 选择目标设备（真机或模拟器）
3. 点击 `Product > Build`

##### 步骤 10：单元测试

**文件**: `frontend/tests/capacitor.test.ts`（新建）

```typescript
import { describe, it, expect, vi } from 'vitest'
import { PushNotifications } from '@capacitor/push-notifications'
import { MobileNotificationService } from '@/plugins/capacitor'

describe('Capacitor Mobile Features', () => {
  it('should register push notifications', async () => {
    const mockRegister = vi.spyOn(PushNotifications, 'register')
    await MobileNotificationService.registerPushNotifications()
    expect(mockRegister).toHaveBeenCalled()
  })

  it('should schedule local reminder', async () => {
    const futureDate = new Date(Date.now() + 60000) // 1 分钟后
    await MobileNotificationService.scheduleLocalReminder(
      1,
      'Test Reminder',
      'This is a test',
      futureDate
    )
    // Verify notification scheduled (mock test)
  })
})
```

---

## 四、P1 — 功能深化

### P1-1: 地图服务深度集成

#### 目标

集成地图服务（高德地图/Google Maps API），实现路径时间计算、POI 推荐、基于位置的智能建议。

#### 涉及文件

1. `backend/app/tools/maps.py` — 地图服务工具类（新建）
2. `backend/app/services/suggestions.py` — 增加位置相关建议逻辑
3. `backend/app/models.py` — 新增地点相关字段
4. `.env` — 地图 API Key 配置
5. `backend/requirements.txt` — 新增地图 SDK
6. `backend/tests/test_maps.py` — 单元测试

#### 详细实现步骤

##### 步骤 1：安装地图 SDK

**文件**: `backend/requirements.txt`

添加：
```
amap-sdk==2.0.0  # 高德地图 Python SDK
requests>=2.31.0
```

##### 步骤 2：配置 API Key

**文件**: `.env`

添加：
```
AMAP_API_KEY=your_amap_api_key_here
AMAP_SECRET=your_amap_secret_here
```

##### 步骤 3：实现地图服务工具类

**文件**: `backend/app/tools/maps.py`（新建）

```python
"""Map service integration for location-based features."""
from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any
from urllib.parse import urlencode

import aiohttp
from app.core.config import settings


class AMapClient:
    """高德地图 API 客户端."""

    BASE_URL = "https://restapi.amap.com/v3"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or settings.AMAP_API_KEY
        self.secret = getattr(settings, "AMAP_SECRET", None)

    def _sign(self, params: dict[str, str]) -> str:
        """生成签名（如果使用安全密钥）。"""
        if not self.secret:
            return ""
        
        timestamp = str(int(time.time()))
        params["timestamp"] = timestamp
        params["key"] = self.api_key
        
        sign_str = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        signature = hmac.new(
            self.secret.encode(),
            sign_str.encode(),
            hashlib.sha1
        ).hexdigest()
        
        return signature

    async def _request(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        """发送 HTTP 请求."""
        url = f"{self.BASE_URL}{endpoint}"
        
        if self.secret:
            params["sig"] = self._sign(params)
        else:
            params["key"] = self.api_key

        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as resp:
                resp.raise_for_status()
                return await resp.json()

    async def calculate_route_time(
        self,
        origin: tuple[float, float],
        destination: tuple[float, float],
        mode: str = "driving"
    ) -> int:
        """
        计算两点之间的路径时间（分钟）。

        Args:
            origin: 起点坐标 (latitude, longitude)
            destination: 终点坐标 (latitude, longitude)
            mode: 交通方式 (driving/walking/transit)

        Returns: 预计耗时（分钟）
        """
        params = {
            "origin": f"{origin[1]},{origin[0]}",  # 高德要求 lon,lat
            "destination": f"{destination[1]},{destination[0]}",
        }

        result = await self._request("/direction/driving", params)
        
        if result.get("status") == "1" and result.get("route", {}).get("paths"):
            duration = int(result["route"]["paths"][0]["duration"])
            return max(1, duration // 60)  # 转换为分钟，至少 1 分钟
        
        return 0

    async def search_poi(
        self,
        keyword: str,
        location: tuple[float, float] | None = None,
        radius: int = 5000
    ) -> list[dict[str, Any]]:
        """
        搜索兴趣点（POI）。

        Args:
            keyword: 搜索关键词
            location: 中心点坐标 (latitude, longitude)
            radius: 搜索半径（米）

        Returns: POI 列表
        """
        params = {
            "keywords": keyword,
            "radius": str(radius),
        }

        if location:
            params["location"] = f"{location[1]},{location[0]}"

        result = await self._request("/place/text", params)
        
        if result.get("status") == "1":
            pois = result.get("pois", [])
            return [
                {
                    "name": poi.get("name"),
                    "address": poi.get("address"),
                    "location": poi.get("location"),  # "lon,lat"
                    "distance": poi.get("distance"),
                }
                for poi in pois[:10]  # 限制返回数量
            ]
        
        return []

    async def geocode_address(self, address: str) -> tuple[float, float] | None:
        """
        地理编码：将地址转换为坐标。

        Args:
            address: 地址字符串

        Returns: (latitude, longitude) 或 None
        """
        params = {"address": address}
        result = await self._request("/geocode/geo", params)
        
        if result.get("status") == "1" and result.get("geocodes"):
            location = result["geocodes"][0]["location"]
            lon, lat = map(float, location.split(","))
            return (lat, lon)
        
        return None
```

##### 步骤 4：在建议服务中集成位置感知

**文件**: `backend/app/services/suggestions.py`

在 `_analyze_user_state()` 方法中增加位置相关逻辑：

```python
from app.tools.maps import AMapClient

class SuggestionsService:
    def __init__(self):
        self.map_client = AMapClient()

    async def _analyze_user_state(
        self,
        user_id: str,
        today_events: list[Event],
        pending_tasks: list[Task],
    ) -> dict[str, Any]:
        # ... existing analysis logic ...

        # 位置感知建议
        if user_location := await self._get_user_location(user_id):
            nearby_pois = await self.map_client.search_poi(
                keyword="咖啡厅",
                location=user_location,
                radius=2000
            )
            
            if nearby_pois and gaps:
                suggestions.append({
                    "type": "location_based_break",
                    "payload": {
                        "poi": nearby_pois[0],
                        "suggested_time": gaps[0][0].isoformat(),
                        "reason": "附近有推荐的休息场所"
                    }
                })

        return {"state_summary": state_summary, "suggestions": suggestions}
```

##### 步骤 5：在事件模型中增加位置字段

**文件**: `backend/app/models.py`

在 `Event` 模型中确认已有位置字段（如果没有则添加）：

```python
class Event(SQLModel, table=True):
    # ... existing fields ...
    
    location_name: str | None = Field(default=None, max_length=255)
    location_address: str | None = Field(default=None, max_length=500)
    location_lat: float | None = Field(default=None)
    location_lng: float | None = Field(default=None)
```

##### 步骤 6：单元测试

**文件**: `backend/tests/test_maps.py`（新建）

```python
"""Tests for map service integration."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from app.tools.maps import AMapClient


@pytest.mark.asyncio
async def test_calculate_route_time():
    client = AMapClient(api_key="test_key")
    
    with patch.object(client, '_request', new_callable=AsyncMock) as mock_request:
        mock_request.return_value = {
            "status": "1",
            "route": {
                "paths": [{"duration": "1800"}]  # 30 分钟
            }
        }
        
        duration = await client.calculate_route_time(
            origin=(39.9042, 116.4074),  # 北京
            destination=(31.2304, 121.4737),  # 上海
            mode="driving"
        )
        
        assert duration == 30


@pytest.mark.asyncio
async def test_search_poi():
    client = AMapClient(api_key="test_key")
    
    with patch.object(client, '_request', new_callable=AsyncMock) as mock_request:
        mock_request.return_value = {
            "status": "1",
            "pois": [
                {
                    "name": "星巴克",
                    "address": "某某路 1 号",
                    "location": "116.4074,39.9042",
                    "distance": "500"
                }
            ]
        }
        
        pois = await client.search_poi(
            keyword="咖啡",
            location=(39.9042, 116.4074),
            radius=1000
        )
        
        assert len(pois) == 1
        assert pois[0]["name"] == "星巴克"
```

---

## 五、P2 — 语音功能实现

### P2-1: 语音输入适配器实现

#### 目标

实现语音转文字（STT）功能，支持用户通过语音输入创建事件、任务。

#### 涉及文件

1. `backend/app/input_adapters/base.py` — 基类定义（新建）
2. `backend/app/input_adapters/whisper_adapter.py` — Whisper STT 实现
3. `backend/app/input_adapters/__init__.py` — 导出适配器
4. `backend/requirements.txt` — 新增语音识别依赖

#### 详细实现步骤

##### 步骤 1：安装语音识别依赖

**文件**: `backend/requirements.txt`

添加：
```
openai-whisper>=20231117
torch>=2.0.0
torchaudio>=2.0.0
```

##### 步骤 2：定义输入适配器基类

**文件**: `backend/app/input_adapters/base.py`（新建）

```python
"""Base class for input adapters."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class BaseInputAdapter(ABC):
    """输入适配器基类."""

    @abstractmethod
    async def process_input(self, input_data: bytes | str) -> str:
        """
        处理输入并返回文本。

        Args:
            input_data: 输入数据（音频字节或文本）

        Returns: 转换后的文本
        """
        pass
```

##### 步骤 3：实现 Whisper 语音识别适配器

**文件**: `backend/app/input_adapters/whisper_adapter.py`（新建）

```python
"""Whisper speech-to-text adapter."""
from __future__ import annotations

import io
import tempfile
from pathlib import Path

import whisper
from .base import BaseInputAdapter


class WhisperInputAdapter(BaseInputAdapter):
    """OpenAI Whisper 语音识别适配器."""

    def __init__(self, model_size: str = "base"):
        """
        初始化 Whisper 模型。

        Args:
            model_size: 模型大小 (tiny, base, small, medium, large)
        """
        self.model = whisper.load_model(model_size)

    async def process_input(self, input_data: bytes | str) -> str:
        """
        将音频转换为文本。

        Args:
            input_data: 音频文件字节流

        Returns: 识别的文本
        """
        if isinstance(input_data, str):
            # 如果已经是文本，直接返回
            return input_data

        # 将字节流保存为临时文件
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
            tmp_file.write(input_data)
            tmp_path = Path(tmp_file.name)

        try:
            # 使用 Whisper 转录
            result = self.model.transcribe(str(tmp_path), language="zh")
            return result["text"].strip()
        finally:
            # 清理临时文件
            tmp_path.unlink()
```

##### 步骤 4：注册适配器

**文件**: `backend/app/input_adapters/__init__.py`（新建）

```python
"""Input adapters for various modalities."""
from .base import BaseInputAdapter
from .whisper_adapter import WhisperInputAdapter

__all__ = [
    "BaseInputAdapter",
    "WhisperInputAdapter",
]
```

##### 步骤 5：在 API 中使用

**文件**: `backend/app/api/routes/inbox.py`

添加语音上传端点：

```python
from fastapi import UploadFile, File
from app.input_adapters import WhisperInputAdapter

# 初始化适配器
whisper_adapter = WhisperInputAdapter(model_size="base")

@router.post("/voice")
async def create_inbox_from_voice(
    audio: UploadFile = File(...),
    user_id: str = Depends(get_current_user),
):
    """从语音创建 Inbox 项."""
    audio_bytes = await audio.read()
    
    # 语音转文字
    text = await whisper_adapter.process_input(audio_bytes)
    
    # 创建 inbox 项
    inbox_item = await inbox_repository.create_inbox(
        user_id=user_id,
        content=text,
        source="voice"
    )
    
    return inbox_item
```

---

## 六、单元测试规范

所有新增功能必须配备单元测试，遵循以下规范：

### 测试文件命名

- 测试文件：`test_<feature>.py` 或 `test_<feature>.ts`
- 位置：与源码同级目录的 `tests/` 文件夹

### 测试覆盖率要求

| 模块 | 最低覆盖率 |
|------|-----------|
| Services | 80% |
| API Routes | 70% |
| Tools | 90% |
| Adapters | 85% |

### 运行测试命令

后端：
```bash
cd backend
pytest --cov=app --cov-report=html
```

前端：
```bash
cd frontend
pnpm test --coverage
```

---

## 七、整体测试验证清单

完成所有开发后，按以下清单进行整体验证：

### 功能性测试

- [ ] Tauri 桌面应用正常启动
- [ ] 桌面通知正常弹出
- [ ] Capacitor 移动端 APK/IPA 可安装
- [ ] 移动端本地通知正常
- [ ] 地图路径时间计算准确
- [ ] 天气预警正确触发
- [ ] 语音输入识别准确率 > 85%
- [ ] 语音输出播放正常
- [ ] PWA 可离线访问核心页面

### 性能测试

- [ ] 前端首屏加载 < 3 秒
- [ ] API 响应时间 P95 < 500ms
- [ ] Celery 任务延迟 < 10 秒
- [ ] Docker 镜像体积 < 500MB

### 兼容性测试

- [ ] Chrome/Edge/Safari 最新稳定版
- [ ] Windows 10/11 桌面端
- [ ] Android 10+ 移动端
- [ ] iOS 15+ 移动端

### 文档完整性

- [ ] README.md 更新部署说明
- [ ] API 文档自动生成交互正常
- [ ] 用户使用手册完成
- [ ] 开发者贡献指南完成

---

## 八、里程碑计划

| 阶段 | 时间窗口 | 交付物 | 验收标准 |
|------|----------|--------|----------|
| **Phase 1** | Week 1-2 | Tauri 桌面应用 | 可安装的 EXE/DMG 文件 |
| **Phase 2** | Week 3-4 | Capacitor 移动应用 | 可安装的 APK/IPA 文件 |
| **Phase 3** | Week 5 | 地图 + 天气集成 | 位置/天气感知建议正常 |
| **Phase 4** | Week 6 | 语音功能 | STT/TTS 端到端测试通过 |
| **Phase 5** | Week 7 | PWA + 优化 | Lighthouse 评分 > 90 |
| **Phase 6** | Week 8 | 整体验收 | 所有测试用例通过 |

---

**文档版本**: V4.0  
**最后更新**: 2026-04-01  
**维护者**: MA-IPAAS Team
