with start_date_table as (
  -- Get the starting date for new clusters.
  select coalesce(date_trunc('day', max(created)) - interval '1 day', timestamp '2024-01-01 00:00Z') as start_date from tasks
)

, clusters as (
  -- Clusterize scribbles.
  select ST_ClusterDBSCAN(geom, 0.02, 1) over (partition by user_id, date_trunc('day', created)) as cid,
    username, user_id, created, geom
  from scribbles, start_date_table
  where deleted is null and created >= start_date
)

, new_tasks as (
  -- Group clusters into tasks.
  select count(*) as cnt, max(username) username, user_id, max(created) created, ST_GeometricMedian(ST_Collect(ST_Centroid(geom))) loc
  from clusters group by cid, user_id, date_trunc('day', created)

), existing as (
  -- Find new tasks to merge with existing tasks.
  select n.*, t.task_id from new_tasks n left join tasks t on n.user_id = t.user_id and date_trunc('day', n.created) = date_trunc('day', t.created) and ST_DWithin(n.loc, t.location, 0.02)

), inserting as (
  -- Insert new tasks.
  insert into tasks (location, scribbles, username, user_id, created)
  select loc, cnt, username, user_id, created
  from existing where task_id is null
  order by created

), updating as (
  -- Update old tasks.
  update tasks
  set location = e.loc, created = e.created, scribbles = e.cnt
  from existing e where tasks.task_id = e.task_id
)

-- Return some debug information.
select * from existing, start_date_table
order by created;
