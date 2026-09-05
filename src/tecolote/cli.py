from __future__ import annotations

import argparse
import getpass
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from . import __version__
from .config import default_template, load_config, masked_config, validate_config, write_json_secure
from .doctor import run_doctor
from .drafts import create_draft, parse_extra
from .errors import TecoloteError, ValidationError
from .money import format_money
from .paths import config_path
from .service import commit_draft
from .state import load_state


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ValidationError("CLI_USAGE_ERROR", message)


def _parser() -> Parser:
    parser = Parser(prog="tecolote", description="Deterministic invoice generation CLI")
    parser.add_argument("--version", action="store_true", help="show version and exit")
    subcommands = parser.add_subparsers(dest="command")

    subcommands.add_parser("doctor", help="validate installation readiness")

    config = subcommands.add_parser("config", help="manage configuration")
    config_commands = config.add_subparsers(dest="config_command", required=True)
    config_commands.add_parser("show", help="show masked configuration")
    init = config_commands.add_parser("init", help="initialize configuration")
    init.add_argument("--from", dest="source", type=Path, help="validated JSON configuration to install")
    init.add_argument("--non-interactive", action="store_true", help="write a sanitized starter configuration")
    init.add_argument("--force", action="store_true", help="replace an existing configuration")

    draft = subcommands.add_parser("draft", help="calculate and persist a reviewable invoice draft")
    draft.add_argument("--month", required=True, help="invoice month in YYYY-MM format")
    draft.add_argument("--extra", action="append", default=[], help="DESCRIPTION=AMOUNT[:assignment]")
    draft.add_argument("--issue-date", help="monthly issue date in YYYY-MM-DD format")
    draft.add_argument("--first-date", help="first twice-monthly issue date")
    draft.add_argument("--second-date", help="second twice-monthly issue date")

    commit = subcommands.add_parser("commit", help="generate the exact reviewed draft")
    commit.add_argument("draft_id")

    history = subcommands.add_parser("history", help="show committed invoice history")
    history.add_argument("--limit", type=int, default=None, help="show only the newest N records")
    return parser


def _public_draft(draft: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "draftId": draft["draftId"],
        "createdAt": draft["createdAt"],
        "month": draft["month"],
        "schedule": draft["schedule"],
        "expectedNextInvoiceNumber": draft["expectedNextInvoiceNumber"],
        "invoices": draft["invoices"],
    }


def _interactive_config() -> dict[str, Any]:
    template = default_template()
    print("Tecolote configuration (sensitive answers are written only to the local config file).")
    template["user"]["fullName"] = input("Full name: ").strip()
    template["bank"]["bank"] = input("Bank: ").strip()
    template["bank"]["bankAddress"] = input("Bank address: ").strip()
    template["bank"]["accountName"] = input("Account name: ").strip()
    template["bank"]["swift"] = input("SWIFT: ").strip()
    template["bank"]["accountNumber"] = getpass.getpass("Account number (hidden): ").strip()
    template["bank"]["signaturePath"] = input(
        f"Signature PNG [{template['bank']['signaturePath']}]: "
    ).strip() or template["bank"]["signaturePath"]
    template["compensation"]["monthlyCents"] = int(input("Monthly compensation in cents: ").strip())
    template["compensation"]["currency"] = input("Currency [USD]: ").strip() or "USD"
    template["compensation"]["schedule"] = input("Schedule [monthly/twice-monthly]: ").strip()
    template["client"]["companyName"] = input("Client company name: ").strip()
    template["client"]["companyAddress"] = input("Client company address: ").strip()
    template["invoice"]["initialNextNumber"] = int(input("Initial next invoice number: ").strip())
    template["invoice"]["outputDirectory"] = input(
        f"Output directory [{template['invoice']['outputDirectory']}]: "
    ).strip() or template["invoice"]["outputDirectory"]
    return template


def _config_init(args: argparse.Namespace) -> dict[str, Any]:
    target = config_path()
    if target.exists() and not args.force:
        raise ValidationError("CONFIG_EXISTS", f"Configuration already exists at {target}; use --force to replace it.")
    if args.source:
        try:
            raw = json.loads(args.source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValidationError("CONFIG_INVALID", "Source configuration is unreadable or invalid JSON.") from exc
        config = validate_config(raw, args.source)
        mode = "installed"
    elif args.non_interactive:
        config = validate_config(default_template(), target)
        mode = "starter"
    else:
        if getattr(args, "json_mode", False):
            raise ValidationError(
                "CLI_USAGE_ERROR", "JSON mode requires 'config init --from FILE' or '--non-interactive'."
            )
        try:
            config = validate_config(_interactive_config(), target)
        except ValueError as exc:
            raise ValidationError("CONFIG_INVALID", "A numeric configuration value was invalid.") from exc
        mode = "interactive"
    write_json_secure(target, config)
    return {
        "ok": True,
        "path": str(target),
        "mode": mode,
        "message": "Configuration created. Add the configured signature and run 'tecolote doctor'.",
    }


def _dispatch(args: argparse.Namespace) -> dict[str, Any]:
    if args.version:
        return {"ok": True, "version": __version__}
    if args.command == "doctor":
        return run_doctor()
    if args.command == "config" and args.config_command == "init":
        return _config_init(args)
    if args.command == "config" and args.config_command == "show":
        config = load_config()
        state = load_state(int(config["invoice"]["initialNextNumber"]))
        return {"ok": True, "config": masked_config(config, int(state["nextInvoiceNumber"]))}
    if args.command == "draft":
        config = load_config()
        state = load_state(int(config["invoice"]["initialNextNumber"]))
        extras = [parse_extra(value) for value in args.extra]
        return _public_draft(
            create_draft(
                config,
                args.month,
                int(state["nextInvoiceNumber"]),
                extras,
                args.issue_date,
                args.first_date,
                args.second_date,
            )
        )
    if args.command == "commit":
        return commit_draft(args.draft_id)
    if args.command == "history":
        if args.limit is not None and args.limit < 1:
            raise ValidationError("CLI_USAGE_ERROR", "--limit must be a positive integer.")
        config = load_config()
        state = load_state(int(config["invoice"]["initialNextNumber"]))
        records = list(state["history"])
        if args.limit is not None:
            records = records[-args.limit :]
        return {"ok": True, "history": records, "nextInvoiceNumber": state["nextInvoiceNumber"]}
    raise ValidationError("CLI_USAGE_ERROR", "A command is required.")


def _human(result: dict[str, Any]) -> str:
    if "version" in result:
        return f"Tecolote CLI {result['version']}"
    if "checks" in result:
        lines = ["Tecolote CLI", ""]
        for name, check in result["checks"].items():
            lines.append(f"{name:<20} {'OK' if check['ok'] else 'FAIL'}")
            if not check["ok"] and check.get("message"):
                lines.append(f"  {check['message']}")
        lines.extend(["", "Ready." if result["ok"] else "Not ready."])
        return "\n".join(lines)
    if "config" in result:
        config = result["config"]
        return "\n".join(
            [
                "Tecolote configuration",
                f"Name: {config['user']['fullName']}",
                f"Client: {config['client']['companyName']}",
                f"Schedule: {config['compensation']['schedule']}",
                f"Monthly: {format_money(config['compensation']['monthlyCents'], config['compensation']['currency'])}",
                f"Account: {config['bank']['accountNumber']}",
                f"Next invoice: {config['invoice']['nextNumber']}",
                f"Output: {config['invoice']['outputDirectory']}",
            ]
        )
    if "draftId" in result and "expectedNextInvoiceNumber" in result:
        lines = [f"Draft {result['draftId']} ({result['schedule']}, {result['month']})"]
        for invoice in result["invoices"]:
            lines.append(
                f"Invoice {invoice['invoiceNumber']}: {invoice['period']}, {invoice['issueDate']}, "
                f"{invoice['totalCents']} minor units"
            )
        lines.append(f"Commit with: tecolote commit {result['draftId']}")
        return "\n".join(lines)
    if "draftId" in result:
        lines = [f"Committed draft {result['draftId']}:"]
        lines.extend(f"Invoice {row['invoiceNumber']}: {row['outputPath']}" for row in result["invoices"])
        return "\n".join(lines)
    if "history" in result:
        if not result["history"]:
            return "No committed invoices."
        return "\n".join(
            f"#{row['invoiceNumber']} {row['month']} {row['period']} {row['totalCents']} minor units -> {row['outputPath']}"
            for row in result["history"]
        )
    return str(result.get("message", "OK"))


def main(argv: Sequence[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    json_mode = "--json" in raw
    raw = [argument for argument in raw if argument != "--json"]
    try:
        parser = _parser()
        if json_mode and any(argument in {"-h", "--help"} for argument in raw):
            print(json.dumps({"ok": True, "help": parser.format_help()}, ensure_ascii=True, separators=(",", ":")))
            return 0
        args = parser.parse_args(raw)
        args.json_mode = json_mode
        result = _dispatch(args)
        if json_mode:
            print(json.dumps(result, ensure_ascii=True, separators=(",", ":")))
        else:
            print(_human(result))
        return 0 if result.get("ok", True) else 2
    except TecoloteError as exc:
        error: dict[str, Any] = {"code": exc.code, "message": exc.message}
        if exc.details:
            error["details"] = exc.details
        if json_mode:
            print(json.dumps({"ok": False, "error": error}, ensure_ascii=True, separators=(",", ":")))
        else:
            print(f"Error [{exc.code}]: {exc.message}", file=sys.stderr)
        return exc.exit_code
    except KeyboardInterrupt:
        if json_mode:
            print(json.dumps({"ok": False, "error": {"code": "INTERRUPTED", "message": "Operation interrupted."}}))
        else:
            print("Operation interrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
