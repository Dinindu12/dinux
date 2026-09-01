from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from urllib.parse import urlparse

import yt_dlp
import os
import uuid
import glob
import shutil
import traceback


# =========================================================
# APP
# =========================================================

app = FastAPI(title="DinuVx API")


# =========================================================
# CORS
# =========================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://dinindu12.github.io",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================================================
# MODELS
# =========================================================

class URLRequest(BaseModel):
    url: str


class DownloadRequest(BaseModel):
    url: str
    format_id: str


# =========================================================
# DIRECTORIES
# =========================================================

DOWNLOAD_DIR = "/opt/dinux/downloads"

os.makedirs(DOWNLOAD_DIR, exist_ok=True)


# =========================================================
# SUPPORTED PLATFORMS
# =========================================================

SUPPORTED_DOMAINS = {
    # YouTube
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "youtu.be",
    "www.youtu.be",

    # TikTok
    "tiktok.com",
    "www.tiktok.com",
    "m.tiktok.com",
    "vm.tiktok.com",
    "vt.tiktok.com",

    # Facebook
    "facebook.com",
    "www.facebook.com",
    "m.facebook.com",
    "fb.watch",
    "www.fb.watch",
}


def validate_url(url: str) -> str:
    """
    Validate URL and allow only supported platforms.
    """

    url = url.strip()

    if not url:
        raise HTTPException(
            status_code=400,
            detail="URL is required"
        )

    if len(url) > 2048:
        raise HTTPException(
            status_code=400,
            detail="URL is too long"
        )

    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        raise HTTPException(
            status_code=400,
            detail="Only HTTP/HTTPS URLs are allowed"
        )

    hostname = (parsed.hostname or "").lower()

    if not hostname:
        raise HTTPException(
            status_code=400,
            detail="Invalid URL"
        )

    if hostname not in SUPPORTED_DOMAINS:
        raise HTTPException(
            status_code=400,
            detail=(
                "Unsupported platform. "
                "Supported platforms: YouTube, TikTok and Facebook."
            )
        )

    return url


# =========================================================
# PLATFORM DETECTION
# =========================================================

def detect_platform(url: str) -> str:
    hostname = (urlparse(url).hostname or "").lower()

    if "youtube.com" in hostname or hostname.endswith("youtu.be"):
        return "YouTube"

    if "tiktok.com" in hostname:
        return "TikTok"

    if "facebook.com" in hostname or "fb.watch" in hostname:
        return "Facebook"

    return "Unknown"


# =========================================================
# COMMON YT-DLP OPTIONS
# =========================================================

def base_ydl_options():
    return {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,

        # Prevent accidental playlist downloads.
        "extract_flat": False,

        # Use installed FFmpeg.
        "ffmpeg_location": "/usr/bin",

        # Avoid writing unnecessary metadata/files.
        "writethumbnail": False,
        "writeinfojson": False,
        "writesubtitles": False,
        "writeautomaticsub": False,
    }


# =========================================================
# API INFO
# =========================================================

@app.post("/api/info")
async def get_info(request: URLRequest):

    url = validate_url(request.url)

    platform = detect_platform(url)

    ydl_opts = base_ydl_options()

    try:

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:

            info = ydl.extract_info(
                url,
                download=False
            )

            formats = []

            for f in info.get("formats", []):

                format_id = f.get("format_id")
                height = f.get("height")
                ext = f.get("ext")
                vcodec = f.get("vcodec")
                acodec = f.get("acodec")

                if not format_id:
                    continue

                # Video formats only for the quality buttons.
                if (
                    vcodec != "none"
                    and height
                ):
                    formats.append({
                        "id": format_id,
                        "height": height,
                        "ext": ext or "mp4",
                        "filesize": f.get("filesize"),
                        "vcodec": vcodec,
                        "acodec": acodec,
                    })

            # -------------------------------------------------
            # Remove duplicate resolutions.
            # Prefer formats that have audio.
            # -------------------------------------------------

            unique_formats = {}

            for f in formats:

                height = f.get("height")

                if height is None:
                    continue

                existing = unique_formats.get(height)

                if existing is None:
                    unique_formats[height] = f
                else:
                    # Prefer a format that already contains audio.
                    if (
                        existing.get("acodec") == "none"
                        and f.get("acodec") != "none"
                    ):
                        unique_formats[height] = f

            formats = list(unique_formats.values())

            formats.sort(
                key=lambda x: x.get("height") or 0,
                reverse=True
            )

            return {
                "title": info.get(
                    "title",
                    "Video"
                ),

                "thumbnail": info.get(
                    "thumbnail"
                ),

                "channel": (
                    info.get("channel")
                    or info.get("uploader")
                    or "Unknown"
                ),

                "duration": info.get(
                    "duration"
                ),

                "view_count": info.get(
                    "view_count"
                ),

                "platform": platform,

                "formats": formats,
            }

    except HTTPException:
        raise

    except Exception as e:

        print("=" * 60)
        print("INFO ERROR")
        print(f"Platform: {platform}")
        print(f"URL: {url}")
        traceback.print_exc()
        print("=" * 60)

        raise HTTPException(
            status_code=400,
            detail=(
                "Unable to process this video. "
                "The URL may be private, unavailable, "
                "or unsupported by yt-dlp."
            )
        )


# =========================================================
# DOWNLOAD
# =========================================================

@app.post("/api/download")
async def download_video(
    request: DownloadRequest
):

    url = validate_url(request.url)

    format_id = request.format_id.strip()

    if not format_id:
        raise HTTPException(
            status_code=400,
            detail="Format is required"
        )

    platform = detect_platform(url)

    # -----------------------------------------------------
    # Security: don't allow arbitrary yt-dlp format strings.
    # -----------------------------------------------------

    if len(format_id) > 100:
        raise HTTPException(
            status_code=400,
            detail="Invalid format"
        )

    # Format IDs returned by yt-dlp are normally numeric
    # or simple strings. Allow only safe characters.
    allowed_chars = set(
        "abcdefghijklmnopqrstuvwxyz"
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "0123456789"
        "_-+."
    )

    if not all(
        char in allowed_chars
        for char in format_id
    ):
        raise HTTPException(
            status_code=400,
            detail="Invalid format ID"
        )

    # -----------------------------------------------------
    # Unique temporary filename.
    # This prevents collisions between users.
    # -----------------------------------------------------

    job_id = uuid.uuid4().hex

    output_template = (
        f"{DOWNLOAD_DIR}/"
        f"job_{job_id}.%(ext)s"
    )

    # =====================================================
    # AUDIO
    # =====================================================

    is_audio = format_id == "bestaudio"

    if is_audio:

        ydl_opts = base_ydl_options()

        ydl_opts.update({
            "format": "bestaudio/best",

            "outtmpl": output_template,

            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ],
        })

    # =====================================================
    # VIDEO
    # =====================================================

    else:

        ydl_opts = base_ydl_options()

        # Requested video + best available audio.
        #
        # If the requested format already contains audio,
        # yt-dlp can use it directly.
        #
        # Otherwise FFmpeg merges the selected video and
        # audio streams into one file.
        ydl_opts.update({
            "format": (
                f"{format_id}+bestaudio/"
                f"{format_id}"
            ),

            "outtmpl": output_template,

            "merge_output_format": "mp4",
        })

    try:

        print("=" * 60)
        print("DOWNLOAD START")
        print(f"Platform : {platform}")
        print(f"Format   : {format_id}")
        print(f"URL      : {url}")
        print("=" * 60)

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:

            info = ydl.extract_info(
                url,
                download=True
            )

        # -------------------------------------------------
        # Find files created by this job only.
        # -------------------------------------------------

        job_files = glob.glob(
            os.path.join(
                DOWNLOAD_DIR,
                f"job_{job_id}.*"
            )
        )

        # Remove temporary/sidecar files if any.
        job_files = [
            path
            for path in job_files
            if os.path.isfile(path)
        ]

        if not job_files:

            raise Exception(
                "Downloaded file not found"
            )

        # -------------------------------------------------
        # Prefer final media file.
        # -------------------------------------------------

        media_extensions = {
            ".mp4",
            ".webm",
            ".mkv",
            ".mov",
            ".m4a",
            ".mp3",
            ".aac",
            ".opus",
            ".wav",
        }

        media_files = [
            path
            for path in job_files
            if os.path.splitext(path)[1].lower()
            in media_extensions
        ]

        if not media_files:
            media_files = job_files

        # Newest file.
        media_files.sort(
            key=os.path.getmtime,
            reverse=True
        )

        original_path = media_files[0]

        # -------------------------------------------------
        # Final extension.
        # -------------------------------------------------

        ext = os.path.splitext(
            original_path
        )[1].lower()

        if not ext:
            ext = ".mp4"

        # -------------------------------------------------
        # Safe public filename.
        # -------------------------------------------------

        final_filename = (
            f"video_{uuid.uuid4().hex[:12]}"
            f"{ext}"
        )

        final_path = os.path.join(
            DOWNLOAD_DIR,
            final_filename
        )

        shutil.move(
            original_path,
            final_path
        )

        # -------------------------------------------------
        # Clean remaining files belonging to this job.
        # -------------------------------------------------

        for path in job_files:

            if (
                os.path.abspath(path)
                != os.path.abspath(final_path)
                and os.path.exists(path)
            ):
                try:
                    os.remove(path)
                except Exception:
                    pass

        print("=" * 60)
        print("DOWNLOAD COMPLETE")
        print(f"Platform : {platform}")
        print(f"File     : {final_filename}")
        print("=" * 60)

        return {
            "title": info.get(
                "title",
                "Downloaded Video"
            ),

            "filename": final_filename,

            "platform": platform,

            "download_url": (
                f"/downloads/{final_filename}"
            ),
        }

    except HTTPException:
        raise

    except Exception as e:

        print("=" * 60)
        print("DOWNLOAD ERROR")
        print(f"Platform: {platform}")
        print(f"Format: {format_id}")
        print(f"URL: {url}")
        traceback.print_exc()
        print("=" * 60)

        # Clean failed job files.
        for path in glob.glob(
            os.path.join(
                DOWNLOAD_DIR,
                f"job_{job_id}.*"
            )
        ):
            try:
                if os.path.isfile(path):
                    os.remove(path)
            except Exception:
                pass

        raise HTTPException(
            status_code=400,
            detail=(
                "Download failed. "
                "The selected quality may not be available "
                "for this video."
            )
        )


# =========================================================
# SERVE DOWNLOADED FILE
# =========================================================

@app.get("/downloads/{filename}")
async def serve_file(filename: str):

    # Security: basename prevents path traversal.
    filename = os.path.basename(filename)

    file_path = os.path.join(
        DOWNLOAD_DIR,
        filename
    )

    if not os.path.isfile(file_path):

        raise HTTPException(
            status_code=404,
            detail="File not found"
        )

    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="application/octet-stream",
    )


# =========================================================
# ROOT
# =========================================================

@app.get("/")
async def root():

    return {
        "status": "online",
        "service": "DinuVx API",
        "platforms": [
            "YouTube",
            "TikTok",
            "Facebook",
        ],
    }


# =========================================================
# HEALTH CHECK
# =========================================================

@app.get("/api/health")
async def health():

    return {
        "status": "ok"
    }
