"""Errors that map to the CLI exit codes in contracts/cli.md."""

from __future__ import annotations


class HipstrawError(Exception):
    exit_code = 1


class UsageError(HipstrawError):
    exit_code = 1


class ConfigError(HipstrawError):
    exit_code = 1


class PreconditionError(HipstrawError):
    exit_code = 2


class ExternalServiceError(HipstrawError):
    exit_code = 3


class BudgetExhaustedError(HipstrawError):
    exit_code = 4
