## Instructions
1. Install & run Docker
2. `docker build -t tiktok-archiver .`
3. `docker run -d -p 8000:8000 -v $(pwd)/media:/app/media tiktok-archiver`
4. Navigate to http://localhost:8000
