"""
YouTube Crawler - Crawl trending + non - trending videos
"""
import json
import os
from datetime import datetime
from googleapiclient.discovery import build
from src.utils.config import Config

class YouTubeCrawler:
    def __init__(self):
        print("Initializing crawler...")
        Config.validate()
        self.youtube = build('youtube', 'v3', developerKey = Config.YOUTUBE_API_KEY )
        self.videos = []

    def get_trending(self):
        """Lay trending videos tu mostPupolar"""
        print("\n Crawling TRENDING videos...")

        next_page = None 
        for page in range(2): #2 pages = 100 videos
            request = self.youtube.videos().list(
                part='snippet,statistics,contentDetails',
                chart='mostPopular',
                regionCode=Config.REGION_CODE,
                maxResults=50,
                pageToken=next_page
            )
            response = request.execute()

            for item in response['items']:
                self.videos.append(self._parse(item, trending=1))

            next_page = response.get('nextPageToken')
            if not next_page:
                break
            print(f"   Page {page + 1} --  done")

        print(f"  GOT {len([v for v in self.videos if v['trending_observed']==1])} trending")

    def get_non_trending(self):
        """Lay non-trending videos tu search"""
        print("\n Crawling NON-TRENDING videos...")

        for query in ['random video', 'new upload', 'small channel']:
            request = self.youtube.search().list(
                part='snippet',
                q=query,
                type='video',
                maxResults=30,
                order='relevance',
                regionCode=Config.REGION_CODE
            )
            response = request.execute()

        video_ids = [item['id']['videoId'] for item in response['items']]
        if video_ids:
            details = self.youtube.videos().list(
                part='snippet,statistics,contentDetails',
                id=','.join(video_ids)
            ).execute()

            for item in details['items']:
                self.videos.append(self._parse(item, trending=0))

        print(f"  GOT {len([v for v in self.videos if v['trending_observed']==0])} non-trending") 

    def _parse(self, item, trending):
        '''Parse video data'''
        snippet = item.get('snippet', {})
        stats = item.get('statistics', {})
        published = snippet.get('publishedAt', '')

        # Extract hour form publishedAt (format: 2024-01-10T14:30:00Z)
        hour = int(published[11:13]) if len(published) > 11 else 0 

        return {
            'video_id': item['id'],
            'title': snippet.get('title', '')[:100],
            'channel_id': snippet.get('channelId', ''),
            "published_at": published,
            'upload_hour': hour,
            'is_working_hours': 9 <= hour < 17,
            'view_count': int(stats.get('viewCount', 0)),
            'like_count': int(stats.get('likeCount', 0)),
            'comment_count': int(stats.get('commentCount', 0)),
            'duration': item.get('contentDetails', {}).get('duration', ''),
            'category_id': snippet.get('categoryId', ''),
            'trending_observed': trending
        }

    def save(self):
        """Luu data vao trong file JSON"""
        print(f"\n Saving DATA...")

        os.makedirs('data/raw', exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filepath = f'data/raw/youtube_{timestamp}.json'

        data = {
            'crawl_time': datetime.now().isoformat(),
            'total': len(self.videos),
            'trending': len([v for v in self.videos if v['trending_observed']==1]),
            'non_trending': len([v for v in self.videos if v['trending_observed']==0]),
            "videos": self.videos
        }

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        size = os.path.getsize(filepath) / (1024*1024)
        print(f" SAVED: {filepath}")
        print(f" SIZE: {size:.2f} MB")
        print(f" VIDEOS: {len(self.videos)}")

    def run(self):
        '''Main CRAWL'''
        print("\n" + "="*60)
        print("  YOUTUBE CRAWLER")
        print("="*60)

        try:
            self.get_trending()
            self.get_non_trending()
            self.save()
            print("\n   DONE! \n")
        except Exception as e:
            print(f"\n  ERROR: {e}\n")

if __name__ == '__main__':
    crawler = YouTubeCrawler()
    crawler.run()

                 