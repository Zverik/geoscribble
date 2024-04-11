import asyncio
import os
import json
from datetime import timedelta
from contextlib import asynccontextmanager
from psycopg_pool import AsyncConnectionPool
from psycopg.rows import dict_row
from typing import Union, Optional
from . import config
from .models import Scribble, Label, NewLabel, NewScribble, Deletion, Box


pool = AsyncConnectionPool(
    kwargs={
        'host': config.PG_HOST,
        'port': config.PG_PORT,
        'dbname': config.PG_DATABASE,
        'user': config.PG_USER,
        'row_factory': dict_row,
    },
    open=False,
)


async def check_connections():
    while True:
        await asyncio.sleep(600)
        await pool.check()


@asynccontextmanager
async def get_cursor(commit: bool = False):
    async with pool.connection() as conn:
        cursor = conn.cursor()
        try:
            yield cursor
            if commit:
                await conn.commit()
        finally:
            await cursor.close()


async def create_table():
    async with get_cursor(True) as cur:
        await cur.execute(
            "select 1 from pg_tables where schemaname='public' and tablename='scribbles'")
        if not await cur.fetchone():
            # Table is missing, run the script
            filename = os.path.join(os.path.dirname(__file__), 'v1_init_tables.sql')
            with open(filename, 'r') as f:
                sql = f.read()
            await cur.execute(sql)


async def init_database():
    await pool.open()
    asyncio.create_task(check_connections())
    await create_table()


def bbox_too_big(box: list[float]) -> bool:
    if (abs(box[2] - box[0]) > config.MAX_COORD_SPAN or
            abs(box[3] - box[1]) > config.MAX_COORD_SPAN):
        return True
    return False


def geohash_digits(box: list[float]) -> int:
    # area in square degrees.
    area = abs(box[2] - box[0]) * abs(box[3] - box[1])
    if area > 1000:
        return 2
    if area > 100:
        return 4
    if area > 10:
        return 5
    return 6


async def query(bbox: list[float], username: Optional[str] = None,
                user_id: Optional[int] = None,
                editor: Optional[str] = None,
                maxage: Optional[int] = None
                ) -> list[Union[Scribble, Label, Box]]:
    age = maxage or config.DEFAULT_AGE
    result: list[Union[Scribble, Label]] = []
    async with get_cursor() as cur:
        params = [*bbox, timedelta(days=age)]
        add_queries = []

        if username:
            add_queries.append('and username = %s')
            params.append(username)
        if user_id:
            add_queries.append('and user_id = %s')
            params.append(user_id)
        if editor:
            add_queries.append('and editor = %s')
            params.append(editor)

        overview = bbox_too_big(bbox)
        if not overview:
            sql = """select *, ST_AsGeoJSON(geom) json from scribbles
            where ST_Intersects(geom, ST_MakeEnvelope(%s, %s, %s, %s, 4326))
            and created >= now() - %s and deleted is null
            {q}""".format(q=' '.join(add_queries))
        else:
            params.insert(0, geohash_digits(bbox))
            sql = """with t as (
            select ST_GeoHash(geom, %s) hash, min(now()-created) age
            from scribbles
            where geom && ST_MakeEnvelope(%s, %s, %s, %s, 4326)
            and created >= now() - %s and deleted is null
            {q} group by 1)
            select ST_AsGeoJSON(ST_GeomFromGeoHash(hash)) json,
            extract(day from age) age from t
            """.format(q=' '.join(add_queries))

        await cur.execute(sql, params)

        async for row in cur:
            geom = json.loads(row['json'])
            if overview:
                c = geom['coordinates'][0]
                result.append(Box(
                    minage=row['age'],
                    box=[c[0][0], c[0][1], c[2][0], c[2][1]],
                ))
            elif geom['type'] == 'Point':
                result.append(Label(
                    id=row['scribble_id'],
                    created=row['created'],
                    username=row['username'],
                    user_id=row['user_id'],
                    editor=row['editor'] or '',
                    location=(geom['coordinates'][0],
                              geom['coordinates'][1]),
                    color=row['color'],
                    text=row['label'],
                ))
            else:
                result.append(Scribble(
                    id=row['scribble_id'],
                    created=row['created'],
                    username=row['username'],
                    user_id=row['user_id'],
                    editor=row['editor'] or '',
                    style=row['style'],
                    color=row['color'],
                    dashed=row['dashed'],
                    thin=row['thin'],
                    points=geom['coordinates'],
                ))
    return result


async def insert_scribble(cur, s: NewScribble) -> int:
    await cur.execute(
        """insert into scribbles
        (user_id, username, editor, style, color, thin, dashed, geom)
        values (%s, %s, %s, %s, %s, %s, %s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))
        returning scribble_id""",
        (s.user_id, s.username, s.editor, s.style, s.color, s.thin, s.dashed,
         json.dumps({'type': 'LineString', 'coordinates': s.points})))
    return (await cur.fetchone())['scribble_id']


async def insert_label(cur, s: NewLabel) -> int:
    await cur.execute(
        """insert into scribbles
        (user_id, username, editor, color, label, geom)
        values (%s, %s, %s, %s, %s, ST_Point(%s, %s, 4326))
        returning scribble_id""",
        (s.user_id, s.username, s.editor, s.color, s.text, *s.location))
    return (await cur.fetchone())['scribble_id']


async def delete_scribble(cur, s: Deletion) -> int:
    await cur.execute(
        "update scribbles set deleted = now(), deleted_by_id = %s where scribble_id = %s",
        (s.user_id, s.id))
    return s.id
