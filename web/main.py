import logging
import os
from typing import Annotated, Union, Optional
from fastapi import FastAPI, Query, HTTPException, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from authlib.integrations.starlette_client import OAuth
from authlib.common.errors import AuthlibBaseError
from xml.etree import ElementTree as etree
from . import config
from .models import (
    NewScribble, NewLabel, Deletion, Scribble, Label,
    FeatureCollection, Feature, Box, Task,
)
from .db import (
    init_database, query, get_cursor,
    insert_scribble, insert_label, delete_scribble,
    list_tasks, mark_processed,
)
from .wms import get_map, get_capabilities


logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=['*'])
app.add_middleware(SessionMiddleware, secret_key=config.SECRET_KEY, max_age=3600*24*365)
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), 'templates'))

oauth = OAuth()
oauth.register(
    'openstreetmap',
    api_base_url='https://api.openstreetmap.org/api/0.6/',
    access_token_url='https://www.openstreetmap.org/oauth2/token',
    authorize_url='https://www.openstreetmap.org/oauth2/authorize',
    client_id=config.OAUTH_ID,
    client_secret=config.OAUTH_SECRET,
    client_kwargs={'scope': 'read_prefs'},
)


@app.on_event('startup')
async def startup():
    await init_database()


@app.get('/map', response_class=HTMLResponse, include_in_schema=False)
async def root(request: Request):
    return templates.TemplateResponse(request=request, name='browse.html')


def format_date(d) -> str:
    return d.strftime('%d %b %H:%M')


templates.env.filters['format_date'] = format_date


@app.get('/', response_class=HTMLResponse, include_in_schema=False)
async def list_edits(request: Request):
    user_id = request.session.get('user_id')
    nofilter = bool(request.session.get('nofilter'))
    edits = await list_tasks(user_id=None if nofilter else user_id)

    context = {
        'edits': edits,
        'username': request.session.get('username'),
        'nofilter': nofilter,
    }
    return templates.TemplateResponse(
        request=request, name='list.html', context=context)


@app.get('/task_process', include_in_schema=False)
async def process_task(task_id: int, request: Request):
    user_id = request.session.get('user_id')
    if user_id:
        await mark_processed(task_id, user_id)
    return RedirectResponse(request.url_for('list_edits'))


@app.get('/task_unprocess', include_in_schema=False)
async def unprocess_task(task_id: int, request: Request):
    user_id = request.session.get('user_id')
    if user_id:
        await mark_processed(task_id, None)
    return RedirectResponse(request.url_for('list_edits'))


@app.get('/toggle_filter', include_in_schema=False)
async def toggle_filter(request: Request):
    request.session['nofilter'] = not request.session.get('nofilter')
    return RedirectResponse(request.url_for('list_edits'))


@app.get("/login", include_in_schema=False)
async def login_via_osm(request: Request):
    redirect_uri = request.url_for('auth_via_osm')
    return await oauth.openstreetmap.authorize_redirect(request, redirect_uri)


@app.get("/auth", include_in_schema=False)
async def auth_via_osm(request: Request):
    try:
        token = await oauth.openstreetmap.authorize_access_token(request)
    except AuthlibBaseError:
        return HTMLResponse('Denied. <a href="' + request.url_for('list_edits') + '">Go back</a>.')

    response = await oauth.openstreetmap.get('user/details', token=token)
    user_details = etree.fromstring(response.content)
    request.session['username'] = user_details[0].get('display_name')
    request.session['user_id'] = int(user_details[0].get('id') or 1)

    return RedirectResponse(request.url_for('list_edits'))


@app.get('/logout', include_in_schema=False)
async def logout(request: Request):
    request.session.pop('username')
    request.session.pop('user_id')
    return RedirectResponse(request.url_for('list_edits'), 302)


@app.get('/tasks')
async def tasks(
        bbox: Annotated[Optional[str], Query(pattern=r'^-?\d+(?:\.\d+)?(,-?\d+(?:\.\d+)?){3}$')],
        username: Optional[str] = None, user_id: Optional[int] = None,
        maxage: Optional[int] = None) -> list[Task]:
    """List tasks (grouped scribbles) by user and date."""
    box = None if not bbox else [float(part.strip()) for part in bbox.split(',')]
    return await list_tasks(box, username, user_id, maxage)


@app.get('/scribbles')
async def scribbles(
        bbox: Annotated[str, Query(pattern=r'^-?\d+(?:\.\d+)?(,-?\d+(?:\.\d+)?){3}$')],
        username: Optional[str] = None, user_id: Optional[int] = None,
        maxage: Optional[int] = None) -> list[Union[Scribble, Label, Box]]:
    """Return scribbles for a given area, in a raw json format."""
    box = [float(part.strip()) for part in bbox.split(',')]
    return await query(box, username, user_id, None, maxage)


@app.get('/geojson')
async def geojson(
        bbox: Annotated[str, Query(pattern=r'^-?\d+(?:\.\d+)?(,-?\d+(?:\.\d+)?){3}$')],
        username: Optional[str] = None, user_id: Optional[str] = None,
        maxage: Optional[int] = None) -> FeatureCollection:
    """Return scribbles for a given area as GeoJSON."""
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
    """WMS endpoint for editors."""
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
    """Batch upload scribbles, labels, and deletions."""
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
    """Upload one scribble or label."""
    async with get_cursor(True) as cur:
        if isinstance(scribble, NewScribble):
            return await insert_scribble(cur, scribble)
        elif isinstance(scribble, NewLabel):
            return await insert_label(cur, scribble)
    raise HTTPException(401)  # TODO: proper error
