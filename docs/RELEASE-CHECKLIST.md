# FleetPilot Production Release Checklist

Release rule: production is not PASS until every required gate has direct evidence from the committed release candidate.

## Source and provenance
- [ ] Clean Git baseline committed from verified Batch 14/15 state.
- [ ] Git author identity explicitly configured by repository owner.
- [ ] Remote repository connected.
- [ ] Protected default branch / review policy configured.
- [ ] Release candidate tag created after regression PASS.

## Automated verification
- [x] TypeScript check passes locally.
- [x] ESLint passes locally.
- [x] Production Next.js build passes with explicit API_INTERNAL_URL.
- [x] Full backend regression passes from current Batch 15 candidate (371/371 continuous PASS in 8m 51s).
- [x] Full frontend regression passes from current Batch 15 candidate (54/54).
- [x] Full browser regression passes continuously from current Batch 15 candidate (37/37 PASS after offline reconnect stabilization; targeted reconnect stress 5/5 PASS).
- [x] Migration forward / rollback / reapply passes from current head (0012 → 0011 → 0012).
- [ ] Remote CI reproduces the complete committed verification suite.

## Deployment and operations
- [ ] Production Docker images build and run successfully.
- [ ] Image digests recorded and pinned for release.
- [ ] Public HTTPS staging frontend/API verified.
- [ ] Production private object storage/IAM verified.
- [ ] External monitoring and alert delivery verified.
- [ ] Remote backup and restore drill verified.
- [ ] Staging load check completed with recorded results.

## Security and device acceptance
- [ ] Deployed tenant isolation verified.
- [ ] Deployed role/capability isolation verified.
- [ ] Cross-driver direct-ID denial verified.
- [ ] Physical Android workflow verified.
- [ ] Actual Safari/iOS workflow verified.
- [ ] Independent security review completed or explicitly accepted as launch risk.

## Final gate
- [ ] Final release report issued as PASS / CONDITIONAL PASS / FAIL.
- [ ] No unresolved P0/P1 defects.
- [ ] Rollback procedure and recovery evidence attached.
- [ ] Production release explicitly approved.