from math import radians, degrees, cos, tan, log, pi, asin, tanh


__all__ = ['BaseCRS', 'CRS_LIST', 'BBox']


EARTH_RADIUS = 6378137


class BaseCRS:
    def coords_to_pixel(self, lon: float, lat: float) -> tuple[float, float]:
        """Always returns (x, y)."""
        return lon, lat

    def pixel_to_coords(self, x: float, y: float) -> tuple[float, float]:
        """Returns either (lon, lat) or (lat, lon) depending on CRS."""
        return x, y


class CRS_4326(BaseCRS):
    pass


class CRS_3857(BaseCRS):
    def coords_to_pixel(self, lon: float, lat: float) -> tuple[float, float]:
        rlat = radians(lat)
        x = radians(lon)
        if lat > 85:
            y = pi * 2
        elif lat < -85:
            y = -pi * 2
        else:
            y = log(tan(rlat) + (1/cos(rlat)))
        return x * EARTH_RADIUS, y * EARTH_RADIUS

    def pixel_to_coords(self, x: float, y: float) -> tuple[float, float]:
        fx = x / EARTH_RADIUS
        fy = asin(tanh(y / EARTH_RADIUS))
        return degrees(fx), degrees(fy)


CRS_LIST: dict[str, BaseCRS] = {
    'EPSG:4326': CRS_4326(),
    'EPSG:3857': CRS_3857(),
}


class BBox:
    def __init__(self, crs: BaseCRS, proj_bbox: list[float]):
        self.crs = crs
        self.x = proj_bbox[0]
        self.y = proj_bbox[1]
        self.w = proj_bbox[2] - proj_bbox[0]
        self.h = proj_bbox[3] - proj_bbox[1]

    def to_pixel(self, lonlat: tuple[float, float]) -> tuple[float, float]:
        proj = self.crs.coords_to_pixel(lonlat[0], lonlat[1])
        return (proj[0] - self.x) / self.w, (proj[1] - self.y) / self.h

    def to_4326(self) -> list[float]:
        return [
            *self.crs.pixel_to_coords(self.x, self.x + self.w),
            *self.crs.pixel_to_coords(self.y, self.y + self.h),
        ]
