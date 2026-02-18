# File Server

A simple FastAPI-based file server that allows downloading files by their hash codes. The server is fully dockerized and supports mounting external file directories.

## Features

- Download files by hash code (filename)
- List all available files
- Health check endpoint
- Dockerized for easy deployment
- Security: Protection against directory traversal attacks
- Read-only file access

## Project Structure

```
fileserver/
├── main.py              # FastAPI application
├── requirements.txt     # Python dependencies
├── Dockerfile          # Docker image configuration
├── docker-compose.yml  # Docker Compose configuration
├── .dockerignore       # Docker ignore file
└── README.md           # This file
```

## API Endpoints

### GET /
Root endpoint with API information

### GET /health
Health check endpoint

### GET /download/{hash_code}
Download a file by its hash code (filename)

**Example:**
```bash
curl -O http://localhost:8000/download/abc123def456
```

### GET /list
List all available files in the directory

**Example:**
```bash
curl http://localhost:8000/list
```

## Setup & Usage

### Prerequisites

- Docker
- Docker Compose

### Method 1: Using Docker Compose (Recommended)

1. Create a directory for your files (if not already exists):
```bash
mkdir files
```

2. Place your files in the `files` directory with hash codes as filenames

3. Edit `docker-compose.yml` to point to your files directory:
```yaml
volumes:
  - ./files:/app/files:ro  # Change ./files to your directory path
```

4. Build and run:
```bash
docker-compose up -d
```

5. The server will be available at `http://localhost:8000`

6. To stop the server:
```bash
docker-compose down
```

### Method 2: Using Docker directly

1. Build the Docker image:
```bash
docker build -t fileserver .
```

2. Run the container with volume mount:
```bash
docker run -d -p 8000:8000 -v /path/to/your/files:/app/files:ro --name fileserver fileserver
```

Replace `/path/to/your/files` with the absolute path to your files directory.

### Method 3: Running locally (without Docker)

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set the files directory (optional):
```bash
export FILES_DIR=/path/to/your/files
```

3. Run the server:
```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

## Configuration

### Environment Variables

- `FILES_DIR`: Path to the directory containing files (default: `/app/files`)

### Port Configuration

The default port is `8000`. To change it:

**Docker Compose:** Edit the `ports` section in `docker-compose.yml`:
```yaml
ports:
  - "9000:8000"  # Maps host port 9000 to container port 8000
```

**Docker:** Use the `-p` flag:
```bash
docker run -d -p 9000:8000 -v /path/to/files:/app/files:ro fileserver
```

## Usage Examples

### Download a file
```bash
curl -O http://localhost:8000/download/abc123def456
```

### Download with custom filename
```bash
curl -o myfile.pdf http://localhost:8000/download/abc123def456
```

### List available files
```bash
curl http://localhost:8000/list
```

### Using wget
```bash
wget http://localhost:8000/download/abc123def456
```

### Using Python
```python
import requests

response = requests.get('http://localhost:8000/download/abc123def456')
with open('downloaded_file', 'wb') as f:
    f.write(response.content)
```

## Security Features

- Directory traversal attack prevention
- Read-only file access
- File existence validation
- File type validation (ensures it's a file, not a directory)

## Monitoring

### Check server health
```bash
curl http://localhost:8000/health
```

### View logs
```bash
docker-compose logs -f
```

Or for Docker:
```bash
docker logs -f fileserver
```

## Troubleshooting

### File not found (404)
- Ensure the file exists in the mounted directory
- Check that the hash code (filename) is correct
- Verify the volume mount path in docker-compose.yml

### Permission denied
- Ensure the Docker container has read permissions for the files directory
- On Linux/Mac, you may need to adjust permissions: `chmod -R 755 files/`

### Port already in use
- Change the host port in docker-compose.yml or Docker run command
- Check what's using the port: `netstat -tuln | grep 8000`

## Development

To run in development mode with auto-reload:

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## License

This project is provided as-is for your use.
