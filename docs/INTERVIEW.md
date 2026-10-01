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
   run the OSHA loader on the real multi-GB files; a reviewed list of manual aliases;
   supply-chain forced labor from official lists (UFLPA Entity List, CBP Withhold Release
   Orders); state environmental enforcement and climate data; judging only companies with a
   known US presence on US-only records.

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
10. **Don't guess an entity from a name.** "Signal" matched three Wikidata items, and the first
    was a record label. Picking one would attach the wrong company to a Unilever toothpaste,
    and with it the wrong company's records. Now a name matching several items is skipped and
    stays "unknown".
11. **A partial load must not look complete.** Marking the WHD dataset loaded per chunk would let
    a company whose cases sit in an unloaded chunk read "no cases". `load-whd` takes every chunk
    and marks the dataset once.
12. **The trade-offs I accepted.** These rules cost real matches: "Haleon US Holdings LLC" and
    "Dabur India Limited" recalls, Lidl US labor cases, GlaxoSmithKline ownership. They show as
    "unknown". A miss is honest; a false match accuses a company of something it didn't do. The
    fix for misses is a reviewed manual alias list (the `aliases` table already supports it), not
    looser matching.
13. **Why I removed the "Independent brand" checkpoint.** Real data broke it: some products list
    the parent company itself as the brand ("Colgate-Palmolive", "Haleon", "Unilever"), so they
    have no parent and passed as independent, and every product's top swaps included one. The
    deeper problem was the question itself: being big or owned by someone isn't wrongdoing.
    Checkpoints now judge conduct backed by records (does it work, what's in it, how the company
    treats workers), and ownership is shown as information and used to find the parent
    company's records. Hiding same-owner swaps is still available, as an opt-in filter.
14. **Designing the environmental record from what the data actually says.** I looked at EPA's
    real cases for the tracked companies before writing rules. Most were Superfund cleanup
    cases naming 100 to 400 companies each; liability there doesn't depend on wrongdoing, so I
    excluded them. The recent cases were chemical reporting and pesticide labeling, not
    pollution: Colgate-Palmolive paid $930,000 in 2026 for failing to report 47 chemicals. So
    the checkpoint is named "Environmental record" and described as federal compliance, not
    climate impact, which the data can't show. Fail is $100,000+ in penalties in 5 years
    (config), only concluded cases count, and a quirk mattered: the case file's penalty column
    is blank on recent cases, so amounts come from a separate penalties file.
