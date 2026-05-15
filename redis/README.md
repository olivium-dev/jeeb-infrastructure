# Redis — jeeb-infrastructure

Single Redis 7 instance shared by the Jeeb backend stack. Config lives in
[`redis.conf`](./redis.conf) and is mounted read-only into the container by
`docker-compose.yml`.

## Workloads

| Workload                   | Key pattern                          | TTL       | Notes |
| -------------------------- | ------------------------------------ | --------- | ----- |
| Jeeber geo positions       | `geo:jeebers:{city}` (sorted set)    | none      | `GEOADD` on heartbeat, `GEOSEARCH` from matching-service |
| Chat pub/sub               | `chat:{conversation_id}` (channel)   | n/a       | Fan-out via `PUBLISH` / `SUBSCRIBE` |
| Delivery tracking pub/sub  | `tracking:{order_id}` (channel)      | n/a       | Driver position pushed to mobile clients |
| Auth session cache         | `session:{jti}` (string/hash)        | 30 min    | Mirrors JWT lifetime; refresh slides TTL |
| Rate limit (gateway)       | `ratelimit:{ip}:{route}` (string)    | 60 s      | Token-bucket counter, `INCR` + `EXPIRE` |

## Configuration choices

- **`maxmemory 256mb`** matches the staging container limit. Production
  override goes on the command line.
- **`maxmemory-policy volatile-lru`** evicts only keys with an explicit TTL.
  Geo sets and pub/sub state have no TTL by design — they must never be
  evicted. Cache and rate-limit keys MUST call `EXPIRE`.
- **Persistence: RDB + AOF**. RDB snapshots give fast crash recovery for the
  geo dataset; AOF (`appendfsync everysec`) covers session state and
  rate-limit counters between snapshots. Worst-case data loss is ~1 second.
- **Pub/Sub buffers**: `pubsub 32mb 8mb 60` — chat fan-out can burst past the
  Redis default during incident traffic. The 60-second grace prevents idle
  clients from being dropped during silent windows.

## Smoke test

After `docker compose up -d`, validate the instance:

```bash
./redis/smoke-test.sh
```

This exercises geo commands, pub/sub round-trip, key expiration, and the
runtime `INFO` view of `maxmemory_policy` / `maxmemory`. Exits non-zero on
any check failure.

## Client connection strings

- **Local dev**: `redis://redis:6379` from inside the compose network,
  `redis://localhost:6379` from the host.
- **Staging**: injected via `Redis__ConnectionString` env var on each service.

## Operational notes

- AOF rewrites are automatic at 100% growth past 64MB. Watch
  `aof_current_size` in `INFO persistence` if disk usage climbs.
- The `redisdata` named volume is mounted at `/data`. Back up with
  `docker compose exec redis redis-cli SAVE` followed by a volume snapshot.
- Migrations: there is no schema. New key namespaces should be added to the
  table above so eviction policy assumptions stay correct.
