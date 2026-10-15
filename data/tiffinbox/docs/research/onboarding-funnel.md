---
title: Research: onboarding funnel analysis
author: neha@tiffinbox.example
date: 2026-08-05T09:30:00Z
kind: research
---

# Research: onboarding funnel analysis

## Summary

Of every 100 people who open the app for the first time, 9 end up with an active subscription a week later. The
biggest single drop is the address step, not payment as we assumed. Fixing address entry is worth more than any
pricing experiment on the table.

## Funnel (first opens Jun 1 to Jul 31, all cities)

| Step | Users | Of previous step |
|---|---|---|
| First open | 18,400 | |
| Browsed the menu | 14,900 | 81% |
| Picked a plan | 6,300 | 42% |
| Entered an address | 3,200 | 51% |
| Paid | 2,050 | 64% |
| Active after 7 days | 1,660 | 81% |

## Address step

Half of the people who pick a plan never finish an address. Session recordings (we watched 60) show three causes:

1. Area not served. 38% of failed attempts are outside our delivery areas, and we only say so after the full form
   is filled in. We should ask for the pincode first.
2. Autocomplete misses apartment complexes. Big gated societies in Pune and Bengaluru are not in the autocomplete
   source, so people type the full address by hand on a phone.
3. Back button wipes the form. Going back to change the plan clears the address. There is already a WEB ticket for it.

## Payment step

64% completion is in line with other Indian subscription apps we compared. UPI failures are most of the drop, and
almost all of those retry successfully within 5 minutes, so the real loss is small.

## Menu to plan

Only 42% of browsers pick a plan. Interviews from the pause research suggest people are unsure about committing for
a week. A "try one day" plan came up again. It needs billing work, so it goes on the Q4 list with corporate plans.

## Recommendations

1. Ask for the pincode first and stop early with a "notify me" option if we do not serve the area.
2. Keep the address in local state across the plan step (Kavya has the ticket).
3. Add the top 300 gated societies per city to autocomplete; ops already has the list from rider notes.
4. Measure again four weeks after the changes ship.

## Expected impact

If the address step goes from 51% to 65%, active subscribers from the same traffic rise by about 27%, roughly 450
more per two months at current traffic.
