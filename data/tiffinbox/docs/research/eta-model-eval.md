---
title: Research: ETA model evaluation
author: rohan@tiffinbox.example
date: 2026-06-26T11:30:00Z
kind: research
---

# Research: ETA model evaluation

## Question

Customers see a delivery ETA when they place a same-day order and again when the rider picks up. Support tickets
about late tiffins rose after we added two new kitchens. Is our ETA model getting worse, and which features would
fix it?

## Current model

ml/eta/predict.py serves a gradient-boosted tree model trained weekly on the last 60 days of deliveries. Features:
kitchen id, area, slot, distance by road, rider's last three trip times, and order count in the slot. The target is
minutes from pickup to doorstep.

## Data

- 41,200 deliveries from Apr 15 to Jun 20 across Bengaluru, Pune and Mumbai.
- Holdout: the last 10 days, so the evaluation sees the new kitchens.
- Labels come from the rider app's "delivered" tap. About 3% of taps happen more than 5 minutes after the actual
  handover (riders tap at the next stop), so we drop trips where the GPS shows the rider already moving away.

## Results on the holdout

| Model | MAE (min) | p90 abs error (min) | Late by over 10 min |
|---|---|---|---|
| Distance-only baseline | 7.9 | 17.4 | 14.1% |
| Current model | 5.2 | 11.8 | 8.6% |
| Current + rain | 4.6 | 10.1 | 6.9% |
| Current + rain + kitchen prep backlog | 4.3 | 9.4 | 6.2% |

The current model is not getting worse overall. The error is concentrated in two places: rainy afternoons in
Mumbai and Pune (MAE 9.8 min) and the two new kitchens, where the model has under two weeks of history.

## Rain

We pull hourly rainfall per area from a public weather API. A simple "raining at pickup" flag cuts MAE on rainy
trips from 9.8 to 6.1 minutes. Intensity buckets add a little more but need a paid tier, so not now.

## New kitchens

For a kitchen with little history we fall back to the area average for prep time. Adding the kitchen's current
backlog (orders accepted but not picked up) helps every kitchen, not only new ones. It needs a small read from the
orders service, which is already exposed for the kitchen dashboard.

## Recommendation

1. Ship the rain flag now. It is one feature, one lookup, and the biggest gain.
2. Add prep backlog after the orders API v2 list endpoint is live, to avoid a new query on the hot path.
3. Show ETA as a 10 minute window instead of a single minute value. The survey last quarter said customers trust a
   window more, and it matches our real p90 error better.

## Risks

- The weather API has had two outages this year. If it is down, the feature defaults to "not raining", which is the
  current behaviour, so the model only loses the gain.
- Weekly retraining can drift if rider labelling changes. The ETA error dashboard (REC ticket) should alert when the
  weekly MAE moves by more than 1 minute.
