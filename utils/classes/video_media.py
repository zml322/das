"""Read-only probes and cache preparation for camera recordings.

Some field recorders write an MPEG program stream while giving the file an
``.mp4`` suffix.  Passing that suffix to the Windows Media Foundation backend
can leave :class:`QMediaPlayer` with a zero duration.  This module identifies
that case by bytes, estimates the playable time from PES timestamps, and (only
when requested) makes a *copy* with an ``.mpg`` suffix in a local cache.  It
never renames, edits, or otherwise writes to the source recording.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


MPEG_PROGRAM_STREAM_PACK = b"\x00\x00\x01\xBA"
MPEG_PROGRAM_STREAM_END = b"\x00\x00\x01\xB9"
_START_CODE = b"\x00\x00\x01"
_PTS_WRAP = 1 << 33


@dataclass(frozen=True)
class VideoProbe:
    """Facts obtained directly from a recording, without a media backend."""

    path: str
    container: str
    video_codec: str
    audio_codec: str
    duration_seconds: Optional[float]
    first_pts: Optional[int]
    last_pts: Optional[int]
    size_bytes: int
    payload_end_offset: int
    trailing_zero_bytes: int
    has_program_end_code: bool

    @property
    def is_mpeg_program_stream(self) -> bool:
        return self.container == "MPEG-PS"

    @property
    def has_fixed_size_padding(self) -> bool:
        return self.trailing_zero_bytes > 0

    @property
    def completion_state(self) -> str:
        """Conservative completion assessment; never treats padding as proof."""

        if not self.is_mpeg_program_stream:
            return "unknown"
        if self.has_program_end_code:
            return "terminated"
        if self.trailing_zero_bytes:
            return "truncated_or_unfinalized"
        return "unfinalized"


def _decode_pts(value: bytes) -> Optional[int]:
    """Decode one MPEG PES five-byte PTS field."""

    if len(value) != 5 or not (value[0] & 1 and value[2] & 1 and value[4] & 1):
        return None
    return (
        ((value[0] >> 1) & 0x07) << 30
        | (value[1] << 22)
        | ((value[2] >> 1) << 15)
        | (value[3] << 7)
        | (value[4] >> 1)
    )


def _pes_pts(buffer: bytes, offset: int) -> Optional[int]:
    """Extract PTS from a PES start code at ``offset`` if it has one."""

    # MPEG-2 PES fixed header: 00 00 01 id length(2) flags(2) hdr_len PTS...
    if offset + 14 > len(buffer) or buffer[offset + 6] & 0xC0 != 0x80:
        return None
    flags = (buffer[offset + 7] >> 6) & 0x03
    if flags not in (2, 3):
        return None
    return _decode_pts(buffer[offset + 9 : offset + 14])


def _codec_hints(payload: bytes) -> tuple[str, str]:
    """Return only unambiguous elementary-stream codec observations."""

    video = "unknown"
    audio = "unknown"
    if b"\x00\x00\x01\xB3" in payload:
        video = "MPEG-2 video"
    elif b"\x00\x00\x01\xB0" in payload:
        video = "MPEG-4 Part 2 video"
    elif b"\x00\x00\x00\x01\x67" in payload or b"\x00\x00\x01\x67" in payload:
        video = "H.264/AVC"
    if b"\x0B\x77" in payload:
        audio = "AC-3"
    return video, audio


def _last_nonzero_offset(path: Path, block_size: int = 1 << 20) -> int:
    """Return the exclusive end offset of meaningful data without loading it."""

    size = path.stat().st_size
    with path.open("rb") as stream:
        position = size
        while position:
            start = max(0, position - block_size)
            stream.seek(start)
            data = stream.read(position - start)
            index = len(data) - 1
            while index >= 0 and data[index] == 0:
                index -= 1
            if index >= 0:
                return start + index + 1
            position = start
    return 0


def _ffmpeg_stream_info(path: Path) -> tuple[Optional[float], str, str]:
    """Ask the bundled decoder for authoritative codec names when available."""
    try:
        completed = subprocess.run(
            [bundled_ffmpeg_executable(), "-hide_banner", "-i", str(path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            check=False,
        )
    except (OSError, RuntimeError, subprocess.SubprocessError):
        return None, "unknown", "unknown"
    text = completed.stderr
    duration_match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", text)
    duration = None
    if duration_match:
        hours, minutes, seconds = duration_match.groups()
        duration = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    video_match = re.search(r"Video:\s*([^,]+)", text)
    audio_match = re.search(r"Audio:\s*([^,]+)", text)
    return (
        duration,
        video_match.group(1).strip() if video_match else "unknown",
        audio_match.group(1).strip() if audio_match else "unknown",
    )


def probe_video(path: str | os.PathLike[str], chunk_size: int = 4 << 20) -> VideoProbe:
    """Probe an MPEG-PS recording using packet timestamps, not its suffix.

    The method deliberately does not guess a duration from file size.  MPEG
    timestamps are 90 kHz and wrap after about 26.5 hours; the scan tracks
    forward wraps so long recorder files retain a correct duration.
    """

    source = Path(path)
    size = source.stat().st_size
    with source.open("rb") as stream:
        head = stream.read(16)
    if not head.startswith(MPEG_PROGRAM_STREAM_PACK):
        duration, video_codec, audio_codec = _ffmpeg_stream_info(source)
        suffix = source.suffix.casefold()
        container = "MP4" if suffix in {".mp4", ".m4v", ".mov"} else "unknown"
        return VideoProbe(
            str(source), container, video_codec, audio_codec, duration,
            None, None, size, size, 0, False,
        )

    first_pts: Optional[int] = None
    last_pts: Optional[int] = None
    last_raw_pts: Optional[int] = None
    epoch = 0
    video_codec = "unknown"
    audio_codec = "unknown"
    overlap = b""
    with source.open("rb") as stream:
        while True:
            data = stream.read(max(1024, int(chunk_size)))
            if not data:
                break
            buffer = overlap + data
            cursor = 0
            while True:
                found = buffer.find(_START_CODE, cursor)
                if found < 0:
                    break
                if found + 4 > len(buffer):
                    break
                stream_id = buffer[found + 3]
                if 0xE0 <= stream_id <= 0xEF or 0xC0 <= stream_id <= 0xDF:
                    pts = _pes_pts(buffer, found)
                    if pts is not None:
                        if last_raw_pts is not None and pts < last_raw_pts and last_raw_pts - pts > _PTS_WRAP // 2:
                            epoch += _PTS_WRAP
                        extended = epoch + pts
                        if first_pts is None:
                            first_pts = extended
                        last_pts = extended
                        last_raw_pts = pts
                if 0xE0 <= stream_id <= 0xEF and video_codec == "unknown":
                    hint, _ = _codec_hints(buffer[found : min(len(buffer), found + 8192)])
                    if hint != "unknown":
                        video_codec = hint
                if audio_codec == "unknown":
                    _, hint = _codec_hints(buffer[found : min(len(buffer), found + 8192)])
                    if hint != "unknown":
                        audio_codec = hint
                    elif 0xC0 <= stream_id <= 0xDF:
                        audio_codec = "MPEG audio"
                cursor = found + 4
            # PES headers and video sequence headers can straddle a chunk.
            overlap = buffer[-8192:]

    payload_end = _last_nonzero_offset(source)
    tail_start = max(0, payload_end - 8192)
    with source.open("rb") as stream:
        stream.seek(tail_start)
        tail = stream.read(payload_end - tail_start)
    pts_duration = (last_pts - first_pts) / 90_000.0 if first_pts is not None and last_pts is not None and last_pts >= first_pts else None
    decoded_duration, decoded_video, decoded_audio = _ffmpeg_stream_info(source)
    duration = decoded_duration if decoded_duration is not None else pts_duration
    video_codec = decoded_video if decoded_video != "unknown" else video_codec
    audio_codec = decoded_audio if decoded_audio != "unknown" else audio_codec
    return VideoProbe(
        str(source), "MPEG-PS", video_codec, audio_codec, duration, first_pts,
        last_pts, size, payload_end, size - payload_end,
        MPEG_PROGRAM_STREAM_END in tail,
    )


def default_video_cache_dir() -> Path:
    """Use a local, disposable cache outside every source-video directory."""

    root = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
    return Path(root) / "DASViewer" / "video-cache"


def cached_mpeg_ps_copy(
    path: str | os.PathLike[str], cache_dir: str | os.PathLike[str] | None = None
) -> Path:
    """Copy an MPEG-PS source to a cache with a truthful ``.mpg`` extension.

    The copy uses an atomic replace in the cache and verifies byte count.  It
    intentionally performs no conversion and never opens the source for write.
    """

    source = Path(path)
    stat = source.stat()
    signature = hashlib.sha256(
        f"{source.resolve()}|{stat.st_size}|{stat.st_mtime_ns}".encode("utf-8")
    ).hexdigest()[:16]
    target_dir = Path(cache_dir) if cache_dir is not None else default_video_cache_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{source.stem}-{signature}.mpg"
    if target.is_file() and target.stat().st_size == stat.st_size:
        return target
    temporary = target.with_suffix(target.suffix + ".part")
    try:
        with source.open("rb") as reader, temporary.open("wb") as writer:
            shutil.copyfileobj(reader, writer, length=8 << 20)
            writer.flush()
            os.fsync(writer.fileno())
        if temporary.stat().st_size != stat.st_size:
            raise IOError("录像缓存复制后的字节数与只读源文件不一致")
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()
    return target


def bundled_ffmpeg_executable() -> str:
    """Return the project-bundled FFmpeg path with a clear installation error."""
    try:
        import imageio_ffmpeg
        return str(imageio_ffmpeg.get_ffmpeg_exe())
    except (ImportError, OSError, RuntimeError) as error:
        raise RuntimeError(
            "未找到内置 FFmpeg；请安装 imageio-ffmpeg 后再生成播放缓存"
        ) from error


def cached_playable_video(
    path: str | os.PathLike[str], cache_dir: str | os.PathLike[str] | None = None
) -> Path:
    """Make an H.264/AAC MP4 *only in the independent cache*.

    MPEG-PS recordings from this camera use HEVC, which the Windows media
    backend commonly cannot seek.  FFmpeg reads the source path and writes an
    atomically published cache file; the original stays read-only throughout.
    """
    source = Path(path)
    stat = source.stat()
    signature = hashlib.sha256(
        f"{source.resolve()}|{stat.st_size}|{stat.st_mtime_ns}|h264-aac-v1".encode("utf-8")
    ).hexdigest()[:16]
    target_dir = Path(cache_dir) if cache_dir is not None else default_video_cache_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{source.stem}-{signature}.mp4"
    if target.is_file() and target.stat().st_size > 0:
        return target
    temporary = target.with_suffix(".part.mp4")
    try:
        # Media Foundation is present on supported Windows machines and avoids
        # competing with the foreground DAS viewer.  Libx264 is the portable
        # deterministic fallback used by a packaged copy on other platforms.
        encoders = (
            ("h264_mf", ["-c:v", "h264_mf", "-b:v", "1200k"]),
            ("libx264", ["-c:v", "libx264", "-preset", "veryfast", "-crf", "22"]),
        )
        completed = None
        for _encoder, video_args in encoders:
            if temporary.exists():
                temporary.unlink()
            completed = subprocess.run(
                [
                    bundled_ffmpeg_executable(), "-y", "-fflags", "+genpts", "-i", str(source),
                    "-map", "0:v:0", "-map", "0:a:0?", *video_args, "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(temporary),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            if completed.returncode == 0 and temporary.is_file() and temporary.stat().st_size > 0:
                break
        if completed is None or completed.returncode != 0 or not temporary.is_file() or temporary.stat().st_size == 0:
            detail = completed.stderr.strip().splitlines()[-1] if completed and completed.stderr.strip() else "未知 FFmpeg 错误"
            raise RuntimeError(f"播放缓存转码失败：{detail}")
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()
    return target
