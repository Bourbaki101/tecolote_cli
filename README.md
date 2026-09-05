# Tecolote CLI

Tecolote CLI is a deterministic, headless invoice engine for Ubuntu 24.04 LTS. It is designed for humans and agent callers: an agent interprets intent, while Tecolote owns dates, integer-safe money, invoice numbering, PDF generation, filenames, and durable local history.

This is independent from the Tecolote Windows/Tauri application. It contains no GUI, server, daemon, MCP implementation, or AI/API integration.

## Architecture

The installed `tecolote` command calls a small Python package:

```text
src/tecolote/
  cli.py        argparse interface, JSON/human output, stable exit behavior
  config.py     validation, masking, secure atomic JSON writes
  periods.py    calendar/month/leap-year rules
  money.py      Decimal input parsing and integer-minor-unit arithmetic
  drafts.py     plan calculation and immutable persisted snapshots
  service.py    locked, collision-safe transactional commit workflow
  renderer.py   fixed-layout A4 ReportLab PDF renderer
  state.py      XDG state, history, current number, process lock
  doctor.py     readiness diagnostics
```

ReportLab was chosen instead of Chromium or WeasyPrint. The supplied reference is a fixed one-page A4 document, so direct vector drawing gives close layout control, deterministic output, a modest dependency set, and no browser/native rendering service on a VPS. Poppler is useful for developer visual QA but is not a production dependency.

## Ubuntu 24.04 installation

Install the operating-system prerequisites once:

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-venv
```

Then install or upgrade Tecolote without root:

```bash
git clone <your-tecolote-cli-repository-url> tecolote-cli
cd tecolote-cli
chmod +x install.sh
./install.sh
```

The installer creates `~/.local/share/tecolote/venv`, installs the current checkout, and links `tecolote` into `~/.local/bin`. It is safe to rerun for upgrades and never overwrites configuration. Ensure `~/.local/bin` is on `PATH`.

For a later update:

```bash
cd tecolote-cli
git pull --ff-only
./install.sh
```

## Configuration and sensitive data

Linux locations follow XDG conventions:

- Configuration: `${XDG_CONFIG_HOME:-~/.config}/tecolote/config.json`
- Signature: normally `${XDG_CONFIG_HOME:-~/.config}/tecolote/signature.png`
- State/history/drafts: `${XDG_STATE_HOME:-~/.local/state}/tecolote/`
- Default invoices: `~/Documents/Tecolote/Invoices/`

`TECOLOTE_CONFIG_HOME`, `TECOLOTE_CONFIG_FILE`, and `TECOLOTE_STATE_HOME` can override locations for isolated automation or testing.

Start interactively:

```bash
tecolote config init
```

For automation, prepare a JSON file based on `config.example.json`, then install it noninteractively:

```bash
tecolote config init --from /secure/path/config.json
install -m 600 /secure/path/signature.png ~/.config/tecolote/signature.png
tecolote doctor --json
```

`tecolote config init --non-interactive` writes a fake starter configuration that must be edited before use. Existing configuration is refused unless `--force` is explicit. Tecolote creates config/state directories with mode `0700` and JSON files with mode `0600` where the platform supports POSIX modes. Use `chmod 700 ~/.config/tecolote ~/.local/state/tecolote` and `chmod 600 ~/.config/tecolote/config.json ~/.config/tecolote/signature.png` if migrating files manually.

Local `asset/`, PDFs, config variants, signatures, environments, logs, caches, and renderer scratch files are ignored by Git. The repository example and tests contain fake values only. `config show` always masks the account number and signature path.

Configuration money is stored as integer minor units. For example, `217000` is USD 2,170.00. The current invoice number lives in state; `invoice.initialNextNumber` is used only when state is first created.

## Commands

```bash
tecolote --version
tecolote doctor
tecolote doctor --json
tecolote config init
tecolote config init --from /secure/path/config.json
tecolote config show --json
tecolote draft --month 2026-09 --json
tecolote commit <draft-id> --json
tecolote history --json
tecolote history --limit 10
```

`--json` may appear anywhere. In JSON mode stdout contains one valid JSON document with no decoration, color, or emoji.

## Draft and commit

Drafting validates and calculates, then persists a snapshot under the state directory. It does not generate PDFs, advance numbering, or create history.

```bash
tecolote draft --month 2026-09 --extra "SLA Bonus=50" --json
tecolote commit 0123456789abcdef --json
```

Commit reloads that exact snapshot under a process lock. If the expected next number has changed, it returns `DRAFT_CONFLICT`; it never silently recalculates. All PDFs are rendered to staging first, output collisions are checked, and files are atomically published without overwrite. State and history advance only after all expected PDFs exist. A render or state-write failure removes any files published by that attempt and preserves numbering.

Monthly schedule creates one PDF containing two equal service lines, with a default issue date on day 16. Twice-monthly creates two numbered PDFs, one for days 1-15 (default date 10) and one for days 16 through the calendar-derived last day (default date 20).

Monthly date override:

```bash
tecolote draft --month 2026-09 --issue-date 2026-09-18 --json
```

Twice-monthly date overrides:

```bash
tecolote draft --month 2026-09 --first-date 2026-09-11 --second-date 2026-09-21 --json
```

## Extras

Amounts passed on the CLI are major units and accept up to two decimal places. All internal and JSON amounts are minor-unit integers.

```bash
# Monthly
tecolote draft --month 2026-09 --extra "SLA Bonus=50" --extra "Bank Fee=25.00" --json

# Twice-monthly: assignment is required
tecolote draft --month 2026-09 \
  --extra "Overtime=40:first" \
  --extra "SLA Bonus=50:both" \
  --extra "Reimbursement=12.50:second" \
  --json
```

`:both` adds the full amount to each invoice. It does not split the amount.

## Output and history

The default structure is:

```text
~/Documents/Tecolote/Invoices/2026/September/
  Invoice_011_September_2026.pdf
```

Twice-monthly filenames include `01-15` or the calculated second period, such as `16-30`. Existing paths are never overwritten. `tecolote history --json` reads lightweight history from the durable state JSON; PDFs remain ordinary files.

## JSON and errors

Success responses use `{"ok":true,...}`. Draft invoice data includes `invoiceNumber`, `issueDate`, `period`, `lines`, `baseCents`, `extrasCents`, `subtotalCents`, `taxCents`, `totalCents`, and `relativeOutputPath`. No private config snapshot is exposed in draft output.

Errors use:

```json
{
  "ok": false,
  "error": {
    "code": "DRAFT_CONFLICT",
    "message": "Invoice numbering changed after this draft was created; create a new draft.",
    "details": {
      "expectedNextInvoiceNumber": 11,
      "actualNextInvoiceNumber": 12
    }
  }
}
```

Stable codes include `CONFIG_NOT_FOUND`, `CONFIG_INVALID`, `SIGNATURE_NOT_FOUND`, `INVALID_MONTH`, `INVALID_DATE`, `INVALID_EXTRA`, `INVALID_AMOUNT`, `DRAFT_NOT_FOUND`, `DRAFT_INVALID`, `DRAFT_CONFLICT`, `OUTPUT_COLLISION`, `PDF_RENDER_FAILED`, and `FILESYSTEM_ERROR`.

Exit codes are `0` for success, `2` for validation/configuration/readiness failure, `3` for PDF rendering failure, `4` for filesystem failure, and `130` for interruption.

## Doctor and troubleshooting

`tecolote doctor --json` checks configuration parsing, signature readability, ReportLab availability, output writability, and state accessibility without revealing bank details.

- `CONFIG_NOT_FOUND`: run `tecolote config init` or install a validated file with `--from`.
- `SIGNATURE_NOT_FOUND`: verify `bank.signaturePath` and file permissions.
- `DRAFT_CONFLICT`: create a fresh draft and review it again.
- `OUTPUT_COLLISION`: reconcile the existing accounting file; Tecolote will not overwrite it.
- `PDF_RENDER_FAILED`: validate the signature PNG and reduce unusually large line-item counts.

The reference layout is intentionally one A4 page. An invoice with enough unusually long extra lines to collide with totals fails instead of shrinking text or producing an unreadable document.

## Tests and Linux validation

Local development:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
pytest
```

WSL2 Ubuntu uses the same commands. Work inside the Linux filesystem for predictable permissions, or access the checkout under `/mnt/c` for a quick compatibility run.

The Dockerfile executes the full suite while building on Ubuntu 24.04:

```bash
docker build --progress=plain -t tecolote-cli-test .
docker run --rm tecolote-cli-test --version
```

Docker is a validation aid only; production runs directly in the virtual environment created by `install.sh`.

## Agent workflow

A future Hermes skill should call `doctor --json` when needed, create a draft with `--json`, summarize only the returned public invoice fields, ask the human for confirmation, and call `commit <draftId> --json`. Hermes-specific code does not belong in this package.

Before connecting Hermes, install on the target Ubuntu VPS, create the real config/signature with restrictive permissions, run `doctor --json`, and complete one manually reviewed draft/commit cycle in a non-production output directory.
