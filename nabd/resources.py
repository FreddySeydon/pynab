import os
import random
from pathlib import Path

from nabweb import settings


class Resources(object):
    _apps_cache = None
    _find_cache = {}

    @staticmethod
    async def find(type, resources):
        """
        Find a resource from its type and its name.
        Return the first found resource, resources being delimited by
        semi-colons.
        Perform localization and random lookups with specific tag.
        Files are first searched in <app>/<type>/<locale>/ then <app>/<type>/
        Random lookup is performed when component is * or *.suffix
        """
        from .i18n import get_locale

        locale = await get_locale()
        cache_key = (type, resources, locale)
        if cache_key in Resources._find_cache:
            return Resources._find_cache[cache_key]

        for filename in resources.split(";"):
            path0 = Path(filename)
            if path0.is_absolute():
                if path0.is_file():
                    return path0  # Already found
                raise ValueError(
                    f"find_resource expects a relative path, got {filename}"
                )
            if "/" in type:
                raise ValueError(
                    f"find_resource expects a directory name for type, "
                    f"got {type}"
                )
            is_random = path0.name.startswith("*")
            if is_random:
                result = await Resources._find_random(
                    type, path0.parent.as_posix(), path0.name, locale
                )
            else:
                result = await Resources._find_file(type, filename, locale)
            if result is not None:
                Resources._find_cache[cache_key] = result
                return result
        return None

    @staticmethod
    async def _get_apps():
        if Resources._apps_cache is not None:
            return Resources._apps_cache

        basepath = Path(settings.BASE_DIR)
        apps = []
        for app in os.listdir(basepath):
            app_path = basepath.joinpath(app)
            if os.path.isdir(app_path):
                apps.append(app_path)
        Resources._apps_cache = apps
        return apps

    @staticmethod
    async def _find_file(type, filename, locale):
        apps = await Resources._get_apps()

        for app_path in apps:
            for path in [
                app_path.joinpath(type, locale, filename),
                app_path.joinpath(type, filename),
            ]:
                if path.is_file():
                    return path
        return None

    @staticmethod
    async def _find_random(type, parent, pattern, locale):
        apps = await Resources._get_apps()

        filelist = []
        for app_path in apps:
            for path in [
                app_path.joinpath(type, locale, parent),
                app_path.joinpath(type, parent),
            ]:
                if path.is_dir():
                    filelist = filelist + list(path.glob(pattern))
        if filelist != []:
            return random.choice(sorted(filelist))  # nosec B311
        return None
