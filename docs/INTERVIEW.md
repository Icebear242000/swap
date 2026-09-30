# Talking points

Know these well enough to explain without notes.

1. **Why not scrape on each scan?** Slow, fragile, and often against site terms. Bulk records
   change slowly, so they're loaded on a schedule; products are fetched once and cached.
2. **The name-matching trade-off.** False matches are worse than misses here, because a false
   match accuses a company of something it didn't do. So matching is exact-after-normalization,
   or fuzzy only with a shared first token, 3/4 token overlap, and no close runner-up.
3. **Unknown is not pass.** The `datasets` table is how the app knows whether "no records" means
   anything. Walk through `check_workers` in `swap/checkpoints.py`.
4. **Graph traversal.** Ownership is a directed graph that can contain cycles and multiple
   parents in volunteer data. `chain_for` walks up with a seen-set and a depth cap;
   `descendants` does BFS down to find sibling brands.
5. **Ranking.** Required checkpoints gate; importance weights score (pass 1, unknown 0.4,
   fail 0); ties break on recalls, then unverified count, then price per ounce.
6. **Resilience.** Every outside call has a timeout and retries and degrades to "unknown".
7. **What I'd do next.** More categories; OCR of ingredient labels for products missing from
   Open Beauty Facts; a scheduled job to refresh records; Postgres if multiple writers appear;
   run the OSHA loader on the real multi-GB files; a reviewed list of manual aliases.

## What testing against real data found

The adapters were first written against sample responses. Running them against the live
services found problems the samples couldn't show. Each fix has a test built on a recorded real
response (fixtures ending in `_real`), written so it failed before the fix.

8. **Recorded samples hide real quirks.** Open Beauty Facts sometimes returns HTML-escaped text
   (users saw a literal "&gt;&gt;"), so I decode it at the adapter, where outside data enters;
   the UI still escapes on output. openFDA answers 400 to any non-ASCII search, so "Marque
   Repère" was silently never searched; I fold accents first. DOL's WHD download had moved to a
   new portal, uses uppercase headers while its own docs are lowercase, and ships as 8 chunks.
9. **Brands are not legal entities.** Labor and recall records name employers and firms. Matching
   them against brand names too turned "C.R.E.S.T., Inc", a care provider with 77 violations and
   $69k in back wages, into Crest, and so into Procter & Gamble; three unrelated "AIM"
   companies matched too. Records now match companies only; a brand still sees its parent's
   records through the ownership chain. WHD matches went from 17 to 10, all correct.
10. **A missing edge in volunteer data is not evidence.** "Signal" matched three Wikidata items,
    and the first was a record label with no owner, so Signal, a Unilever toothpaste, showed as
    independent. Now a name matching several items is skipped, and a Wikidata brand with no
    listed owner is "unknown". PASS needs a checked fact.
11. **A partial load must not look complete.** Marking the WHD dataset loaded per chunk would let
    a company whose cases sit in an unloaded chunk read "no cases". `load-whd` takes every chunk
    and marks the dataset once.
12. **The trade-offs I accepted.** These rules cost real matches: "Haleon US Holdings LLC" and
    "Dabur India Limited" recalls, Lidl US labor cases, GlaxoSmithKline ownership. They show as
    "unknown". A miss is honest; a false match accuses a company of something it didn't do. The
    fix for misses is a reviewed manual alias list (the `aliases` table already supports it), not
    looser matching.
