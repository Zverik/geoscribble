import logging
import os
from typing import Annotated, Union, Optional
from fastapi import FastAPI, Query, HTTPException, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from . import config
from .models import (
    NewScribble, NewLabel, Deletion, Scribble, Label,
    FeatureCollection, Feature, Box, Task,
)
from .db import (
    init_database, query, get_cursor,
    insert_scribble, insert_label, delete_scribble,
    list_tasks,
)
from .wms import get_map, get_capabilities


logging.basicConfig(
    level=logging.INFO, format='[%(levelname)s] %(message)s')
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
)
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), 'templates'))


@app.on_event('startup')
async def startup():
    await init_database()


@app.get('/map', response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse(request=request, name='browse.html')


def format_date(d) -> str:
    return d.strftime('%d %b %H:%M')


templates.env.filters['format_date'] = format_date


@app.get('/', response_class=HTMLResponse)
async def list_edits(request: Request):
    # TODO: sign in with oauth2, filter by user, close tasks
    edits = await list_tasks()
    return templates.TemplateResponse(
        request=request, name='list.html', context={'edits': edits})


@app.get('/tasks')
async def tasks(
        bbox: Annotated[Optional[str], Query(pattern=r'^-?\d+(?:\.\d+)?(,-?\d+(?:\.\d+)?){3}$')],
        username: Optional[str] = None, user_id: Optional[int] = None,
        maxage: Optional[int] = None) -> list[Task]:
    box = None if not bbox else [float(part.strip()) for part in bbox.split(',')]
    return await list_tasks(box, username, user_id, maxage)


@app.get('/scribbles')
async def scribbles(
        bbox: Annotated[str, Query(pattern=r'^-?\d+(?:\.\d+)?(,-?\d+(?:\.\d+)?){3}$')],
        username: Optional[str] = None, user_id: Optional[int] = None,
        maxage: Optional[int] = None) -> list[Union[Scribble, Label, Box]]:
    box = [float(part.strip()) for part in bbox.split(',')]
    return await query(box, username, user_id, None, maxage)


@app.get('/geojson')
async def geojson(
        bbox: Annotated[str, Query(pattern=r'^-?\d+(?:\.\d+)?(,-?\d+(?:\.\d+)?){3}$')],
        username: Optional[str] = None, user_id: Optional[str] = None,
        maxage: Optional[int] = None) -> FeatureCollection:
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
                    'color': None if not s.color else f'#{s.color}',
                    'dashed': s.dashed,
                    'thin': s.thin,
                    'userName': s.username,
                    'userId': s.user_id,
                    'editor': s.editor,
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
                    'userId': s.user_id,
                    'editor': s.editor,
                    'created': s.created,
                }
            ))
        elif isinstance(s, Box):
            features.append(Feature(
                f_type='Feature',
                geometry={
                    'type': 'Polygon',
                    'coordinates': [[
                        [s.box[0], s.box[1]],
                        [s.box[2], s.box[1]],
                        [s.box[2], s.box[3]],
                        [s.box[0], s.box[3]],
                        [s.box[0], s.box[1]],
                    ]],
                },
                properties={
                    'type': 'box',
                    'minAge': s.minage,
                },
            ))
    return FeatureCollection(features=features)


@app.get('/wms')
async def wms(request: Request):
    params = {k.lower(): v for k, v in request.query_params.items()}
    if params.get('request') == 'GetCapabilities':
        if params.get('service', 'WMS') != 'WMS':
            raise HTTPException(422, "Please use WMS for service")
        base_url = config.BASE_URL or request.scope.get('root_path') or request.base_url
        xml = get_capabilities(base_url)  # TODO: url behind proxy
        return Response(content=xml, media_type='application/xml')
    elif params.get('request') == 'GetMap':
        if any([k not in params for k in ('format', 'bbox', 'width', 'height', 'layers')]):
            raise HTTPException(422, "Missing parameter for GetMap")
        if params.get('format') != 'image/png':
            raise HTTPException(422, "GetMap supports only PNG images")
        data = await get_map(params)
        return Response(content=data, media_type='image/png')
    else:
        raise HTTPException(422, "This server supports only GetCapabilities and GetMap")


@app.post('/upload')
async def put_scribbles(
        scribbles: list[Union[NewScribble, NewLabel, Deletion]]
        ) -> list[Optional[int]]:
    # Check that at least the user is the same
    for i in range(1, len(scribbles)):
        if (scribbles[i].user_id != scribbles[0].user_id or
                scribbles[i].username != scribbles[0].username or
                scribbles[i].editor != scribbles[0].editor):
            raise HTTPException(401, "User and editor should be the same for all elements")

    new_ids: list[Optional[int]] = []
    async with get_cursor(True) as cur:
        for s in scribbles:
            if isinstance(s, NewScribble):
                new_ids.append(await insert_scribble(cur, s))
            elif isinstance(s, NewLabel):
                new_ids.append(await insert_label(cur, s))
            elif isinstance(s, Deletion):
                new_ids.append(await delete_scribble(cur, s))
    return new_ids


@app.put('/new')
async def put_one_scribble(scribble: Union[NewScribble, NewLabel]) -> int:
    async with get_cursor(True) as cur:
        if isinstance(scribble, NewScribble):
            return await insert_scribble(cur, scribble)
        elif isinstance(scribble, NewLabel):
            return await insert_label(cur, scribble)
    raise HTTPException(401)  # TODO: proper error
