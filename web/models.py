from math import radians, cos, sqrt
from typing import Annotated, Optional
from annotated_types import Len
from pydantic import BaseModel, Field, PastDatetime
from pydantic.functional_validators import AfterValidator
from . import config


class Identification(BaseModel):
    username: Annotated[str, Field(description='OSM user name')]
    user_id: Annotated[int, Field(
        gt=0, description='OSM user id', examples=[1234])]
    editor: Annotated[str, Field(
        description='Editor that uploaded the element', examples=['Every Door'])]


def distance(p1: tuple[float, float], p2: tuple[float, float]) -> float:
    l1 = radians(p1[1])
    l2 = radians(p2[1])
    f1 = radians(p1[0])
    f2 = radians(p2[0])
    x = (l2 - l1) * cos((f1 + f2) / 2)
    y = f2 - f1
    return sqrt(x * x + y * y) * 6371000


def validate_length(points: list[tuple[float, float]]):
    length = 0.0
    for i in range(1, len(points)):
        length += distance(points[i-1], points[i])
    assert length <= config.MAX_LENGTH, (
        f'Length of a scribble should be under {config.MAX_LENGTH} meters')
    return points


class NewScribble(Identification):
    style: Annotated[str, Field(examples=['track'])]
    color: Annotated[Optional[str], Field(
        pattern='^[0-9a-fA-F]{6}$', description='Color in hex format RRGGBB')] = None
    dashed: bool = False
    thin: bool = True
    points: Annotated[list[tuple[float, float]],
                      Len(min_length=2, max_length=config.MAX_POINTS),
                      AfterValidator(validate_length),
                      Field(
                          description='Points as (lon, lat) for a line',
                          examples=[[[10.1, 55.2], [10.2, 55.1]]])
                      ]


class NewLabel(Identification):
    location: Annotated[tuple[float, float], Field(examples=[[10.1, 55.2]])]
    text: Annotated[str, Field(
        min_length=1, max_length=40, examples=['fence'])]
    color: Annotated[Optional[str], Field(
        pattern='^[0-9a-fA-F]{6}$', description='Color in hex format RRGGBB')] = None


class Deletion(Identification):
    id: Annotated[int, Field(
        description='Unique id of the scribble', examples=[45, 91])]
    deleted: Annotated[bool, Field(
        description='Should be true for deleting an element')]


class Scribble(NewScribble):
    id: Annotated[int, Field(
        description='Unique id of the scribble', examples=[45, 46])]
    created: PastDatetime


class Label(NewLabel):
    id: Annotated[int, Field(
        description='Unique id of the scribble', examples=[46])]
    created: PastDatetime


class Box(BaseModel):
    box: Annotated[list[float], Field(description='Bounding box')]
    minage: int


class Task(BaseModel):
    id: Annotated[int, Field(
        description='Unique id of the task', examples=[21])]
    location: Annotated[tuple[float, float], Field(examples=[[10.1, 55.2]])]
    location_str: Annotated[Optional[str], Field(
        description='Country and city of the task')]
    scribbles: Annotated[int, Field(
        description='Count of scribbles in this task', examples=[1])]
    username: Annotated[str, Field(description='OSM user name')]
    user_id: Annotated[int, Field(
        gt=0, description='OSM user id', examples=[1234])]
    created: PastDatetime
    processed: Optional[PastDatetime]
    processed_by_id: Annotated[Optional[int], Field(
        gt=0, description='OSM user who closed the task', examples=[1234])]


class Feature(BaseModel):
    f_type: Annotated[str, Field("Feature", serialization_alias='type')]
    geometry: dict
    properties: dict


class FeatureCollection(BaseModel):
    features: list[Feature]
