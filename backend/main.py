from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from contextlib import asynccontextmanager
import os
import shutil
import subprocess
import uuid
import asyncio
import logging
import time

# Configure logging so Railway logs show what's happening
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

TEMP_DIR = "temp_files"

@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(TEMP_DIR, exist_ok=True)
    logger.info("Watermark API started. Temp directory ready.")
    yield
    if os.path.exists(TEMP_DIR):
        shutil.rmtree(TEMP_DIR, ignore_errors=True)

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)


def apply_watermark(input_video: str, logo: str, output_video: str, logo_type: str = "png") -> bool:
    try:
        start_time = time.time()
        logger.info(f"Starting FFmpeg processing: logo_type={logo_type}")
        logger.info(f"Input video size: {os.path.getsize(input_video) / (1024*1024):.1f} MB")
        logger.info(f"Logo size: {os.path.getsize(logo) / (1024*1024):.1f} MB")

        if logo_type == "anim":
            # Animated watermark (MOV/WEBM) — scale logo to 25% of video width for memory savings
            filter_complex = (
                "[0:v]scale=trunc(iw/2)*2:trunc(ih/2)*2[base];"
                "[1:v]format=rgba,colorchannelmixer=aa=1.0,"
                "scale=trunc(iw/4)*2:-1[wm];"
                "[base][wm]overlay=W-w-10:H-h-10:shortest=1"
            )
            command = [
                'ffmpeg', '-y',
                '-i', input_video,
                '-stream_loop', '-1',
                '-i', logo,
                '-filter_complex', filter_complex,
                '-c:v', 'libx264',
                '-preset', 'ultrafast',
                '-crf', '23',
                '-threads', '1',
                '-max_muxing_queue_size', '1024',
                '-c:a', 'copy',
                output_video
            ]
        else:
            # Static watermark (PNG) — scale logo to 25% of video width
            filter_complex = (
                "[0:v]scale=trunc(iw/2)*2:trunc(ih/2)*2[base];"
                "[1:v]format=rgba,colorchannelmixer=aa=1.0,"
                "scale=trunc(iw/4)*2:-1[logo];"
                "[base][logo]overlay=W-w-10:H-h-10"
            )
            command = [
                'ffmpeg', '-y',
                '-i', input_video,
                '-i', logo,
                '-filter_complex', filter_complex,
                '-c:v', 'libx264',
                '-preset', 'ultrafast',
                '-crf', '23',
                '-threads', '1',
                '-max_muxing_queue_size', '1024',
                '-c:a', 'copy',
                output_video
            ]

        logger.info(f"FFmpeg command: {' '.join(command)}")

        # Run FFmpeg, capture stderr for progress info, timeout after 10 minutes
        result = subprocess.run(
            command, check=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=600
        )

        elapsed = time.time() - start_time
        output_size = os.path.getsize(output_video) / (1024 * 1024)
        logger.info(f"FFmpeg completed in {elapsed:.1f}s. Output size: {output_size:.1f} MB")
        return True

    except subprocess.TimeoutExpired:
        logger.error("FFmpeg timed out after 10 minutes.")
        return False
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg Error:\n{e.stderr.decode()}")
        return False
    except FileNotFoundError:
        logger.error("FFmpeg not found. Please ensure it is installed.")
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
    logger.info(f"New watermark request: session={session_id}, video={video.filename}, logo={logo.filename}")

    # Save Video
    video_ext = os.path.splitext(video.filename)[1]
    input_video_path = os.path.join(TEMP_DIR, f"{session_id}_video{video_ext}")
    logger.info("Saving uploaded video to disk...")
    with open(input_video_path, "wb") as buffer:
        shutil.copyfileobj(video.file, buffer)
    logger.info(f"Video saved: {os.path.getsize(input_video_path) / (1024*1024):.1f} MB")

    # Save Logo
    logo_ext = os.path.splitext(logo.filename)[1].lower()
    input_logo_path = os.path.join(TEMP_DIR, f"{session_id}_logo{logo_ext}")
    logger.info("Saving uploaded logo to disk...")
    with open(input_logo_path, "wb") as buffer:
        shutil.copyfileobj(logo.file, buffer)
    logger.info(f"Logo saved: {os.path.getsize(input_logo_path) / (1024*1024):.1f} MB")

    output_video_path = os.path.join(TEMP_DIR, f"{session_id}_output.mp4")

    is_anim = logo_ext in ['.mov', '.webm']
    logo_type = "anim" if is_anim else "png"

    # Run FFmpeg in a thread so we don't block the async event loop
    logger.info("Starting FFmpeg processing in background thread...")
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
        logger.error(f"Processing failed for session {session_id}")
        raise HTTPException(status_code=500, detail="Video processing via FFmpeg failed. Check Railway logs for details.")

    output_filename = f"watermarked_{video.filename}"
    if not output_filename.endswith(".mp4"):
        output_filename = os.path.splitext(output_filename)[0] + ".mp4"

    logger.info(f"Streaming result back to client: {output_filename}")
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


@app.get("/health")
def health_check():
    """Health check endpoint to verify the server and FFmpeg are working."""
    try:
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, timeout=5)
        ffmpeg_ok = result.returncode == 0
    except Exception:
        ffmpeg_ok = False

    return {
        "status": "healthy" if ffmpeg_ok else "degraded",
        "ffmpeg_available": ffmpeg_ok,
        "temp_dir_exists": os.path.exists(TEMP_DIR),
    }
