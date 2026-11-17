# 三维复刻第二轮

基准：`../image.png`。本轮继续修改真实三维模型、材质与镜头；尚未达到参考图的照片级、一比一效果。

## 查看效果

- `production-2444x1377.png`：最终生产构建，与参考图同尺寸。
- `production-1600x952.png`：最终生产构建，本机桌面客户区尺寸。
- `overview-*`、`view-1`～`view-5`：五种分辨率与五种观察机位。
- `transparency-60.png`、`fallback-no-assets.png`：透明度与素材失败时的完整回退画面。

生产截图来自实际 PySide6 桌面进程提供的本地 HTTP 服务，使用 Headless Microsoft Edge 渲染。本轮也在实际 Qt 窗口观察到三维场景正常加载；不把一次截图当作长期帧率或闪屏问题的验收。

## 相比第一轮的改进

| 项目 | 本轮改动 | 主要代码（相对 frontend/src/three） |
|---|---|---|
| 车辆 | 许可明确的独立轿车、货车、公交 GLB；合并同材质网格、减面；修正车头轴向、落地高度、白色车漆；保留源材质法线/粗糙度等数据贴图 | `engineering/VehicleAssets.ts` |
| 交互 | 替换车辆的显示子节点，保留原有可点击根对象、类型、颜色和分组；不同车辆车漆独立 | `engineering/VehicleAssets.ts` |
| 土体 | 分层表面凹凸与实例化立体土块；约束土块不穿入管道；装饰土块不参与昂贵射线检测 | `engineering/GeologyBuilder.ts`、`StrataDetails.ts` |
| 垫层 | 抬高碎石与管底接触面，变化石块尺寸、密度和颜色，补充前景石块 | `engineering/RockBedBuilder.ts` |
| 金属与水流 | 代码生成线性空间的拉丝粗糙度；细分水面，使用随统一时钟移动的多尺度噪声波纹 | `engineering/MetalSurface.ts`、`SewerBuilder.ts`、`hero/HeroSewer.ts` |
| 路面 | 局部湿润平面反射、柔化采样与边缘渐隐；静止镜头复用缓存；图层变化后更新；环境反射开关同步控制；卸载释放反射目标 | `engineering/RoadReflection.ts`、`core/SceneManager.ts` |
| 树木 | 同一 GLB 中保留 51,272 / 6,315 三角形两级模型，共享纹理；按空间分组，结合视锥剔除与距离切换 | `engineering/SceneRealism.ts`、`TreeFoliage.ts` |
| 构图 | 调整五种镜头，放大车辆和管道的视觉占比；监测箱移开前景车身；玻璃楼外观和云层边缘修正 | `hero/HeroCameraController.ts`、`engineering/MonitoringHardware.ts`、`CityBuilder.ts`、`SceneLighting.ts` |
| 光纤 | 三条主要光纤保持红/蓝/绿；第四条埋地光纤降低线径与亮度，仍显示其告警状态 | `hero/HeroFibers.ts` |

车辆素材来源、原始与处理后的哈希、许可和处理方式保留在 `frontend/public/assets/realism/ATTRIBUTION.md` 与 `vehicles/SOURCE.json`。运行时没有外部素材服务器请求。

## 尺度与业务数据

工程数据仍覆盖 910 米，首页源区段仍为 K0+300～K0+400 的 100 米。展示纵向压缩为 0.6 倍、地下深度放大 1.8 倍、管道径向放大 1.35 倍，车辆另作展示放大。道路外廓仍宽 40 米，中央带展示为 3 米，车道等量扩宽。

这些调整只用于展示。光纤、设备、事件继续使用共同坐标变换；管道和光纤长度元数据保持原始米制。原始里程、设备数、光纤总长、事件等级和统计值没有为了贴合参考图而改写。四辆场景车辆仍是展示模型，没有接入真实车辆轨迹。

## 验证

- `npm run build:check`、`npm run test:scene`、`npm run test:charts` 通过。
- 新增 `tests/vehicle-assets.mjs`：校验实际 GLB 哈希、模型落地、公交与轿车不同的车头轴向、根对象复用、独立车漆、灰色源贴图不覆盖白漆、关闭昂贵折射、树木 LOD、反射失效标记。该测试只验证几何与材质元数据；嵌入图片解码由浏览器验证。
- 桌面桥接与本地 HTTP 服务两项测试通过。
- 五种分辨率、五种机位下标注无重叠、无越界；六项图层、透明度、水流暂停恢复、旋转与重置可用。
- 实际车辆资源替换、反射开关、路由卸载重建、所有写实资源失败时的回退通过。浏览器没有页面异常、着色器控制台错误或 Three.js 警告。
- 18 个原有来源文件 MD5、三辆车辆 GLB 和两级树木 GLB 的 SHA-256 校验通过。
- 默认视角约 106～111 万个提交三角形、约 481～488 次绘制调用；上一轮约 271 万个三角形、713 次绘制调用。不同机位和 LOD 切换会改变计数。
- 1920 × 1080 Headless Edge、Intel Arc 130T、桌面程序同时运行时的两秒采样约 28 FPS，静止期间没有重复捕获反射。短采样不能作为长期稳定帧率保证。
- 生产构建成功，仍有首页 Three.js 分包大于 500 kB 的体积提示。

报告：`scene-report.json`、`production-report.json`、`performance-report.json`。

## 仍需提高

公交外形仍偏方正；建筑与树冠排布仍有规律性；土体的破碎结构、车辆表面细节、光照和接触阴影与参考图仍有差距。当前实现保留了真实三维交互，但不能宣称一比一或离线渲染级复刻完成。横/纵断面按钮仍是观察机位，没有新增可移动工程切割面。
