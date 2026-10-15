---
title: Runbook: deploying the api
author: priya@tiffinbox.example
date: 2026-05-20T10:30:00Z
kind: runbook
---

# Runbook: deploying the api

1. Merge to main. The pipeline deploys a canary: 10% of pods for 30 minutes.
2. Watch the error-rate gate in the Actions log. If 5xx > 2% it rolls back by itself.
3. Manual rollback: re-run the previous successful deploy job.
Never edit pods by hand.
