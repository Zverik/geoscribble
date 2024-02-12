import logging
import os
from typing import Annotated
from fastapi import FastAPI, Query, HTTPException, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from . import config
from .models import (
    NewScribble, NewLabel, Deletion, Scribble, Label,
    FeatureCollection, Feature,
)
from .db import (
    init_database, query, get_cursor,
    insert_scribble, insert_label, delete_scribble,
)
from .wms import get_map, get_capabilities


logging.basicConfig(
    level=logging.INFO, format='[%(levelname)s] %(message)s')
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
)
browse_cache: str = ''


@app.on_event('startup')
async def startup():
    await init_database()

    global browse_cache
    with open(os.path.join(os.path.dirname(__file__), 'browse.html'), 'r') as f:
        browse_cache = f.read()


@app.get('/', response_class=HTMLResponse)
async def root():
    # return {'name': 'GeoScribble Server', 'version': '0.1'}
    global browse_cache
    return browse_cache


@app.get('/scribbles')
async def scribbles(
        bbox: Annotated[str, Query(pattern=r'^-?\d+(?:\.\d+)?(,-?\d+(?:\.\d+)?){3}$')],
        username: str | None = None, user_id: int | None = None,
        maxage: int | None = None) -> list[Scribble | Label]:
    box = [float(part.strip()) for part in bbox.split(',')]
    if (abs(box[2] - box[0]) > config.MAX_COORD_SPAN or
            abs(box[3] - box[1]) > config.MAX_COORD_SPAN):
        raise HTTPException(422, f"Maximum coordinate span is {config.MAX_COORD_SPAN}")
    return await query(box, username, user_id, maxage)


@app.get('/geojson')
async def geojson(
        bbox: Annotated[str, Query(pattern=r'^-?\d+(?:\.\d+)?(,-?\d+(?:\.\d+)?){3}$')],
        username: str | None = None, user_id: str | None = None,
        maxage: int | None = None) -> FeatureCollection:
    scr = await scribbles(bbox, username, user_id, maxage)
    features = []
    for s in scr:
        if isinstance(s, Scribble):
            features.append(Feature(
                f_type='Feature',
                geometry={'type': 'LineString', 'coordinates': s.points},
                properties={
                    'type': 'scribble',
                    'id': s.id,
                    'style': s.style,
                    'color': f'#{s.color}',
                    'dashed': s.dashed,
                    'thin': s.thin,
                    'username': s.username,
                    'user_id': s.user_id,
                    'created': s.created,
                }
            ))
        elif isinstance(s, Label):
            features.append(Feature(
                f_type='Feature',
                geometry={'type': 'Point', 'coordinates': s.location},
                properties={
                    'type': 'label',
                    'id': s.id,
                    'color': None if not s.color else f'#{s.color}',
                    'text': s.text,
                    'username': s.username,
                    'user_id': s.user_id,
                    'created': s.created,
                }
            ))
    return FeatureCollection(features=features)


@app.get('/wms')
async def wms(request: Request):
    params = {k.lower(): v for k, v in request.query_params.items()}
    if params.get('request') == 'GetCapabilities':
        if params.get('service', 'WMS') != 'WMS':
            raise HTTPException(422, "Please use WMS for service")
        logging.info('Base URL: %s', request.base_url)
        xml = get_capabilities(request.base_url)  # TODO: url
        return Response(content=xml, media_type='application/xml')
    elif params.get('request') == 'GetMap':
        if any([k not in params for k in ('format', 'bbox', 'crs', 'width', 'height', 'layers')]):
            raise HTTPException(422, "Missing parameter for GetMap")
        if params.get('format') != 'image/png':
            raise HTTPException(422, "GetMap supports only PNG images")
        data = await get_map(params)
        return Response(content=data, media_type='image/png')
    else:
        raise HTTPException(422, "This server supports only GetCapabilities and GetMap")


@app.post('/upload')
async def put_scribbles(
        scribbles: list[NewScribble | NewLabel | Deletion]
        ) -> list[int | None]:
    # Check that at least the user is the same
    for i in range(1, len(scribbles)):
        if (scribbles[i].user_id != scribbles[0].user_id or
                scribbles[i].username != scribbles[0].username):
            raise HTTPException(401, "User should be the same for all elements")

    new_ids: list[int | None] = []
    async with get_cursor(True) as cur:
        for s in scribbles:
            if isinstance(s, NewScribble):
                new_ids.append(await insert_scribble(cur, s))
            elif isinstance(s, NewLabel):
                new_ids.append(await insert_label(cur, s))
            elif isinstance(s, Deletion):
                new_ids.append(await delete_scribble(cur, s.id))
    return new_ids


@app.put('/new')
async def put_one_scribble(scribble: NewScribble | NewLabel) -> int:
    async with get_cursor(True) as cur:
        if isinstance(scribble, NewScribble):
            logging.info(scribble.points)
            return await insert_scribble(cur, scribble)
        elif isinstance(scribble, NewLabel):
            return await insert_label(cur, scribble)
    raise HTTPException(401)  # TODO: proper error


@app.delete('/delete/{scribble_id}')
async def delete_one_scribble(scribble_id: int) -> int:
    async with get_cursor(True) as cur:
        return await delete_scribble(cur, scribble_id)
