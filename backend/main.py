from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from contextlib import asynccontextmanager
import os
import shutil
import subprocess
import uuid
import asyncio

TEMP_DIR = "temp_files"

@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(TEMP_DIR, exist_ok=True)
    yield
    # Cleanup on shutdown
    if os.path.exists(TEMP_DIR):
        shutil.rmtree(TEMP_DIR, ignore_errors=True)

app = FastAPI(lifespan=lifespan)

# Allow frontend to communicate with backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)


def apply_watermark(input_video: str, logo: str, output_video: str, logo_type: str = "png") -> bool:
    try:
        if logo_type == "anim":
            command = [
                'ffmpeg',
                '-y',
                '-i', input_video,
                '-stream_loop', '-1',
                '-i', logo,
                '-filter_complex', '[1:v]format=rgba,colorchannelmixer=aa=1.0[wm];[wm][0:v]scale2ref[wm_scaled][base];[base][wm_scaled]overlay=0:0:shortest=1',
                '-c:v', 'libx264',
                '-preset', 'ultrafast',
                '-crf', '23',
                '-threads', '1',
                '-bufsize', '2000k',
                '-c:a', 'copy',
                output_video
            ]
        else:
            command = [
                'ffmpeg',
                '-y',
                '-i', input_video,
                '-i', logo,
                '-filter_complex', '[1:v]format=rgba,colorchannelmixer=aa=1.0[logo];[logo][0:v]scale2ref[logo_scaled][base];[base][logo_scaled]overlay=0:0',
                '-c:v', 'libx264',
                '-preset', 'ultrafast',
                '-crf', '23',
                '-threads', '1',
                '-bufsize', '2000k',
                '-c:a', 'copy',
                output_video
            ]

        result = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=600)
        return True
    except subprocess.TimeoutExpired:
        print("FFmpeg timed out after 10 minutes.")
        return False
    except subprocess.CalledProcessError as e:
        print(f"FFmpeg Error: {e.stderr.decode()}")
        return False
    except FileNotFoundError:
        print("FFmpeg not found. Please ensure it is installed.")
        return False


def cleanup_session_files(session_id: str):
    """Remove all temporary files for a given session."""
    for f in os.listdir(TEMP_DIR):
        if f.startswith(session_id):
            try:
                os.remove(os.path.join(TEMP_DIR, f))
            except OSError:
                pass


def iterfile(path: str, session_id: str):
    """Stream the output file in chunks, then clean up all session files."""
    try:
        with open(path, "rb") as f:
            while chunk := f.read(1024 * 1024):  # 1MB chunks
                yield chunk
    finally:
        cleanup_session_files(session_id)


@app.post("/watermark")
async def create_watermark(
    video: UploadFile = File(...),
    logo: UploadFile = File(...)
):
    if not video.filename or not logo.filename:
        raise HTTPException(status_code=400, detail="Video and logo files are required.")

    session_id = str(uuid.uuid4())

    # Save Video
    video_ext = os.path.splitext(video.filename)[1]
    input_video_path = os.path.join(TEMP_DIR, f"{session_id}_video{video_ext}")
    with open(input_video_path, "wb") as buffer:
        shutil.copyfileobj(video.file, buffer)

    # Save Logo
    logo_ext = os.path.splitext(logo.filename)[1].lower()
    input_logo_path = os.path.join(TEMP_DIR, f"{session_id}_logo{logo_ext}")
    with open(input_logo_path, "wb") as buffer:
        shutil.copyfileobj(logo.file, buffer)

    output_video_path = os.path.join(TEMP_DIR, f"{session_id}_output.mp4")

    is_anim = logo_ext in ['.mov', '.webm']
    logo_type = "anim" if is_anim else "png"

    # Run FFmpeg in a thread so we don't block the async event loop
    loop = asyncio.get_event_loop()
    success = await loop.run_in_executor(
        None, apply_watermark, input_video_path, input_logo_path, output_video_path, logo_type
    )

    # Clean up input files immediately
    for p in [input_video_path, input_logo_path]:
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass

    if not success or not os.path.exists(output_video_path):
        cleanup_session_files(session_id)
        raise HTTPException(status_code=500, detail="Video processing via FFmpeg failed.")

    # Stream the response back in chunks instead of loading the entire file into memory
    output_filename = f"watermarked_{video.filename}"
    if not output_filename.endswith(".mp4"):
        output_filename = os.path.splitext(output_filename)[0] + ".mp4"

    return StreamingResponse(
        iterfile(output_video_path, session_id),
        media_type="video/mp4",
        headers={
            "Content-Disposition": f'attachment; filename="{output_filename}"'
        }
    )


@app.get("/")
def read_root():
    return {"message": "Watermark API is running."}
