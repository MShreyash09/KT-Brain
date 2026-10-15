---
title: Research: Redis right-sizing
author: priya@tiffinbox.example
date: 2026-08-20T05:30:00Z
kind: research
---

# Research: Redis right-sizing

## Trigger

The AWS bill rose 8% in July and almost all of the increase is Redis. We run one ElastiCache cluster (3 nodes,
cache.r6g.xlarge) defined in infra/terraform/main.tf. Memory use has crept from 9 GB to 19 GB since April.

## What is in Redis

A one-hour key scan by prefix (MEMORY USAGE on a sample of 50,000 keys, scaled up):

| Prefix | Share of memory | TTL | Owner |
|---|---|---|---|
| rec:user:* | 46% | none | recommendations cache |
| sess:* | 21% | 30 days | auth sessions |
| menu:* | 12% | 1 hour | menu cache |
| ratelimit:* | 3% | 1 minute | login rate limit |
| rq:* | 9% | until done | background jobs |
| other | 9% | mixed | |

## Findings

1. The recommendations cache sets no TTL. The endpoint is meant to cache for 10 minutes, but the TTL is passed to
   the wrong argument, so entries never expire. This one bug is almost half our Redis memory.
2. Auth sessions keep 30 days even for users who logged out. Logout deletes the token on the client only.
3. Finished background jobs keep their results forever. Nobody reads them after one day.
4. CPU averages 6% on all three nodes. We are paying for memory, not compute.

## Options

- Fix the TTLs and stay on the same size: memory should drop to about 8 GB, but the bill stays the same.
- Fix the TTLs and move to cache.r6g.large (13 GB each): about 48% cheaper, with headroom.
- Move sessions out of Redis into Postgres: not worth it; sessions are small once logout deletes them.

## Recommendation

1. Rohan fixes the recommendations cache TTL (one line in the endpoint).
2. Arjun makes logout delete the session key on the server.
3. Set result_ttl to one day on background jobs.
4. Watch memory for a week, then change the node type in Terraform, one node at a time, during the 3 to 5 PM lull
   between lunch and dinner.

## Rollback

The node type change is a Terraform apply. If latency rises, apply the old type back; ElastiCache resizes online.
Keep the old size in a comment in main.tf until the next bill confirms the saving.

## Expected saving

About 48% of the Redis line, which is around 5% of the total AWS bill.
