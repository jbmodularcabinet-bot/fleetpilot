# Known Limitations

1. FFmpeg is not currently available on PATH. This does not block Batches 0–8, but must be resolved before Batch 9 composition/export verification.
2. PowerShell script execution policy blocks npm.ps1; use npm.cmd. No system policy change is required.
3. Live AI provider credentials have not yet been configured. Batch 4 LIVE Creative Director adapter explicitly refuses execution rather than faking success; deterministic MOCK is used instead.
4. Git author identity has not been configured; do not invent commit attribution.
5. Brand Brain backend persistence is SQLite, but the React UI currently uses browser localStorage for editable draft persistence until the planned Tauri desktop bridge is introduced.
6. Creative Director authoritative generated/approved plans persist in SQLite, while the React Director UI uses localStorage for editable proposal drafts until the desktop bridge is introduced.
