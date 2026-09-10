# MSI realtime Redis override

`zzzz-msi-redis.conf` is a minimal native-systemd override for the verified MSI
development backend. Its target is
`/etc/systemd/system/jeeb-realtime.service.d/zzzz-msi-redis.conf`.

It changes only the Redis endpoint/database and explicitly preserves pool size5.
It must not be applied to staging, production, another Redis owner, or another
unit. It neither enables chat transport nor opens a network listener.

Before application, the authorized operator must verify the exact MSI host,
incumbent PID/source/user, all effective unit/drop-in/environment sources, the
dedicated `jeeb-redis` loopback6380 mapping, database/namespace ownership and
runtime override precedence. Preserve the existing configuration and key mounts;
reject unexpected drift or an existing conflicting destination. Stage verified
bytes privately and install atomically without overwriting an unknown file.

After daemon-reload, prove that only the two intended environment entries changed
before restarting **only** `jeeb-realtime.service`. Require a stable new process,
unchanged user/source/MIX_ENV and secret settings, no automatic restarts, and
repeated strict `/health/ready` checks for database/Redis/pubsub/draining. Verify
Redis rate-limiter selection; replay initialization alone does not attest its
selected backend. No Redis flush, key deletion, migration or broad service restart
is warranted. Any incomplete verification requires diagnosis, not a false pass.

See [the full development contract](../FULL-DEVELOPMENT-BACKEND.md) for the
timestamped applied result and remaining independent acceptance gates.
