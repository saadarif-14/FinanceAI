import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

_URL = os.getenv("SUPABASE_URL")
_KEY = os.getenv("SUPABASE_SERVICE_KEY")


def get_db() -> Client:
    # New client per request — avoids stale HTTP/2 connections being reused
    # after Supabase closes them on the server side (RemoteProtocolError).
    return create_client(_URL, _KEY)
