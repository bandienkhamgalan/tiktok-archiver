import json
import os
import tempfile
import shutil
from datetime import datetime
from typing import Callable, Tuple, List
from yt_dlp import YoutubeDL
import time

class TiktokDownloader:
    def __init__(self, base_directory: str):
        self.__base_directory = base_directory
        self.__ytdl = YoutubeDL({
            "outtmpl": {
                "default": "[%(id)s].%(ext)s"
            }
        })
        self.__downloaded = dict()
        self.__tempdir = None

    def __enter__(self):
        self.__tempdir = tempfile.mkdtemp()
        self.__previous_cwd = os.getcwd()
        os.chdir(self.__tempdir)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if os.path.exists(self.__tempdir):
            shutil.rmtree(self.__tempdir)
        os.chdir(self.__previous_cwd)
        self.__tempdir = None

    def download_single_video(self, url: str, interaction_date: datetime, output_folder: str):
        if self.__tempdir is None:
            raise ValueError("must be used as context manager")

        dest_folder_path = os.path.join(self.__base_directory, *os.path.split(output_folder))
        if not os.path.isdir(dest_folder_path):
            os.makedirs(dest_folder_path)

        date_string = interaction_date.strftime("%Y%m%d_%H%M%S")
        dest_file_path = self.__generate_unique_dest_file_path(dest_folder_path, date_string)

        info = self.__download_video(url)
        info["url"] = url
        info["interaction_date"] = date_string
        info["interaction_timestamp"] = int(interaction_date.timestamp())
        info["file_path"] = self.__save_video(info, dest_file_path)

        with open(f"{dest_file_path}.json", "w") as file:
            json.dump(info, file, indent=True)

    @staticmethod
    def __generate_unique_dest_file_path(folder_path: str, filename: str) -> str:
        counter = 0
        while True:
            candidate = os.path.join(folder_path, filename)
            if counter > 0:
                candidate += f"_{counter}"
            if not os.path.exists(candidate + ".json"):
                return candidate
            counter += 1

    def __download_video(self, url: str) -> dict:
        """Returns (info, downloaded_path)"""
        info = self.__downloaded.get(url, None)
        if not info:
            info = self.__ytdl.extract_info(url, download=True)
            info = self.__trim_info(info)
            self.__downloaded[url] = info

        return info.copy()

    def __save_video(self, info: dict, file_path: str) -> str:
        """Returns destination path"""
        downloads = info["requested_downloads"][0]
        src = downloads["filepath"]
        _, ext = os.path.splitext(src)
        dst = file_path + ext
        shutil.copy(src, dst)
        return dst

    @staticmethod
    def __trim_info(info):
        allowed_keys = [
            "requested_downloads",
            "epoch",
            "artist",
            "upload_date",
            "duration",
            "fulltitle",
            "comment_count",
            "repost_count",
            "like_count",
            "view_count",
            "timestamp",
            "title",
            "description",
            "uploader_url",
            "track"
        ]
        return {key: value for key, value in info.items() if key in allowed_keys}

    def download_video_list(
        self,
        video_list: List[dict],
        video_list_description: str,
        folder: str,
        filter_fn: Callable[dict, bool],
        url_extractor: Callable[dict, str],
        date_string_extractor: Callable[dict, str]):
        start_time = time.time()
        total = 0
        success = 0
        for data in video_list:
            try:
                if not filter_fn(data):
                    continue
            except:
                yield (f"data: filter_fn failed unexpectedly for {data}, skipping\n\n")
                continue
    
            total += 1
    
            url = None
            try:
                url = url_extractor(data)
            except:
                yield (f"data: url_extractor failed unexpectedly for {data}, skipping\n\n")
                continue
    
            date = None
            try:
                date_string = date_string_extractor(data)
                date = datetime.strptime(date_string, "%Y-%m-%d %H:%M:%S")
            except:
                yield (f"data: date_string_extractor failed unexpectedly for {data}, skipping\n\n")
                continue
    
            try:
                self.download_single_video(url, date, folder)
                success += 1
                yield (f"data: Downloaded url=\"{url}\", date=\"{date}\" (#{total} or {total * 100.0 / len(video_list):.1f}% in {video_list_description})\n\n")
            except:
                yield (f"data: Failed to download url=\"{url}\", date=\"{date}\" (#{total} or {total * 100.0 / len(video_list):.1f}% in {video_list_description})\n\n")
    
        duration = time.time() - start_time
        yield (f"Successfully downloaded {success} out of {total} {video_list_description}. Download duration: {duration} seconds\n\n")        

    def download_chat_videos(self, recipient, messages):
        yield from self.download_video_list(
            video_list=messages,
            video_list_description=f"videos exchanged with {recipient}",
            folder=f"chats/{recipient}",
            filter_fn=lambda data: data["Content"].startswith("https://www.tiktokv.com/"),
            url_extractor=lambda data: data["Content"],
            date_string_extractor=lambda data: data["Date"])
    
    def download_favorited_videos(self, video_list):
        yield from self.download_video_list(
            video_list=video_list,
            video_list_description="favorited videos",
            folder="favorited",
            filter_fn=lambda data: True,
            url_extractor=lambda data: data["Link"],
            date_string_extractor=lambda data: data["Date"])
    
    def download_liked_videos(self, video_list):
        yield from self.download_video_list(
            video_list=video_list,
            video_list_description="liked videos",
            folder="liked",
            filter_fn=lambda data: True,
            url_extractor=lambda data: data["link"],
            date_string_extractor=lambda data: data["date"])
