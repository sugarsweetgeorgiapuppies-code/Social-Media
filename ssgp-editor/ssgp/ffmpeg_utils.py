"""Thin helpers around the system FFmpeg / FFprobe binaries."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from typing import List, Optional


class FFmpegError(RuntimeError):
    """Raised when an ffmpeg/ffprobe command fails."""


def install_hint() -> str:
    """Human-readable install instructions for the current platform."""
    import platform

    system = platform.system().lower()
    if system == "darwin":
        return "FFmpeg not found. Install it with:  brew install ffmpeg"
    if system == "linux":
        return (
            "FFmpeg not found. Install it with:\n"
            "  Debian/Ubuntu:  sudo apt-get update && sudo apt-get install -y ffmpeg\n"
            "  Fedora:         sudo dnf install -y ffmpeg\n"
            "  Arch:           sudo pacman -S ffmpeg"
        )
    if system == "windows":
        return "FFmpeg not found. Install it with:  winget install Gyan.FFmpeg  (or: choco install ffmpeg)"
    return "FFmpeg not found. See https://ffmpeg.org/download.html"


def ensure_ffmpeg() -> None:
    """Raise a helpful error if ffmpeg/ffprobe are not on PATH."""
    missing = [b for b in ("ffmpeg", "ffprobe") if shutil.which(b) is None]
    if missing:
        raise FFmpegError(install_hint())


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


@dataclass
class ProbeInfo:
    duration: float
    width: int
    height: int
    fps: float
    has_audio: bool
    video_codec: str
    audio_codec: Optional[str]
    color_space: str = ""
    color_transfer: str = ""
    color_primaries: str = ""

    @property
    def is_hdr(self) -> bool:
        """iPhone HDR (HLG / Dolby Vision) shows washed-out/grey if not tone-
        mapped to SDR. Detect it from the color metadata."""
        cs = (self.color_space or "").lower()
        trc = (self.color_transfer or "").lower()
        prm = (self.color_primaries or "").lower()
        return (cs.startswith("bt2020") or prm.startswith("bt2020")
                or trc in ("smpte2084", "arib-std-b67"))


_FILTERS_CACHE: Optional[set] = None


def has_filter(name: str) -> bool:
    """True if the local ffmpeg build provides the given filter."""
    global _FILTERS_CACHE
    if _FILTERS_CACHE is None:
        _FILTERS_CACHE = set()
        try:
            out = subprocess.run(["ffmpeg", "-hide_banner", "-filters"],
                                  capture_output=True, text=True).stdout
            for line in out.splitlines():
                parts = line.split()
                if len(parts) >= 2 and parts[0].isalpha() is False:
                    # lines look like: " ... name  V->V  desc"
                    pass
            # simpler: collect the second token of each filter line
            for line in out.splitlines():
                toks = line.strip().split()
                if len(toks) >= 3 and "->" in toks[2]:
                    _FILTERS_CACHE.add(toks[1])
        except Exception:
            _FILTERS_CACHE = set()
    return name in _FILTERS_CACHE


def hdr_quality(info: "ProbeInfo") -> str:
    """Which HDR->SDR path will run for this clip:
    ""       -> not HDR, nothing to do
    "proper" -> real tone-map (zscale/libplacebo) — picture-perfect color
    "approx" -> lean-ffmpeg fallback — de-greys it, but not a true tone-map
    """
    if not info.is_hdr:
        return ""
    if (has_filter("zscale") and has_filter("tonemap")) or has_filter("libplacebo"):
        return "proper"
    return "approx"


def hdr_to_sdr_prefilter(info: "ProbeInfo") -> str:
    """A filter-chain prefix (ending with a comma) that converts HDR footage to
    SDR BT.709 using the best filter this ffmpeg has. Empty string for SDR."""
    if not info.is_hdr:
        return ""
    if has_filter("zscale") and has_filter("tonemap"):
        # proper HDR->SDR tone-map (needs libzimg)
        return ("zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,"
                "tonemap=tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,format=yuv420p,")
    if has_filter("libplacebo"):
        return "libplacebo=colorspace=bt709:color_primaries=bt709:color_trc=bt709:range=tv,format=yuv420p,"
    # No proper tone-mapper (lean ffmpeg): do the bt2020->bt709 matrix conversion
    # and counteract the flat, washed-out "grey" look that HLG/PQ footage takes on
    # when it isn't tone-mapped — its blacks are lifted, contrast is low and colour
    # is dull. We darken slightly, add contrast and restore saturation so it reads
    # like normal SDR video. Approximate, but never errors. For picture-perfect
    # colour, install an ffmpeg that has zscale (see README).
    return ("scale=in_color_matrix=bt2020:out_color_matrix=bt709,"
            "eq=contrast=1.16:saturation=1.32:gamma=0.94:brightness=-0.02,"
            "format=yuv420p,")


# SDR BT.709 output tags — set on every encode so players never misread the file
SDR_TAGS = ["-colorspace", "bt709", "-color_primaries", "bt709",
            "-color_trc", "bt709", "-color_range", "tv"]


def probe(path: str) -> ProbeInfo:
    """Return basic media info via ffprobe."""
    cmd = [
        "ffprobe", "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", path,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise FFmpegError(f"ffprobe failed for {path}: {proc.stderr.strip()}")
    data = json.loads(proc.stdout)

    v = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    a = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)
    if v is None:
        raise FFmpegError(f"No video stream found in {path}")

    # frame rate can be "30000/1001"
    fps = 30.0
    rate = v.get("avg_frame_rate") or v.get("r_frame_rate") or "30/1"
    try:
        num, den = rate.split("/")
        fps = float(num) / float(den) if float(den) else float(num)
    except Exception:
        pass

    duration = 0.0
    for src in (v.get("duration"), data.get("format", {}).get("duration")):
        try:
            duration = float(src)
            if duration > 0:
                break
        except (TypeError, ValueError):
            continue

    return ProbeInfo(
        duration=duration,
        width=int(v.get("width", 0)),
        height=int(v.get("height", 0)),
        fps=fps or 30.0,
        has_audio=a is not None,
        video_codec=v.get("codec_name", ""),
        audio_codec=(a or {}).get("codec_name"),
        color_space=v.get("color_space", "") or "",
        color_transfer=v.get("color_transfer", "") or "",
        color_primaries=v.get("color_primaries", "") or "",
    )


def run(cmd: List[str], log_path: Optional[str] = None) -> str:
    """Run an ffmpeg command, raising FFmpegError with stderr tail on failure.

    Returns the combined stderr (ffmpeg logs progress there). If ``log_path``
    is given, the full stderr is appended to that file for debugging.
    """
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if log_path:
        try:
            with open(log_path, "a", encoding="utf-8") as fh:
                fh.write(" ".join(cmd) + "\n")
                fh.write(proc.stderr + "\n\n")
        except OSError:
            pass
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-25:])
        raise FFmpegError(f"ffmpeg failed (exit {proc.returncode}):\n{tail}")
    return proc.stderr


def hex_to_ass(color: str, alpha: float = 1.0) -> str:
    """Convert '#rrggbb' to an ASS colour '&HAABBGGRR' (note: BGR order)."""
    color = color.lstrip("#")
    if len(color) == 3:
        color = "".join(c * 2 for c in color)
    r, g, b = color[0:2], color[2:4], color[4:6]
    a = format(int(round((1.0 - alpha) * 255)), "02X")  # ASS alpha: 00=opaque, FF=transparent
    return f"&H{a}{b}{g}{r}".upper()


def hex_to_ffmpeg(color: str) -> str:
    """Convert '#rrggbb' to ffmpeg drawtext colour '0xRRGGBB'."""
    return "0x" + color.lstrip("#")
