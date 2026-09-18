# ADR-001 — Small npm workspace monorepo

Status: accepted for Batch 2.

There is no previous implementation to preserve. Use Next.js in `apps/web`, FastAPI in `apps/api`, and small shared UI/types/auth-display/config packages. Python dependencies use a project-local venv and a fully pinned requirements file; npm uses a workspace lockfile.

This keeps server-authoritative logic in Python while sharing the owner/driver design system. No microservices, queue or native app is introduced. A real embedded PostgreSQL process supports local tests without Docker; a container alternative is supplied. Production remains ordinary PostgreSQL.
