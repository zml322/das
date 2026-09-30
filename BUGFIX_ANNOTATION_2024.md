# 打标功能Bug修复报告

## 修复日期
2024年（根据git状态显示的最近提交）

## 发现的Bug及修复

### 1. **区间标注状态未在视频切换时清除**
**严重程度：高**

**问题描述：**
- 用户开始区间标注（点击"开始区间"按钮）后，如果切换到新视频文件，区间标注的起始时间戳（`video_annotation_interval_start_ms`）不会被清除
- 导致"结束并保存"按钮保持启用状态，使用的是旧视频的时间戳
- 用户可能在新视频中点击"结束并保存"，创建错误的、使用旧视频时间戳的标注

**影响：**
- 标注数据错误，时间戳不匹配实际视频
- 可能导致数据分析错误

**修复位置：** `utils/mainwindow.py:1589`

**修复方法：**
```python
def loadVideoComparisonFile(self, path: str, update_project: bool = True):
    """Set source media and use a local truthful-suffix cache only if needed."""
    
    path = str(path)
    # 加载新视频时清除正在进行的区间标注
    self._cancelPendingIntervalAnnotation()
    # ... 其余代码
```

### 2. **DAS数据上下文切换时未清除区间标注**
**严重程度：高**

**问题描述：**
- 当DAS数据上下文失效或不匹配时（`video_annotation_context_matches = False`），区间标注状态未被清除
- 用户在有效上下文中开始区间标注，然后数据上下文变为无效，但"结束并保存"按钮仍然启用
- 可能创建无效的标注或导致程序崩溃

**修复位置：** `utils/mainwindow.py:1407-1420`

**修复方法：**
```python
def updateVideoAnnotationDataContext(self):
    """Bind an annotation project only to its matching imported DAS source."""
    
    data_group, timeline = self._videoDataContext()
    if data_group is None or timeline is None:
        self.video_annotation_context_matches = False
        # 上下文无效时清除正在进行的区间标注
        self._cancelPendingIntervalAnnotation()
        self._updateVideoControlEnabledState()
        return False
    matches = self.video_annotation_project.set_das_context(data_group, timeline)
    self.video_annotation_context_matches = bool(matches)
    if matches:
        self.video_annotation_project.reproject_video_annotations(timeline)
    else:
        # 上下文不匹配时清除正在进行的区间标注
        self._cancelPendingIntervalAnnotation()
    self._updateVideoControlEnabledState()
    return matches
```

### 3. **清除视频序列上下文时未重置区间标注**
**严重程度：中**

**问题描述：**
- `_clearVideoSequenceContext()` 函数清除视频序列相关的所有状态，但遗漏了区间标注状态
- 在长录像分析场景中切换上下文时，可能保留过时的区间标注状态

**修复位置：** `utils/mainwindow.py:1372-1387`

**修复方法：**
```python
def _clearVideoSequenceContext(self):
    """Return video comparison to the normal, full-resolution data context."""
    
    self.video_sequence_data_group = None
    self.video_sequence_timeline = None
    self.video_sequence_display_data = None
    self.video_sequence_display_stride = 1
    self.video_sequence_source_paths = []
    self.video_sequence_selected_segment_index = None
    self.video_trajectory_windows.clear()
    self.video_trajectory_pending.clear()
    self.video_trajectory_current_window = None
    # 清除正在进行的区间标注状态
    self._cancelPendingIntervalAnnotation()
    if hasattr(self, 'video_sequence_status_label'):
        self.video_sequence_status_label.setText('连续 DAS：未加载')
        self.video_sequence_status_label.setToolTip('')
```

### 4. **完成区间标注时未验证上下文有效性**
**严重程度：中**

**问题描述：**
- `finishVideoIntervalAnnotation()` 函数在保存区间标注前未验证当前DAS数据上下文是否仍然有效
- 如果用户在开始区间后，数据上下文变为无效，仍可能尝试保存标注

**修复位置：** `utils/mainwindow.py:2369-2378`

**修复方法：**
```python
def finishVideoIntervalAnnotation(self):
    if self.video_annotation_interval_start_ms is None:
        return
    # 验证上下文仍然有效
    if self._annotationTimeline() is None:
        printError('DAS 数据上下文已失效，区间标注已取消')
        self._cancelPendingIntervalAnnotation()
        return
    start = self.video_annotation_interval_start_ms
    end = self._currentVideoPosition()
    annotation = self._addVideoAnnotation(start, end)
    if annotation is not None:
        self.video_annotation_interval_start_ms = None
        self.annotation_interval_label.setText('未开始区间标注')
        self._updateVideoControlEnabledState()
```

### 5. **标注表格更新时的信号竞争条件**
**严重程度：中**

**问题描述：**
- `refreshVideoAnnotationTable()` 使用 `blockSignals(True)` 来防止触发 `itemChanged` 信号
- 但在某些情况下，Qt可能将信号排队到事件循环，导致在解除阻塞后仍触发
- 可能导致意外的标注可见性修改或递归更新

**修复位置：** `utils/mainwindow.py:2201-2242`

**修复方法：**
```python
def refreshVideoAnnotationTable(self, select_identifier=None):
    timeline = self._annotationTimeline()
    selected = self.video_annotation_selected_id if select_identifier is None else select_identifier
    # 断开信号连接以避免触发 itemChanged
    self.annotation_table.itemChanged.disconnect(self._videoAnnotationTableItemChanged)
    self.annotation_table.blockSignals(True)
    try:
        # ... 表格更新代码 ...
    finally:
        self.annotation_table.blockSignals(False)
        # 重新连接信号
        self.annotation_table.itemChanged.connect(self._videoAnnotationTableItemChanged)
    self._updateVideoControlEnabledState()
```

### 6. **新增统一的区间标注取消函数**
**改进：代码重构**

**位置：** `utils/mainwindow.py:2356`

**新增函数：**
```python
def _cancelPendingIntervalAnnotation(self):
    """清除正在进行的区间标注状态（上下文变化或用户取消时调用）"""
    if self.video_annotation_interval_start_ms is not None:
        self.video_annotation_interval_start_ms = None
        if hasattr(self, 'annotation_interval_label'):
            self.annotation_interval_label.setText('未开始区间标注')
        if hasattr(self, 'annotation_interval_finish_button'):
            self._updateVideoControlEnabledState()
```

**优势：**
- 集中处理区间标注清除逻辑
- 避免代码重复
- 确保UI状态同步更新

## 测试建议

### 测试场景1：视频切换
1. 打开视频A
2. 点击"开始区间 (I)"
3. 不点击"结束并保存"，直接加载视频B
4. **预期结果：** 区间标注状态被清除，"结束并保存"按钮禁用，标签显示"未开始区间标注"

### 测试场景2：DAS数据切换
1. 加载DAS数据和视频，完成对时
2. 点击"开始区间 (I)"
3. 切换到不同的DAS数据文件
4. **预期结果：** 区间标注状态被清除，提示上下文不匹配

### 测试场景3：上下文失效后完成区间
1. 加载DAS数据和视频，完成对时
2. 点击"开始区间 (I)"
3. 通过某种方式使上下文失效（例如卸载DAS数据）
4. 尝试点击"结束并保存 (O)"
5. **预期结果：** 显示错误提示"DAS 数据上下文已失效，区间标注已取消"，不创建标注

### 测试场景4：表格更新
1. 创建多个标注
2. 快速切换标注可见性（勾选/取消勾选"显"列）
3. 同时选择不同的标注
4. **预期结果：** 无递归更新，无意外的可见性变化

## 键盘快捷键验证

确认以下快捷键工作正常（仅在视频标注标签页激活且无文本输入框获得焦点时）：
- **T**: 标记车辆（点标注）
- **I**: 开始区间标注
- **O**: 结束并保存区间标注
- **Space**: 播放/暂停视频

## 相关文件

- `utils/mainwindow.py` - 主窗口，所有修复均在此文件
- `utils/classes/video_annotation.py` - 标注数据模型（未修改）

## 向后兼容性

所有修复均向后兼容，不影响：
- 现有标注工程文件的加载和保存
- CSV导出功能
- 轨迹关联功能
- 视频对时功能

## 编译验证

```bash
python -m py_compile utils/mainwindow.py
# 结果：通过（仅有一个不相关的警告）
```

## 后续建议

1. **添加单元测试：** 为标注功能编写自动化测试，特别是状态转换场景
2. **状态机重构：** 考虑使用显式状态机管理区间标注的状态（空闲、标注中、已完成）
3. **用户反馈增强：** 当区间标注被自动取消时，显示更明显的提示（例如状态栏消息）
4. **日志记录：** 在区间标注状态变化时记录调试日志，便于追踪问题

## 修复确认

✅ 所有标识的bug已修复  
✅ 代码语法验证通过  
✅ 添加了统一的清理函数  
✅ 增强了错误处理和验证  
✅ 向后兼容性保持完整
