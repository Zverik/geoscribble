create table scribbles (
    scribble_id serial primary key,
    geom geometry not null,
    username text not null,
    user_id integer not null,
    editor text not null,
    created timestamp with time zone not null default now(),

    style text,
    color text,
    thin boolean not null default true,
    dashed boolean not null default false,
    label text,
    deleted timestamp with time zone
);

create index scribbles_idx_geom on scribbles using gist (geom);
create index scribbles_idx_created on scribbles (created);
