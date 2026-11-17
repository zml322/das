# 光纤全场景三维智能监测平台

PySide6 桌面外壳 + Vue3 / TypeScript 页面 + Three.js 工程场景。当前使用模拟数据；保留道路、分层土体、排污管道、光纤和监测点模型及动画状态控制。

## 安装与启动

需要 Python 3.11+、Node.js 18+，在正确的 Python 虚拟环境中执行：

```powershell
.\install.bat     # 安装依赖、检查类型并构建前端
.\start.bat       # 加载本地构建，启动桌面程序
```

开发时，在一个终端执行 `cd frontend; npm run dev`，另一个终端运行 `start_dev.bat`。开发端口为 5173；正常启动使用本机临时端口，无需 Vite。

## 目录与阅读顺序

```text
FiberMonitoring/
├─ desktop/                  # 桌面窗口、WebChannel、本地页面服务
│  └─ tests/                 # 桥接和本地 HTTP 服务测试
├─ frontend/
│  ├─ src/
│  │  ├─ views/              # 首页、事件、历史、配置路由页面
│  │  ├─ components/dashboard/ # 首页独立组件
│  │  ├─ composables/        # 场景生命周期、监测数据刷新、窗口动作
│  │  ├─ stores/             # 页面共享的监测状态
│  │  ├─ services/           # 数据源接口与模拟实现
│  │  ├─ three/
│  │  │  ├─ core/            # 场景组装、渲染与业务状态同步
│  │  │  ├─ engineering/     # 工程尺寸、环境、材质和细节模型
│  │  │  ├─ hero/            # 首页100米剖切模型、背景和GSAP视角系统
│  │  │  ├─ models/          # 道路、光纤、管道基础实体
│  │  │  └─ effects/         # 统一时钟、路径流光与标记
│  │  ├─ types/              # 共用业务类型与枚举
│  │  └─ assets/styles/      # 全局样式及按区域拆分的首页样式
│  ├─ public/assets/realism/  # 本地 PBR、树木/车辆模型、HDR、许可与校验清单
│  ├─ tests/                 # 几何、动画和渲染策略回归测试
│  └─ dist/                  # 构建生成；桌面运行时使用，不提交
├─ reference/                # 用户提供的设计参考图
├─ install.bat
├─ start.bat
└─ start_dev.bat
```

阅读入口：`desktop/main.py` → `main_window.py` → `webview.py`；前端从 `src/main.ts` → `router/index.ts` → `views/DashboardView.vue` 开始。场景由 `useMonitoringScene.ts` 管生命周期，`SceneBuilder.ts` 组装模型，`SceneManager.ts` 管渲染。

## 工程与渲染约定

- 工程数据仍覆盖 910 米；首页通过 `three/hero/config.ts` 聚焦 K0+300～K0+400 的100米区段。宽40米，横向为4+12+8+12+4米，土层总深10米。
- X为纵向、Y为高程、Z为横向。原始区段长度仍为100米；展示纵向压缩为0.6倍，地下深度放大1.8倍，管道截面放大1.35倍，车辆另作展示放大。道路外廓仍宽40米，展示中央带收窄为3米，车道等量扩宽。配置集中在 `three/engineering/layout.ts`、`HeroSceneBuilder.ts`。设备、事件和光纤使用同一坐标变换；图形尺寸不能直接用于现场测量。
- 实体光纤与流光共用曲线；设备和事件使用同一坐标变换。所有动画由场景统一时钟驱动，支持暂停、复位及分项开关。
- 场景分为envGroup、heroRoadGroup、geologyGroup、sewerGroup、fiberGroup、vehicleGroup、markerGroup、effectGroup；保留原图层键的兼容映射。
- 默认斜俯视，支持俯视、地下、横断面和纵断面。`HeroCameraController.ts` 使用GSAP平滑过渡，连续切换或鼠标操作会中断旧过渡，卸载会释放动画。
- 区段外事件保留在业务列表，不投影到Hero边界；点击时提示不在当前范围。`HeroEnvironment.ts` 提供连续道路、双排行道树、城市天际线和完整地面背景。
- 管道具有真实开口、内壁、检修观察窗、五组金属接头和80枚螺栓；金属使用拉丝粗糙度贴图，水面由统一动画时钟驱动。土层使用颜色、法线和粗糙度贴图，并增加实例化立体土块、砂石。标注有引线、边界约束和碰撞避让。
- 桌面使用不透明画布、尺寸去重和按需阴影；默认加载生产构建，避免开发热更新影响演示。
- 写实资源来自 Poly Haven、Innerscene，许可与校验和保留在素材目录。树木分为近/远两级，并按空间分组实例化；车辆模型合并、减面后复用几何，保留独立车漆。路面增加带边缘渐隐的局部平面反射，静止镜头复用反射缓存，图层变化后重新捕获。运行时不访问外部素材服务器；加载失败时保留程序化备用模型，卸载时释放材质、几何和反射目标。
- 事件、历史和配置页仍含演示内容，尚未连接实际设备或持久化服务。

## 检查

最新三维效果与验收记录：`reference/scene-review-v2/README.md`；同尺寸生产预览：`reference/scene-review-v2/production-2444x1377.png`。

```powershell
cd frontend
npm run build:check
npm run test:scene
npm run test:charts
cd ../desktop
python tests/bridge_smoke.py
python -m unittest discover -s tests -p test_frontend_server.py
```

`node_modules`、`dist`、Python 缓存和日志属于生成内容，已在本目录 `.gitignore` 中排除。保留 `package-lock.json` 以复现依赖版本。

本轮清理删除了旧面板、未接入的构建器和加载器、旧车辆实现、未调用的演示 API、重复文档及失效启动器；所有现用路由、场景分组、测试、参考图和素材许可均保留。
