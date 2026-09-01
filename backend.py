from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
import yt_dlp
import os
import uuid
import shutil

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
# DOWNLOAD DIRECTORY
# =========================================================

DOWNLOAD_DIR = "/opt/dinux/downloads"

os.makedirs(DOWNLOAD_DIR, exist_ok=True)


# =========================================================
# API INFO
# =========================================================

@app.post("/api/info")
async def get_info(request: URLRequest):

    url = request.url.strip()

    if not url:
        raise HTTPException(
            status_code=400,
            detail="URL is required"
        )

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }

    try:

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:

            info = ydl.extract_info(
                url,
                download=False
            )

            formats = []

            for f in info.get("formats", []):

                if (
                    f.get("vcodec") != "none"
                    and f.get("height")
                ):

                    formats.append({
                        "id": f.get("format_id"),
                        "height": f.get("height"),
                        "ext": f.get("ext"),
                        "filesize": f.get("filesize"),
                        "vcodec": f.get("vcodec"),
                    })

            # Remove duplicate resolutions
            unique_formats = {}

            for f in formats:

                height = f.get("height")

                if height not in unique_formats:
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
                ),

                "duration": info.get(
                    "duration"
                ),

                "view_count": info.get(
                    "view_count"
                ),

                "formats": formats,
            }

    except Exception as e:

        print("INFO ERROR:")
        print(str(e))

        raise HTTPException(
            status_code=400,
            detail=str(e)
        )


# =========================================================
# DOWNLOAD
# =========================================================

@app.post("/api/download")
async def download_video(
    request: DownloadRequest
):

    url = request.url.strip()
    format_id = request.format_id.strip()

    if not url:
        raise HTTPException(
            status_code=400,
            detail="URL is required"
        )

    if not format_id:
        raise HTTPException(
            status_code=400,
            detail="Format is required"
        )

    before_files = set(
        os.listdir(DOWNLOAD_DIR)
    )

    # -----------------------------------------------------
    # AUDIO
    # -----------------------------------------------------

    is_audio = format_id == "bestaudio"

    if is_audio:

        ydl_opts = {
            "format": "bestaudio/best",

            "outtmpl": (
                f"{DOWNLOAD_DIR}/"
                "%(title)s.%(ext)s"
            ),

            "quiet": True,

            "no_warnings": True,

            "noplaylist": True,

            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ],
        }

    # -----------------------------------------------------
    # VIDEO
    # -----------------------------------------------------

    else:

        ydl_opts = {
            "format": format_id,

            "outtmpl": (
                f"{DOWNLOAD_DIR}/"
                "%(title)s.%(ext)s"
            ),

            "quiet": True,

            "no_warnings": True,

            "noplaylist": True,
        }

    try:

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:

            info = ydl.extract_info(
                url,
                download=True
            )

        # -------------------------------------------------
        # FIND NEW FILE
        # -------------------------------------------------

        after_files = set(
            os.listdir(DOWNLOAD_DIR)
        )

        new_files = (
            after_files - before_files
        )

        original_path = None

        if new_files:

            new_files_full = []

            for filename in new_files:

                path = os.path.join(
                    DOWNLOAD_DIR,
                    filename
                )

                if os.path.isfile(path):

                    new_files_full.append(path)

            if new_files_full:

                new_files_full.sort(
                    key=os.path.getmtime,
                    reverse=True
                )

                original_path = new_files_full[0]

        # -------------------------------------------------
        # FALLBACK
        # -------------------------------------------------

        if not original_path:

            all_files = []

            for filename in os.listdir(
                DOWNLOAD_DIR
            ):

                path = os.path.join(
                    DOWNLOAD_DIR,
                    filename
                )

                if os.path.isfile(path):

                    all_files.append(path)

            if not all_files:

                raise Exception(
                    "Downloaded file not found"
                )

            all_files.sort(
                key=os.path.getmtime,
                reverse=True
            )

            original_path = all_files[0]

        # -------------------------------------------------
        # UNIQUE FILENAME
        # -------------------------------------------------

        original_filename = os.path.basename(
            original_path
        )

        ext = os.path.splitext(
            original_filename
        )[1]

        if not ext:
            ext = ".mp4"

        unique_id = uuid.uuid4().hex[:12]

        new_filename = (
            f"video_{unique_id}{ext}"
        )

        new_path = os.path.join(
            DOWNLOAD_DIR,
            new_filename
        )

        shutil.move(
            original_path,
            new_path
        )

        return {
            "title": info.get(
                "title",
                "Downloaded Video"
            ),

            "filename": new_filename,

            "download_url": (
                f"/downloads/{new_filename}"
            ),
        }

    except Exception as e:

        import traceback

        print("=" * 60)
        print("DOWNLOAD ERROR")
        traceback.print_exc()
        print("=" * 60)

        raise HTTPException(
            status_code=400,
            detail=str(e)
        )


# =========================================================
# SERVE DOWNLOADED FILE
# =========================================================

@app.get("/downloads/{filename}")
async def serve_file(filename: str):

    # Security: don't allow paths outside downloads
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
# HEALTH CHECK
# =========================================================

@app.get("/")
async def root():

    return {
        "status": "online",
        "service": "DinuVx API"
    }


@app.get("/api/health")
async def health():

    return {
        "status": "ok"
    }
