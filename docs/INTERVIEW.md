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
   Open Beauty Facts; a scheduled job to refresh records; Postgres if multiple writers appear.
