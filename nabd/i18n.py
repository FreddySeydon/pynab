from django.db import models

from nabcommon import singleton_model


class Config(singleton_model.SingletonModel):

    locale = models.TextField(default="fr_FR")
    quiet_mode = models.BooleanField(default=False)

    class Meta:
        app_label = "nabd"


async def get_locale():
    config = await Config.load_async()
    return config.locale
