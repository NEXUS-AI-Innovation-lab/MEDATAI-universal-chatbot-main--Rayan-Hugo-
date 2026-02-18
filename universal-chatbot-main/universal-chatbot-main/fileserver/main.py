from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
import os
import hashlib
from pathlib import Path
from typing import Optional

app = FastAPI(title="File Server", description="Download and upload files by hash code")

# Directory for existing files (PDFs, etc.) - can be read-only
FILES_DIR = os.getenv("FILES_DIR", "/app/files")

# Directory for uploads (QCM JSONs, etc.) - must be writable
UPLOADS_DIR = os.getenv("UPLOADS_DIR", "/app/uploads")

# Ensure uploads directory exists
Path(UPLOADS_DIR).mkdir(parents=True, exist_ok=True)


@app.get("/")
async def root():
    return {
        "message": "File Server API",
        "usage": "GET /download/{hash_code} to download a file"
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


@app.get("/download/{hash_code}")
async def download_file(hash_code: str):
    """
    Download a file by its hash code (extension auto-detected).
    Searches in both FILES_DIR (existing files) and UPLOADS_DIR (uploaded files).
    """

    # Sanitize
    hash_code = os.path.basename(hash_code)

    # Look in both directories
    matching_files = []

    # First check uploads directory (for QCM JSONs etc.)
    uploads_path = Path(UPLOADS_DIR)
    if uploads_path.exists():
        matching_files.extend(list(uploads_path.glob(f"{hash_code}.*")))

    # Then check files directory (for existing PDFs etc.)
    if not matching_files:
        files_path = Path(FILES_DIR)
        if files_path.exists():
            matching_files.extend(list(files_path.glob(f"{hash_code}.*")))

    if not matching_files:
        raise HTTPException(
            status_code=404,
            detail=f"No file found for hash '{hash_code}' (searched in uploads and files)"
        )

    # If multiple results, choose the first one
    file_path = matching_files[0]

    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
        media_type="application/octet-stream"
    )


@app.get("/list")
async def list_files():
    """
    List all available files in the directory.

    Returns:
        List of file hashes (filenames)
    """
    try:
        files_path = Path(FILES_DIR)
        if not files_path.exists():
            return {"files": [], "message": "Files directory does not exist"}

        files = [f.name for f in files_path.iterdir() if f.is_file()]
        return {
            "files": files,
            "count": len(files),
            "directory": FILES_DIR
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    custom_hash: Optional[str] = Form(None),
    extension: Optional[str] = Form(None)
):
    """
    Upload a file and get back its hash code for download.

    The file will be saved with a hash-based name (auto-generated or custom).
    Use the returned hash_code to download the file via /download/{hash_code}.

    Args:
        file: The file to upload
        custom_hash: Optional custom hash code to use instead of auto-generated
        extension: Optional file extension (defaults to original file extension)

    Returns:
        hash_code: The hash to use for downloading
        filename: Original filename
        download_url: URL path to download the file
    """
    try:
        # Read file contents
        contents = await file.read()

        # Generate hash or use custom
        if custom_hash:
            hash_code = os.path.basename(custom_hash)  # Sanitize
        else:
            # Auto-generate hash from content
            hash_code = hashlib.sha256(contents).hexdigest()[:16]

        # Determine file extension
        if extension:
            file_ext = extension if extension.startswith('.') else f".{extension}"
        else:
            # Use original file extension
            original_ext = Path(file.filename).suffix if file.filename else ""
            file_ext = original_ext if original_ext else ".bin"

        # Save to uploads directory (writable)
        uploads_path = Path(UPLOADS_DIR)
        uploads_path.mkdir(parents=True, exist_ok=True)

        # Save file
        file_path = uploads_path / f"{hash_code}{file_ext}"

        with open(file_path, "wb") as f:
            f.write(contents)

        return {
            "hash_code": hash_code,
            "filename": file.filename,
            "saved_as": file_path.name,
            "size": len(contents),
            "download_url": f"/download/{hash_code}"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/upload/json")
async def upload_json(
    data: dict,
    custom_hash: Optional[str] = None
):
    """
    Upload JSON data directly and get back its hash code for download.

    This is a convenience endpoint for uploading JSON without needing
    to create a file first. Useful for the RAG server to upload generated QCM.

    Args:
        data: JSON data to upload
        custom_hash: Optional custom hash code

    Returns:
        hash_code: The hash to use for downloading
        download_url: URL path to download the file
    """
    import json as json_module

    try:
        # Convert to JSON string
        json_content = json_module.dumps(data, ensure_ascii=False, indent=2)
        contents = json_content.encode('utf-8')

        # Generate hash or use custom
        if custom_hash:
            hash_code = os.path.basename(custom_hash)
        else:
            hash_code = hashlib.sha256(contents).hexdigest()[:16]

        # Save to uploads directory (writable)
        uploads_path = Path(UPLOADS_DIR)
        uploads_path.mkdir(parents=True, exist_ok=True)

        # Save file
        file_path = uploads_path / f"{hash_code}.json"

        with open(file_path, "wb") as f:
            f.write(contents)

        return {
            "hash_code": hash_code,
            "saved_as": file_path.name,
            "size": len(contents),
            "download_url": f"/download/{hash_code}"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
