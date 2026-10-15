---
title: Research: backups we can trust
author: priya@tiffinbox.example
date: 2026-06-18T06:30:00Z
kind: research
---

# Research: backups we can trust

GitLab's 31 Jan 2017 database incident: five backup methods were set up and none worked when needed,
because nobody had tested a restore. Our INC-2 is the same failure in miniature.

Takeaways: alert on failed or tiny dumps; a backup only counts once it has been restored.
Plan: dump at 3 AM IST (lowest traffic), alert if the job fails or the dump is under 1 MB,
and a restore test every quarter into a scratch database with row-count checks.
