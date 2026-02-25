from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import os
import shutil
import subprocess
import uuid

app = FastAPI()

# Allow frontend to communicate with backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, restrict to your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TEMP_DIR = "temp_files"
os.makedirs(TEMP_DIR, exist_ok=True)

# 1GB limit is effectively handled by server config, but FastAPI can accept large files by default using SpooledTemporaryFile

def apply_watermark(input_video: str, logo: str, output_video: str, logo_type: str = "png") -> bool:
    try:
        if logo_type == "anim":
            # FFMPEG Command for .mov or .webm
            command = [
                'ffmpeg',
                '-y',
                '-i', input_video,
                '-stream_loop', '-1',
                '-i', logo,
                '-filter_complex', '[1:v]format=rgba,colorchannelmixer=aa=1.0[wm];[wm][0:v]scale2ref[wm_scaled][base];[base][wm_scaled]overlay=0:0:shortest=1',
                '-c:v', 'libx264',
                '-preset', 'fast',
                '-threads', '1',
                '-bufsize', '2000k',
                '-c:a', 'copy',
                output_video
            ]
        else:
            # FFMPEG Command for .png
            command = [
                'ffmpeg',
                '-y',
                '-i', input_video,
                '-i', logo,
                '-filter_complex', '[1:v]format=rgba,colorchannelmixer=aa=1.0[logo];[logo][0:v]scale2ref[logo_scaled][base];[base][logo_scaled]overlay=0:0',
                '-c:v', 'libx264',
                '-preset', 'fast',
                '-threads', '1',
                '-bufsize', '2000k',
                '-c:a', 'copy',
                output_video
            ]
        
        # Run ffmpeg command
        result = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return True
    except subprocess.CalledProcessError as e:
        print(f"FFmpeg Error: {e.stderr.decode()}")
        return False
    except FileNotFoundError:
        print("FFmpeg not found. Please ensure it is installed.")
        return False

@app.post("/watermark")
async def create_watermark(
    video: UploadFile = File(...),
    logo: UploadFile = File(...)
):
    # Validate files
    if not video.filename or not logo.filename:
        raise HTTPException(status_code=400, detail="Video and logo files are required.")
        
    # Generate unique IDs for this set of files to prevent collisions
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
    
    # Process
    success = apply_watermark(input_video_path, input_logo_path, output_video_path, logo_type)
    
    # Cleanup inputs immediately to save disk space
    if os.path.exists(input_video_path):
        os.remove(input_video_path)
    if os.path.exists(input_logo_path):
        os.remove(input_logo_path)
        
    if not success or not os.path.exists(output_video_path):
        raise HTTPException(status_code=500, detail="Video processing via FFmpeg failed.")
        
    # Return the file and delete it after sending
    return FileResponse(
        path=output_video_path,
        filename=f"watermarked_{video.filename}",
        media_type="video/mp4",
        # background Task to delete file would be ideal, but for simplicity FileResponse handles standard serving.
        # We will need a cleanup cronjob or background task for the output files in a real prod app.
    )

@app.get("/")
def read_root():
    return {"message": "Watermark API is running."}
