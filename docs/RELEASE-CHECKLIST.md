# FleetPilot Production Release Checklist

Release rule: production is not PASS until every required gate has direct evidence from the committed release candidate.

## Source and provenance
- [x] Clean Git baseline committed from verified Batch 14/15 state (`22f3b368396385f1533b356f9a3b6e22efc75d3b`).
- [x] Git author identity explicitly configured by repository owner (`jbmodularcabinet-bot <jb.modularcabinet@gmail.com>`).
- [x] Remote repository connected (`https://github.com/jbmodularcabinet-bot/fleetpilot.git`, `main` tracking `origin/main`).
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
- [x] Remote CI reproduces the committed verification suite (GitHub Actions `Foundation checks` PASS on commit `25199581c505f62c68602dc38b7b36882063aceb`).

## Deployment and operations
- [x] Production Docker images build and run successfully (API readiness 200; web login 200; web→API unauthenticated proxy 401 on clean Docker PostgreSQL 18 network).
- [ ] Registry image digests recorded and pinned for release. Local content-addressed image IDs recorded: API `sha256:0dcf3dad6f85f0825b9ec8f953dfc070bc5323bfab2aa39621407ebd5a4f5caa`; web `sha256:26a3afe509ccbd81536dd7b4a8d873e8c3d88f6c26d5c5c861c08801acdae020`.
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