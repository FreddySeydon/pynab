import abc
import asyncio

from .resources import Resources


class Sound(object, metaclass=abc.ABCMeta):
    """Interface for sound"""

    async def preload(self, audio_resource):
        if audio_resource.startswith("https://") or audio_resource.startswith(
            "http://"
        ):
            return audio_resource
        file = await Resources.find("sounds", audio_resource)
        if file is not None:
            return file.as_posix()
        print(f"Warning : could not find resource {audio_resource}")
        return None

    async def play_list(self, filenames, preloaded, event=None):
        preloaded_list = []
        if preloaded:
            preloaded_list = filenames
        else:
            # Preload all in parallel to minimize SD card latency
            tasks = [self.preload(filename) for filename in filenames]
            results = await asyncio.gather(*tasks)
            preloaded_list = [f for f in results if f is not None]

        await self.start_playing_list_preloaded(preloaded_list, event)

    async def start_playing(self, audio_resource):
        preloaded = await self.preload(audio_resource)
        if preloaded is not None:
            await self.start_playing_preloaded(preloaded)

    @abc.abstractmethod
    async def start_playing_preloaded(self, filename):
        """
        Start to play a given sound.
        Stop currently playing sound if any.
        """
        raise NotImplementedError("Should have implemented")

    @abc.abstractmethod
    async def start_playing_list_preloaded(self, filenames, event=None):
        """
        Start to play a list of given sounds.
        Stop currently playing sound if any.
        """
        raise NotImplementedError("Should have implemented")

    @abc.abstractmethod
    async def wait_until_done(self, event=None):
        """
        Wait until sound has been played or event is fired.
        """
        raise NotImplementedError("Should have implemented")

    @abc.abstractmethod
    async def stop_playing(self):
        """
        Stop currently playing sound.
        """
        raise NotImplementedError("Should have implemented")

    @abc.abstractmethod
    async def start_recording(self, stream_cb):
        """
        Start recording sound.
        Invokes stream_cb repeatedly with recorded samples.
        """
        raise NotImplementedError("Should have implemented")

    @abc.abstractmethod
    async def stop_recording(self):
        """
        Stop recording sound.
        Invokes stream_cb with finalize set to true.
        """
        raise NotImplementedError("Should have implemented")
