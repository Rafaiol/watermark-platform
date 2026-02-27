from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import os
import shutil
import subprocess
import uuid
import asyncio
import logging
import time

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

TEMP_DIR = "temp_files"
OUTPUT_DIR = "output_files"

# Ensure directories exist before mounting StaticFiles
os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Watermark API started. Directories ready.")
    yield
    for d in [TEMP_DIR]:
        if os.path.exists(d):
            shutil.rmtree(d, ignore_errors=True)


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

# Serve output files as static files for direct download
app.mount("/downloads", StaticFiles(directory=OUTPUT_DIR), name="downloads")


def apply_watermark(input_video: str, logo: str, output_video: str, logo_type: str = "png") -> bool:
    try:
        start_time = time.time()
        logger.info(f"Starting FFmpeg: logo_type={logo_type}")
        logger.info(f"Input video: {os.path.getsize(input_video) / (1024*1024):.1f} MB")
        logger.info(f"Logo: {os.path.getsize(logo) / (1024*1024):.1f} MB")

        if logo_type == "anim":
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

        result = subprocess.run(
            command, check=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=600
        )

        elapsed = time.time() - start_time
        output_size = os.path.getsize(output_video) / (1024 * 1024)
        logger.info(f"FFmpeg completed in {elapsed:.1f}s. Output: {output_size:.1f} MB")
        return True

    except subprocess.TimeoutExpired:
        logger.error("FFmpeg timed out after 10 minutes.")
        return False
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg Error:\n{e.stderr.decode()}")
        return False
    except FileNotFoundError:
        logger.error("FFmpeg not found.")
        return False


@app.post("/watermark")
async def create_watermark(
    video: UploadFile = File(...),
    logo: UploadFile = File(...)
):
    if not video.filename or not logo.filename:
        raise HTTPException(status_code=400, detail="Video and logo files are required.")

    session_id = str(uuid.uuid4())
    logger.info(f"New request: session={session_id}, video={video.filename}, logo={logo.filename}")

    # Save Video
    video_ext = os.path.splitext(video.filename)[1]
    input_video_path = os.path.join(TEMP_DIR, f"{session_id}_video{video_ext}")
    logger.info("Saving video...")
    with open(input_video_path, "wb") as buffer:
        shutil.copyfileobj(video.file, buffer)
    logger.info(f"Video saved: {os.path.getsize(input_video_path) / (1024*1024):.1f} MB")

    # Save Logo
    logo_ext = os.path.splitext(logo.filename)[1].lower()
    input_logo_path = os.path.join(TEMP_DIR, f"{session_id}_logo{logo_ext}")
    logger.info("Saving logo...")
    with open(input_logo_path, "wb") as buffer:
        shutil.copyfileobj(logo.file, buffer)
    logger.info(f"Logo saved: {os.path.getsize(input_logo_path) / (1024*1024):.1f} MB")

    # Output goes to the output_files directory so it can be served as a static download
    output_filename = f"{session_id}_watermarked.mp4"
    output_video_path = os.path.join(OUTPUT_DIR, output_filename)

    is_anim = logo_ext in ['.mov', '.webm']
    logo_type = "anim" if is_anim else "png"

    # Run FFmpeg in a thread
    logger.info("Starting FFmpeg...")
    loop = asyncio.get_event_loop()
    success = await loop.run_in_executor(
        None, apply_watermark, input_video_path, input_logo_path, output_video_path, logo_type
    )

    # Clean up inputs
    for p in [input_video_path, input_logo_path]:
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass

    if not success or not os.path.exists(output_video_path):
        logger.error(f"Processing failed for session {session_id}")
        raise HTTPException(status_code=500, detail="FFmpeg processing failed.")

    # Return a JSON response with the download URL instead of streaming the whole file
    logger.info(f"Processing complete! Download URL: /downloads/{output_filename}")
    return {
        "success": True,
        "download_url": f"/downloads/{output_filename}",
        "filename": f"watermarked_{video.filename}",
    }


@app.get("/")
def read_root():
    return {"message": "Watermark API is running."}


@app.get("/health")
def health_check():
    try:
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, timeout=5)
        ffmpeg_ok = result.returncode == 0
    except Exception:
        ffmpeg_ok = False
    return {
        "status": "healthy" if ffmpeg_ok else "degraded",
        "ffmpeg_available": ffmpeg_ok,
    }
