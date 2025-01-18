## Instructions
Install Docker
docker build -t tiktok-archiver .
docker run -p 8000:8000 -v $(pwd)/media:/app/media tiktok-archiver
