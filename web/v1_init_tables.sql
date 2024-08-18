create table if not exists scribbles (
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

    deleted timestamp with time zone,
    deleted_by_id integer
);

create index if not exists scribbles_idx_geom on scribbles using gist (geom);
create index if not exists scribbles_idx_created on scribbles (created);
create index if not exists scribbles_idx_user_id on scribbles (user_id);

create table if not exists tasks (
    task_id serial primary key,
    location geometry not null,
    location_str text,
    scribbles integer not null,
    username text not null,
    user_id integer not null,
    created timestamp with time zone not null,
    processed timestamp with time zone,
    processed_by_id integer
);

create index if not exists tasks_idx_location on tasks (location);
create index if not exists tasks_idx_created on tasks (created);
create index if not exists tasks_idx_user_id on tasks (user_id);
