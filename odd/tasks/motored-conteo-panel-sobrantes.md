# Motored: "Sobrantes" tab on the leader panel (NOTED, not started)

## Request (owner, 2026-10-10)

Add a tab on the leader's differences table, like "Críticas", that lists surpluses: references where contado is greater than sistema. A surplus is positive, but it is still an inventory mismatch the leader must review.

## Verified facts

- Surpluses already trigger reconteo and become critical exactly like shortages. `diferencias.py:193` and `:197` compare `abs(valor)` against the thresholds.
- What is missing is only a way to see them apart: chips today are Todas / Críticas / En reconteo / Contadas.

## Proposal to confirm before building

- A chip "Sobrantes (N)" with diferencia > 0, ordered by value descending.
- Open question for the owner: should "Faltantes (N)" be added too, for symmetry?

## Status

Waiting for the owner's go-ahead. Do not build until approved.
