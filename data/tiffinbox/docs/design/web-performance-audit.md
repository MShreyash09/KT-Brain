---
title: Design: web performance audit (June)
author: kavya@tiffinbox.example
date: 2026-06-10T10:30:00Z
kind: design
---

# Design: web performance audit (June)

## Why now

NPS comments in May mentioned "slow menu" eleven times. Real-user monitoring agrees: on mid-range Android phones in
Pune the menu page has a largest contentful paint (LCP) of 4.8 s at p75. Google's "good" line is 2.5 s. Checkout is
better at 2.9 s but still above the line. This audit lists what is slow and what we fix first.

## Method

- Real-user metrics from the last 14 days, split by page and device class.
- Lighthouse runs on a throttled profile (Moto G class, slow 4G), five runs per page, median reported.
- A bundle analysis of the production build.

## Findings: menu page

1. Every dish image loads eagerly. A typical menu shows 36 dishes, so the page downloads about 2.6 MB of JPEGs
   before it settles, most of them below the fold.
2. Images are served at 1200 px wide even on 360 px screens. No srcset.
3. web/menu/MenuGrid.tsx re-renders the whole grid when the veg filter changes, because the filter state lives in the
   parent and every card gets a new props object.
4. The grid has no fixed card height, so cards jump as images arrive. Cumulative layout shift is 0.31 (good is under 0.1).

## Findings: checkout

1. web/checkout/CheckoutPage.tsx imports the full date library for one formatter. That is 71 KB gzipped.
2. The address autocomplete script loads on page load, not when the field gets focus.
3. web/lib/api.ts retries a failed request three times with no backoff, so on a flaky network a spinner can hang for
   20 s before the user sees an error.

## Plan, in order

| Fix | Page | Expected effect |
|---|---|---|
| Lazy-load dish images, add width/height | menu | LCP -1.5 s, CLS under 0.1 |
| srcset at 360/720/1200 px from the CDN | menu | -60% image bytes on phones |
| Memoize cards, keep filter state local | menu | smoother filter toggle |
| Replace the date library with Intl.DateTimeFormat | checkout | -71 KB JS |
| Load autocomplete on focus | checkout | -180 ms main-thread time |
| Timeout + one retry with backoff in the API client | all | errors show in under 8 s |

## Results so far

Lazy loading and fixed card heights shipped on June 8. Menu LCP p75 dropped from 4.8 s to 3.1 s and CLS from 0.31 to
0.04. Skeleton loaders followed. srcset is blocked on the CDN image-resize setting, which Priya is checking.

## What we are not doing

A move to server-side rendering came up. It would help first paint, but it is a large change to the build and deploy
pipeline for a gain we can mostly get from images alone. We revisit it if LCP stays above 2.5 s after the image work.
