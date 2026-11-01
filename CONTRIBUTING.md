# Contributing

Work in the existing shared Python services/contracts and React UI. Keep behaviours in one module, validate at boundaries, use short documented public functions, and explain non-obvious decisions in comments. Do not add a new service for functionality the current API/worker can own.

Configuration and secrets belong in environment variables. Put parameterised SQL in named `_SQL_*` constants at the top of a module. Append migrations; never edit a migration already released/applied outside disposable development. Preserve tenant-aware constraints and RLS. API credentials never go in the UI bundle.

Run Ruff, the PostgreSQL integration suite, SDK tests, TypeScript/Vite build and affected browser tests. Update dependency locks/notices with dependency changes. Tests must exercise behaviour and isolation, not merely duplicate implementation.

The approved roadmap is US10000 in AgentDesk. Keep partially implemented items in progress; move an item to review only when its acceptance criteria have been verified. External credentials, missing container verification and incomplete integrations must remain visible in the handoff.
