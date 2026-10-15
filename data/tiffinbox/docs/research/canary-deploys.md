---
title: Research: progressive delivery after INC-1
author: priya@tiffinbox.example
date: 2026-05-15T09:30:00Z
kind: research
---

# Research: progressive delivery after INC-1

Cloudflare's 2 July 2019 outage: one WAF rule was pushed to every machine at once and CPU hit 100% worldwide.
Their fix was staged rollouts that watch error rates before going wider.
Same shape as our INC-1: one change, every pod, no stop button.

Options considered: blue/green (needs 2x capacity, too expensive now), canary (cheap on k8s).
Recommendation: canary 10% of pods for 30 minutes and roll back automatically if 5xx goes above 2%.
