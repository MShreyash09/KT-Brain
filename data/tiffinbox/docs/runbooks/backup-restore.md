---
title: Runbook: backups and restores
author: priya@tiffinbox.example
date: 2026-06-23T09:30:00Z
kind: runbook
---

# Runbook: backups and restores

- Dumps run daily at 3 AM IST to s3://tiffinbox-backups (30 days).
- Alerts fire in #infra if a dump fails or is under 1 MB.
- We do a restore test every quarter: restore into a scratch DB, compare row counts, record the date here.
- Last restore test: 2026-06-24 (passed).
