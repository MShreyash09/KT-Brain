---
title: Research: cold-start recommendations
author: rohan@tiffinbox.example
date: 2026-08-12T12:30:00Z
kind: research
---

# Research: cold-start recommendations

## Problem

The home screen shows "Recommended for you": six dishes ranked by ml/recommend/model.py. For a subscriber with two or
more weeks of orders this works well: click-through on the row is 7.2%. For a new user with no history, the model
falls back to the six most-ordered dishes in their city, and click-through is 2.1%. New users are a third of daily
home-screen views, so this is where the row is weakest.

## What a new user gives us

- City and area, from the address step.
- Plan type (veg, non-veg, mixed), from the plan step.
- Every menu page they scroll and every dish they open before ordering, from the first session.
- Optional: a three-question taste quiz we could add to onboarding (spice level, cuisines, "light or filling").

## Options compared

| Option | Offline hit rate @6 | Notes |
|---|---|---|
| City top sellers (today) | 0.11 | No personalisation |
| Area top sellers filtered by plan type | 0.17 | Trivial to build |
| Session-based: embed dishes opened in session one | 0.24 | Needs the cuisine embeddings already in ml/recommend/features.py |
| Taste quiz to cuisine embedding | 0.22 | Adds an onboarding step, which the funnel research says to avoid |
| Session-based + area top sellers blend | 0.27 | Best offline |

Offline hit rate means: of the next week's orders for users in the holdout, how often was an ordered dish in the six
we would have shown. The holdout is 2,300 users who signed up between Jul 10 and Jul 31.

## Choice

The blend: start with area top sellers filtered by plan type, then, as soon as the user opens two or more dishes,
mix in nearest neighbours of those dishes from the cuisine embeddings. After the first order the normal model takes
over.

We drop the taste quiz. The onboarding funnel research shows every extra step costs users, and the session signal
gives most of the gain for free.

## Serving

api/recommend/endpoint.py already caches responses per user for 10 minutes. For cold-start users the cache key
becomes (area, plan type, opened dish ids), so most new users share cache entries. No new infrastructure.

## How we will know

An A/B test on new users for two weeks. Primary metric: home-row click-through in the first 7 days. Guardrail: 7-day
activation must not drop. We expect click-through to go from 2.1% to about 4%.

## Later

If the weekly retrain job moves to daily, cold-start users would graduate to the full model faster. Not needed for
this change.
