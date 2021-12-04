import logging
from pathlib import Path

from tortoise import Tortoise

from mobilizon_reshare.config.publishers import publisher_names
from mobilizon_reshare.storage.query.write import update_publishers
from aerich import Command
from mobilizon_reshare.aerich_conf.database import TORTOISE_ORM

logger = logging.getLogger(__name__)


class MoReDB:
    def __init__(self, path: Path):
        self.path = path
        # TODO: Check if DB is openable/"queriable"
        self.is_init = self.path.exists() and (not self.path.is_dir())
        if not self.is_init:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    async def __implement_db_changes__(self):
        print('implementing db changes')
        command = Command(tortoise_config=TORTOISE_ORM, app='models',
                          location='./')
        await command.init()
        await command.upgrade()


    async def setup(self):
        await self.__implement_db_changes__()
        await Tortoise.init(
            db_url=f"sqlite:///{self.path}",
            modules={
                "models": [
                    "mobilizon_reshare.models.event",
                    "mobilizon_reshare.models.notification",
                    "mobilizon_reshare.models.publication",
                    "mobilizon_reshare.models.publisher",
                ]
            },
            # always store UTC time in database
            use_tz=True,
        )
        if not self.is_init:
            await Tortoise.generate_schemas()
            self.is_init = True
            logger.info(f"Successfully initialized database at {self.path}")

        await update_publishers(publisher_names)


async def tear_down():
    return await Tortoise.close_connections()
