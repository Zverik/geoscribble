import asyncio
import logging
from .db import init_database, update_tasks


async def update():
    await init_database()
    await update_tasks()


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO, format='[%(levelname)s] %(message)s')
    asyncio.run(update())
