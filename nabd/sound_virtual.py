import asyncio
import time
import wave
from concurrent.futures import ThreadPoolExecutor

from mpg123 import Mpg123  # type: ignore

from .cancel import wait_with_cancel_event
from .sound import Sound


class SoundVirtual(Sound):
    def __init__(self, nabio_virtual):
        super().__init__()
        self.nabio_virtual = nabio_virtual
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.future = None
        self.currently_playing = False

    def _play(self, filename):
        try:
            if filename.endswith(".wav"):
                with wave.open(filename, "rb") as f:
                    rate = f.getframerate()
                    frames = f.getnframes()
                    duration = frames / float(rate)
                    time.sleep(duration)
            elif filename.endswith(".mp3"):
                mp3 = Mpg123(filename)
                rate, channels, encoding = mp3.get_format()
                frames = mp3.length()
                duration = frames / float(rate)
                time.sleep(duration)
        finally:
            self.currently_playing = False
            self.nabio_virtual.update_rabbit()

    async def start_playing_preloaded(self, filename):
        await self.stop_playing()
        self.currently_playing = True
        self.sound_file = filename
        self.nabio_virtual.update_rabbit()
        self.future = asyncio.get_event_loop().run_in_executor(
            self.executor, lambda f=filename: self._play(f)
        )

    async def stop_playing(self):
        if self.currently_playing:
            self.currently_playing = False
        if self.future:
            try:
                await self.future
            except Exception:
                pass
            self.future = None

    async def wait_until_done(self, event=None):
        if self.future:
            if event:
                event_wait_task = asyncio.create_task(event.wait())
                done, pending = await asyncio.wait(
                    {event_wait_task, self.future},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if self.future in pending:
                    await self.stop_playing()
                else:
                    event_wait_task.cancel()
            else:
                try:
                    await self.future
                except Exception:
                    pass
            self.future = None

    async def start_recording(self, stream_cb):
        raise NotImplementedError("Should have implemented")

    async def stop_recording(self):
        raise NotImplementedError("Should have implemented")
