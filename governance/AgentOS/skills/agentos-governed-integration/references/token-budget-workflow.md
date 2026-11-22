# Token Budget Workflow

Use `protocols/TOKEN-BUDGET.md` for the full contract. This reference defines
the repeatable workflow used by `meta-token-budget`.

1. **Baseline**: measure the same client/profile/task mix before changing it.
2. **Locate the multiplier**: inspect prefix, tool-result and output shares;
   do not optimize schema or cache without evidence.
3. **Choose the smallest intervention**: selective reads, bounded output,
   batching and durable artifacts before client-specific compression knobs.
4. **Protect evidence**: classify data; save approved bulky output with SHA256
   before eviction; preserve user messages and tool-call parameters.
5. **Compare**: rerun the same task mix and record raw observations, not only a
   percentage.
6. **Quality gate**: use the task's existing acceptance and evidence checks.
7. **Promote or roll back**: promote only measured, quality-preserving changes;
   otherwise restore the pre-change configuration and record the failure.

The 50% objective is a target for measured improvement. It is not permission to
fabricate provider charges, weaken governance, or claim client behavior that has
not been observed.
