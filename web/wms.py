from fastapi import HTTPException
from io import BytesIO
from . import config
from .crs import CRS_LIST, BBox
from .models import Scribble, Label, Box
from .db import query
from .dashed_draw import DashedImageDraw
from PIL import Image, ImageDraw, ImageFont
from typing import Union


def get_capabilities(endpoint: str) -> str:
    srs = '\n'.join([f'<SRS>{k}</SRS>' for k in CRS_LIST.keys()])
    xml = """<?xml version='1.0' encoding="UTF-8" standalone="no" ?>
<WMS_Capabilities xmlns="http://www.opengis.net/wms" version="1.1.1">
<Service>
  <Name>WMS</Name>
  <Title>GeoScribbles</Title>
  <ContactInformation>
  </ContactInformation>
</Service>

<Capability>
  <Request>
    <GetCapabilities>
      <Format>application/vnd.ogc.wms_xml</Format>
      <DCPType>
        <HTTP>
          <Get><OnlineResource xmlns:xlink="http://www.w3.org/1999/xlink"
              xlink:href="{url}/wms?"/></Get>
        </HTTP>
      </DCPType>
    </GetCapabilities>
    <GetMap>
      <Format>image/png</Format>
      <DCPType>
        <HTTP>
          <Get><OnlineResource xmlns:xlink="http://www.w3.org/1999/xlink"
              xlink:href="{url}/wms?"/></Get>
        </HTTP>
      </DCPType>
    </GetMap>
  </Request>

  <Exception>
    <Format>application/vnd.ogc.se_xml</Format>
    <Format>application/vnd.ogc.se_inimage</Format>
    <Format>application/vnd.ogc.se_blank</Format>
  </Exception>

  <VendorSpecificCapabilities />

  <Layer>
    <Title>GeoScribbles</Title>
    {srs}
    <LatLonBoundingBox minx="-180" miny="-85.0511287798" maxx="180" maxy="85.0511287798"/>
    <BoundingBox SRS="EPSG:4326" minx="-180" miny="-85.0511287798"
        maxx="180" maxy="85.0511287798"/>
    <Layer queryable="0" opaque="0">
        <Name>scribbles</Name>
        <Title>Scribbles and labels</Title>
    </Layer>
    <Layer queryable="0" opaque="0">
        <Name>latest</Name>
        <Title>Scribbles less than a month old</Title>
    </Layer>
  </Layer>
</Capability>
</WMS_Capabilities>
    """.format(url=str(endpoint).rstrip('/'), srs=srs)
    return xml


async def get_map(params: dict[str, str]) -> bytes:
    # Fist get CRS because everything depends on it.
    crs = CRS_LIST.get(params.get('crs', params.get('srs', '')).upper())
    if not crs:
        raise HTTPException(422, 'Unsupported CRS')

    # Now parse width and height and check they're inside max values.
    try:
        width = int(params['width'])
        height = int(params['height'])
    except ValueError:
        raise HTTPException(422, 'Width and height should be integer numbers')
    if width < 100 or width > config.MAX_IMAGE_WIDTH:
        raise HTTPException(422, f'Max width is {config.MAX_IMAGE_WIDTH}')
    if height < 100 or height > config.MAX_IMAGE_HEIGHT:
        raise HTTPException(422, f'Max height is {config.MAX_IMAGE_HEIGHT}')

    # Bounding box - reproject to 4326.
    try:
        bbox = [float(p) for p in params['bbox'].split(',')]
    except ValueError:
        bbox = []
    if len(bbox) != 4:
        raise HTTPException(422, 'Expecting 4 numbers for bbox')

    bbox_obj = BBox(crs, bbox)
    maxage = 30 if 'latest' in params.get('layers', '') else None
    scribbles = await query(bbox_obj.to_4326(), maxage=maxage)
    out = Image.new('RGBA', (width, height))
    render_image(out, bbox_obj, scribbles)
    content = BytesIO()
    out.save(content, 'PNG')
    return content.getvalue()


def render_image(image: Image, bbox: BBox, scribbles: list[Union[Scribble, Label]]):
    age_colors = {
        3: '#ffffb2',
        7: '#fed976',
        14: '#feb24c',
        30: '#fd8d3c',
        61: '#f03b20',
        1000: '#bd0026',
    }
    draw = DashedImageDraw(image)
    for s in scribbles:
        if isinstance(s, Scribble):
            coords = [bbox.to_pixel(c) for c in s.points]
            coords = [(round(c[0] * image.width), round(c[1] * image.height)) for c in coords]
            width = 3 if s.thin else 5
            if s.dashed:
                draw.dashed_line(coords, (10, 10), fill=f'#{s.color}', width=width)
            else:
                draw.line(coords, fill=f'#{s.color}', width=width)
        elif isinstance(s, Box):
            x1, y1 = bbox.to_pixel((s.box[0], s.box[1]))
            x2, y2 = bbox.to_pixel((s.box[2], s.box[3]))
            xy = [min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)]
            color = '#ffffff'  # not used
            for k in sorted(age_colors.keys()):
                if s.minage <= k or k == 1000:
                    color = age_colors[k]
                    break
            draw.rectangle(xy, fill=color, width=0)
    for s in scribbles:
        # Drawing labels always after geometries
        if isinstance(s, Label):
            coord = bbox.to_pixel(s.location)
            coord = (round(coord[0] * image.width), round(coord[1] * image.height))
            r = 3
            elcoord = [
                (coord[0] - r, coord[1] - r),
                (coord[0] + r, coord[1] + r),
            ]
            draw.ellipse(elcoord, outline='#000000', fill='#e0ffe0', width=1)
            try:
                font = ImageFont.truetype(config.FONT, size=14)
            except OSError:
                font = ImageFont.load_default()
            # Draw semi-transparent background
            expand = 3
            torig = [coord[0] + expand, coord[1] - expand]
            tbox = font.getbbox(s.text)
            tbounds = [
                tbox[0] + torig[0] - expand, tbox[1] + torig[1] - expand,
                tbox[2] + torig[0] + expand, -tbox[3] + torig[1] + expand,
            ]
            draw.rounded_rectangle(tbounds, 5, fill='#00000050')
            draw.text(torig, s.text, fill='#ffffff', font=font, anchor='lb')
