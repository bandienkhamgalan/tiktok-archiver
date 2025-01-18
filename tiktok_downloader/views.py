import json
import os
from django.shortcuts import render, redirect
from django.core.files.storage import FileSystemStorage
from django.http import StreamingHttpResponse, HttpResponse
from .utils import TiktokDownloader
import shutil
from datetime import datetime
from django.conf import settings
from urllib.parse import urlparse

BASE_DOWNLOAD_DIR = settings.MEDIA_ROOT

def home_page(request):
    # Check if any chat files exist
    chats_dir = os.path.join(settings.MEDIA_ROOT, "chats")
    chat_links = []

    if os.path.exists(chats_dir):
        for filename in os.listdir(chats_dir):
            if filename.endswith(".json"):
                chat_name = filename.replace(".json", "")
                chat_links.append(chat_name)

    # Check if favorited or liked videos exist
    favorited_dir = os.path.join(settings.MEDIA_ROOT, "favorited")
    liked_dir = os.path.join(settings.MEDIA_ROOT, "liked")
    has_favorited = os.path.exists(favorited_dir) and os.listdir(favorited_dir)
    has_liked = os.path.exists(liked_dir) and os.listdir(liked_dir)

    # If no content is available, redirect to the upload page
    if not chat_links and not has_favorited and not has_liked:
        return redirect('upload_page')

    # Render the home page if content exists
    return render(request, 'home.html', {
        'chat_links': chat_links,
        'feed_links': [
            {'title': 'Favorited', 'url': '/favorites/'} if has_favorited else None,
            {'title': 'Liked', 'url': '/likes/'} if has_liked else None,
        ]
    })

def upload_page(request):
    if request.method == 'POST' and request.FILES['json_file']:
        json_file = request.FILES['json_file']
        fs = FileSystemStorage()
        filename = fs.save(json_file.name, json_file)
        uploaded_file_path = fs.path(filename)

        # Store the file path in the session to be used in the streaming view
        request.session['uploaded_file_path'] = uploaded_file_path

        # Redirect to the progress view
        return render(request, 'progress.html')  # Progress template

    return render(request, 'upload_page.html')



def progress_view(request):
    # Get the uploaded file path from the session
    uploaded_file_path = request.session.get('uploaded_file_path')
    if not uploaded_file_path:
        return HttpResponse("No file uploaded.", status=400)

    # Stream progress updates
    def stream():
        yield "data: Starting processing...\n\n"
        try:
            with open(uploaded_file_path, 'r') as file:
                data = json.load(file)

            shutil.rmtree(BASE_DOWNLOAD_DIR, ignore_errors=True)
            if not os.path.exists(BASE_DOWNLOAD_DIR):
                os.makedirs(BASE_DOWNLOAD_DIR)

            # Initialize TikTokDownloader
            with TiktokDownloader(BASE_DOWNLOAD_DIR) as downloader:
                for key, messages in data.get("Direct Messages", {}).get("Chat History", {}).get("ChatHistory", {}).items():
                    recipient = key[18:-1]
                    yield f"data: Downloading chat videos for {recipient}...\n\n"
                    yield from downloader.download_chat_videos(recipient, messages)
                    yield f"data: Finished chat videos for {recipient}.\n\n"

                    with open(os.path.join(BASE_DOWNLOAD_DIR, "chats", recipient + ".json"), "w") as file:
                        json.dump(messages, file)

                yield "data: Downloading favorited videos...\n\n"
                yield from downloader.download_favorited_videos(data.get("Activity", {}).get("Favorite Videos", {}).get("FavoriteVideoList", []))
                yield "data: Finished favorited videos.\n\n"

                yield "data: Downloading liked videos...\n\n"
                yield from downloader.download_liked_videos(data.get("Activity", {}).get("Like List", {}).get("ItemFavoriteList", []))
                yield "data: Finished liked videos.\n\n"

            yield "data: All downloads completed successfully!\n\n"
        except Exception as e:
            yield f"data: Error occurred: {str(e)}\n\n"
        finally:
            # Clean up uploaded file
            if os.path.exists(uploaded_file_path):
                os.remove(uploaded_file_path)

    return StreamingHttpResponse(stream(), content_type='text/event-stream')

def read_videos_json_folder(folder):
    videos = []
    directory = os.path.join(settings.MEDIA_ROOT, folder)

    if os.path.exists(directory):
        for filename in os.listdir(directory):
            # Process only .json files
            if filename.endswith('.json'):
                json_file_path = os.path.join(directory, filename)

                # Parse the JSON file
                with open(json_file_path, 'r') as file:
                    metadata = json.load(file)

                # Extract the corresponding .mp4 video path
                video_file_name = filename.replace('.json', '.mp4')
                video_file_path = os.path.join(settings.MEDIA_URL, folder, video_file_name)

                # Extract uploader_tag from uploader_url
                uploader_url = metadata.get('uploader_url', '')
                uploader_tag = urlparse(uploader_url).path.split('@')[-1] if '@' in urlparse(uploader_url).path else 'NULL'

                liked_timestamp = None
                if 'interaction_timestamp' in metadata:
                    liked_timestamp = datetime.fromtimestamp(metadata["interaction_timestamp"])
                elif 'like_date' in metadata:
                    liked_timestamp = datetime.strptime(metadata['like_date'], "%Y%m%d_%H%M%S")

                # Append metadata to the list
                videos.append({
                    'video_path': video_file_path,
                    'uploaded_timestamp': datetime.fromtimestamp(metadata.get('timestamp')),
                    'liked_timestamp': liked_timestamp,
                    'view_count': metadata.get('view_count'),
                    'like_count': metadata.get('like_count'),
                    'repost_count': metadata.get('repost_count'),
                    'comment_count': metadata.get('comment_count'),
                    'url': metadata.get('url'),
                    'fulltitle': metadata.get('fulltitle'),
                    'uploader_tag': f"@{uploader_tag}",
                })
    
    return videos

def feed(request, folder, title):
    videos = read_videos_json_folder(folder)
    
    # Sort videos by timestamp (most recent first)
    videos = sorted(videos, key=lambda x: x.get('video_path', 0), reverse=True)

    # Pass the video metadata to the template
    return render(request, 'feed.html', {'videos': videos, 'feed_title': title})

def favorited_page(request):
    return feed(request, "favorited", "Favorited Videos")

def liked_page(request):
    return feed(request, "liked", "Liked Videos")

def chat_page(request, recipient):
    json_path = os.path.join(settings.MEDIA_ROOT, "chats", recipient + ".json")
    if not os.path.exists(json_path):
        return render(request, 'chat.html', {'messages': [], 'recipient': recipient})

    with open(json_path, "r") as file:
        data = json.load(file)

    videos = read_videos_json_folder(f"chats/{recipient}")
    videos = { v['url']: v for v in videos }

    messages = []
    for message in data:
        result = {
            'incoming': message['From'] == recipient,
            'date': message['Date']
        }

        if message["Content"].startswith("https://www.tiktokv.com/"):
            result['video'] = videos.get(message["Content"], None)
        elif message["Content"].startswith("[") and message["Content"].endswith("]"):
            result['gif'] = message["Content"][1:-1]
        else:
            result['text'] = message["Content"]

        messages.append(result)

    return render(request, 'chat.html', {'messages': messages, 'recipient': recipient})
    