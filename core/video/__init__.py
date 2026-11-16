# -*- coding: utf-8 -*-
"""
视频处理模块

- annotation: 视频标注项目（JSON侧载文件）
- media: 格式转换与播放准备
- trajectory: 后台轨迹分析窗口
- player: FFmpeg回退播放器
"""
from .annotation import AnnotationProject, VideoAnnotation, GEOMETRY_LABELS, VEHICLE_TYPES
from .media import cached_playable_video, probe_video, bundled_ffmpeg_executable
from .trajectory import VideoTrajectoryWindow, analyze_group_window, read_group_window
from .player import FfmpegFrameWorker

__all__ = [
    'AnnotationProject', 'VideoAnnotation', 'GEOMETRY_LABELS', 'VEHICLE_TYPES',
    'cached_playable_video', 'probe_video', 'bundled_ffmpeg_executable',
    'VideoTrajectoryWindow', 'analyze_group_window', 'read_group_window',
    'FfmpegFrameWorker'
]
