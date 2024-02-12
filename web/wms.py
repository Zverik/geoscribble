from fastapi import HTTPException
from io import BytesIO
from . import config
from .crs import CRS_LIST, BBox
from .models import Scribble, Label
from .db import query
from PIL import Image, ImageDraw


def get_capabilities(endpoint: str) -> str:
    srs = '\n'.join([f'<SRS>{k}</SRS>' for k in CRS_LIST.keys()])
    xml = """
<?xml version='1.0' encoding="UTF-8" standalone="no" ?>
<!DOCTYPE WMT_MS_Capabilities SYSTEM "http://schemas.opengis.net/wms/1.1.1/WMS_MS_Capabilities.dtd"
 [
 <!ELEMENT VendorSpecificCapabilities EMPTY>
 ]>  <!-- end of DOCTYPE declaration -->

<WMT_MS_Capabilities version="1.1.1">
<Service>
  <Name>OGC:WMS</Name>
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
</WMT_MS_Capabilities>
    """.format(url=endpoint, srs=srs)
    return xml


async def get_map(params: dict[str, str]) -> bytes:
    # Fist get CRS because everything depends on it.
    crs = CRS_LIST.get(params['crs'].upper())
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
    out = Image.new('RGBA', width, height)
    render_image(out, bbox_obj, scribbles)
    content = BytesIO()
    out.save(content, 'PNG')
    return content.getvalue()


def render_image(image: Image, bbox: BBox, scribbles: list[Scribble | Label]):
    draw = ImageDraw.Draw(image)
    for s in scribbles:
        if isinstance(s, Scribble):
            coords = [bbox.to_pixel(c) for c in s.points]
            coords = [(round(c[0] * image.width), round(c[1] * image.height)) for c in coords]
            width = 3 if s.thin else 7
            draw.line(coords, fill=f'#{s.color}', width=width)
        elif isinstance(s, Label):
            coord = bbox.to_pixel(s.location)
            coord = (round(coord[0] * image.width), round(coord[1] * image.height))
            # TODO: draw.text
