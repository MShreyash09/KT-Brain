---
title: Design: orders API v2
author: arjun@tiffinbox.example
date: 2026-05-26T06:30:00Z
kind: design
---

# Design: orders API v2

## Context

The orders API grew one endpoint at a time during the April build. The kitchen dashboard, the customer app and the
ops export all read orders through api/orders/service.py, and each caller added its own query parameters. By late
May we had three ways to filter by status, no pagination, and a list endpoint that returned every order for an area
in one response. On a busy lunch day in Bengaluru that response is 4 MB and takes 2.1 s at p95.

This note proposes a v2 shape for the read side. Writes (create, cancel) stay as they are.

## Goals

- One list endpoint with cursor pagination, stable under concurrent inserts.
- One way to filter: status, area, delivery date, subscription id.
- p95 under 300 ms for the kitchen dashboard query (one area, one delivery slot).
- No breaking change for the mobile app until it ships the new client.

## Non-goals

- Changing how orders are created from subscriptions (billing owns that).
- Real-time updates. The kitchen dashboard polls every 20 s and that is fine for now.

## Proposal

GET /v2/orders takes status, area, date, subscription_id, limit (default 50, max 200) and cursor. The cursor is an
opaque base64 of (delivery_slot, id), which is the sort key. Offset pagination was rejected: new orders arrive during
the lunch rush and offset pages would skip or repeat rows.

The response carries next_cursor, or null on the last page. Each order embeds only what the list views need: id,
status, area, slot, item count, total. The full order with line items stays at GET /v2/orders/{id}.

We add a composite index on (area, delivery_slot, id). The current index on (area) alone forces a sort on every
dashboard call.

## Status filter

Today the kitchen sends status=pending,preparing, the app sends active=true, and the export sends no filter and
drops cancelled rows client-side. v2 accepts status as a comma list only. The v1 endpoint maps active=true to the
same list so old clients keep working.

## Cancel window

Ops asked whether the 10 minute cancel window should be visible in the list. It should: each order gets
cancel_until (a timestamp), so the app can hide the cancel button without asking the server.

## Rollout

1. Ship /v2/orders behind no flag; nothing calls it yet.
2. Move the kitchen dashboard first (we own both sides).
3. Move the ops export, then the mobile app in its next release.
4. Keep v1 for 60 days, log every call, and remove it when the log is quiet for two weeks.

## Open questions

- Should the export get a streaming CSV endpoint instead of paging through JSON? Probably yes, later.
- Do we need area-level rate limits? Only if a partner integration shows up.
