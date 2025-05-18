"""
rate_limit.py
Simple token-bucket limiter: 20 messages / 30 seconds (Twitch default)
"""

import time, asyncio

class Limiter:
    def __init__(self, burst: int = 20, window: int = 30):
        self.burst = burst
        self.window = window
        self.timestamps: list[float] = []

    async def wait(self):
        now = time.time()
        # prune old stamps
        self.timestamps = [t for t in self.timestamps if now - t < self.window]
        if len(self.timestamps) >= self.burst:
            await asyncio.sleep(self.window - (now - self.timestamps[0]))
        self.timestamps.append(time.time())
