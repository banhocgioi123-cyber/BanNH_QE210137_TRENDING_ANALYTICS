"""Configuration - Load tuwf .env"""
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY')
    REGION_CODE = os.getenv('REGION_CODE', 'VN')

    @classmethod
    def validate(cls):
        if not cls.YOUTUBE_API_KEY:
            raise ValueError("YOUTUBE_API_KEY not in .env")
        print("   Config loaded")