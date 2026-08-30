# backend.py
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
import yt_dlp
import os
import uuid
import shutil
import time

app = FastAPI(title="Downly API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class URLRequest(BaseModel):
    url: str

class DownloadRequest(BaseModel):
    url: str
    format_id: str

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

@app.post("/api/info")
async def get_info(request: URLRequest):
    ydl_opts = {"quiet": True, "no_warnings": True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(request.url, download=False)
            formats = []
            for f in info.get("formats", []):
                if f.get("vcodec") != "none" and f.get("height"):
                    formats.append({
                        "id": f.get("format_id"),
                        "height": f.get("height"),
                        "ext": f.get("ext"),
                        "filesize": f.get("filesize"),
                        "vcodec": f.get("vcodec"),
                    })
            return {
                "title": info.get("title"),
                "thumbnail": info.get("thumbnail"),
                "channel": info.get("channel") or info.get("uploader"),
                "duration": info.get("duration"),
                "view_count": info.get("view_count"),
                "formats": formats,
            }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/download")
async def download_video(request: DownloadRequest):
    is_audio = request.format_id == "bestaudio"

    # Get a list of existing files before download to find the new one
    before_files = set(os.listdir(DOWNLOAD_DIR))

    if is_audio:
        ydl_opts = {
            "format": "bestaudio",
            "outtmpl": f"{DOWNLOAD_DIR}/%(title)s.%(ext)s",
            "quiet": True,
            "no_warnings": True,
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
        }
    else:
        ydl_opts = {
            "format": request.format_id,
            "outtmpl": f"{DOWNLOAD_DIR}/%(title)s.%(ext)s",
            "quiet": True,
            "no_warnings": True,
        }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(request.url, download=True)

        # Find the newly created file in the download directory
        after_files = set(os.listdir(DOWNLOAD_DIR))
        new_files = after_files - before_files

        # Also check if any file was replaced or renamed – we can also look for the newest file
        if not new_files:
            # Fallback: get the most recently modified file
            all_files = [os.path.join(DOWNLOAD_DIR, f) for f in os.listdir(DOWNLOAD_DIR) if os.path.isfile(os.path.join(DOWNLOAD_DIR, f))]
            if not all_files:
                raise Exception("No files found in download directory after download")
            newest = max(all_files, key=os.path.getmtime)
            original_path = newest
            original_filename = os.path.basename(original_path)
        else:
            # There might be multiple new files (e.g., temp files), pick the largest or the newest
            # We'll take the one with the most recent modification time
            new_files_full = [os.path.join(DOWNLOAD_DIR, f) for f in new_files]
            if not new_files_full:
                raise Exception("No new files found after download")
            # Sort by modification time, pick the latest
            new_files_full.sort(key=os.path.getmtime, reverse=True)
            original_path = new_files_full[0]
            original_filename = os.path.basename(original_path)

        # Rename to a unique name to avoid collisions and ensure correct extension
        unique_id = uuid.uuid4().hex[:8]
        ext = os.path.splitext(original_filename)[1]  # includes the dot
        new_filename = f"video_{unique_id}{ext}"
        new_path = os.path.join(DOWNLOAD_DIR, new_filename)
        shutil.move(original_path, new_path)

        return {
            "title": info.get("title", "Downloaded Video"),
            "download_url": f"/downloads/{new_filename}",
        }
    except Exception as e:
        import traceback
        print("=" * 60)
        print("DOWNLOAD ERROR:")
        traceback.print_exc()
        print("=" * 60)
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/downloads/{filename}")
async def serve_file(filename: str):
    file_path = os.path.join(DOWNLOAD_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="application/octet-stream",
    )