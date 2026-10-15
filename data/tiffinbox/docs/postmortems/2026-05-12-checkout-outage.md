---
title: Postmortem: checkout outage (May 12)
author: priya@tiffinbox.example
date: 2026-05-14T05:30:00Z
kind: postmortem
---

# Postmortem: checkout outage (May 12)

**Impact:** checkout returned 502 for 38 minutes at lunch peak. About 140 orders lost.
**Cause:** v1.8 shipped a config that needed a new env var. The pipeline rolls out to all pods at once,
so every api pod crashlooped at the same time.
**Action items:** research progressive delivery (Priya), add an env-var check to CI (Priya).
