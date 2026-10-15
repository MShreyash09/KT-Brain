---
title: Notes: payments, from my first week
author: meera@tiffinbox.example
date: 2026-09-30T11:30:00Z
kind: notes
---

# Notes: payments, from my first week

## What I learned in week one

These are my notes from the KT session with Arjun on Sep 24, my first two PRs and reading the history. Written for
the next person who joins backend.

## Retries

api/payments/retry.py retries a failed charge 7 times with exponential backoff. It looks like too many, but the
gateway pauses webhooks for a few minutes during its own deploys, and fewer retries lost real orders in August.
The count is now read from PAYMENT_RETRIES, default 7. Do not lower it without reading PAY-88.

## Webhooks

api/payments/webhooks.py dedupes on event_id, so a webhook delivered twice is safe. It verifies every webhook with
WEBHOOK_SECRET. Signature failures now log at error level with a metric; before my PR they were debug-only, which is
why a broken key rotation on staging went unnoticed for a day.

## Rotating keys

Rotating the gateway API key also rotates the webhook signing secret on the gateway's side. Always use
infra/scripts/rotate_secrets.sh, which updates both and sends a test webhook. Never rotate by hand in the console.

## What I still do not know

- How canary deploys decide to roll back (Priya's area; she has left).
- How the database restore test works and who runs it now.
- The Terraform state lock setup.

Those are on the remaining KT list. Kavya knows the CI side and is the closest backup.
