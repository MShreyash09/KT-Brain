---
title: PRD: Weekly tiffin subscriptions
author: neha@tiffinbox.example
date: 2026-07-20T05:30:00Z
kind: prd
---

# PRD: Weekly tiffin subscriptions

## Problem
Office workers in Pune want a home-style lunch without ordering every day.

## Billing
- We charge on day 1 of each cycle; paused days are prorated as credit on the next cycle.
- Failed charges are retried automatically before a subscription is marked unpaid.

## Pausing (added 2026-07-20)
- Customers can pause from the app. Based on interviews, the survey and the competitor scan
  (docs/research/), pauses are capped at 14 days. Longer breaks should cancel and resubscribe.

## Out of scope for v1
Family plans, corporate billing.
