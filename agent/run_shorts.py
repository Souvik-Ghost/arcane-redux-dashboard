"""
run_shorts.py — Produce and upload YouTube Shorts.
Usage: python run_shorts.py [from the agent/ directory]

Topics can be customised below or passed via the dashboard.
"""
import sys
import os
from pathlib import Path

# Ensure we run from the agent directory so relative imports work
os.chdir(Path(__file__).parent)
sys.path.insert(0, str(Path(__file__).parent))
os.environ["PYTHONIOENCODING"] = "utf-8"

from agents.shorts_agent import produce_and_upload_short

SHORTS = [
    "GPS satellites lose 7 microseconds per day to time dilation — here's why that matters",
    "Einstein's relativity runs inside your smartphone right now",
    "The Hafele-Keating experiment proved time travel is real — at tiny scales",
]

print(f"\n{'='*60}")
print(f"  Arcane Redux — Shorts Production ({len(SHORTS)} videos)")
print(f"{'='*60}\n")

for i, topic in enumerate(SHORTS, 1):
    print(f"\n[Short {i}/{len(SHORTS)}] {topic}")
    try:
        video_id = produce_and_upload_short(topic=topic)
        print(f"  PUBLISHED: https://youtube.com/shorts/{video_id}")
    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback
        traceback.print_exc()

print(f"\n{'='*60}")
print(f"  All shorts done.")
print(f"{'='*60}\n")
