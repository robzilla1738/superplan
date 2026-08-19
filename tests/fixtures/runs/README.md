# Supergoal v1 Fixture Runs

These fixtures document the four run shapes the kernel should keep supporting:

- `clean-success/` - all gates and audit pass.
- `audit-gap-fixed/` - audit found a gap, a focused fix ran, then audit passed.
- `blocked-run/` - recovery exhausted and the run stopped without completion.
- `scope-drift/` - a phase gate found edits outside `allowed_paths`.

The shell fixture test builds throwaway git repos dynamically because `repo-state.sh`
needs a real baseline commit. These static fixtures are intentionally lightweight
examples for docs, future tests, and report-gallery work.
