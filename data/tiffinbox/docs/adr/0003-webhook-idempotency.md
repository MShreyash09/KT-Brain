---
title: ADR 0003: Webhook idempotency
author: neha@tiffinbox.example
date: 2026-06-12T09:30:00Z
kind: adr
---

# ADR 0003: Webhook idempotency

**Status:** accepted (written by Neha after a walkthrough with Arjun)
**Context:** RupeeRail retries webhooks when our endpoint is slow, so the same event can arrive more than once (PAY-61).
**Decision:** dedupe on event_id. Every event id is stored; a repeat is acknowledged and ignored.
**Consequences:** the processed_events table grows; we keep 90 days.
