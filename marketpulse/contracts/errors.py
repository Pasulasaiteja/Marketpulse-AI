"""Failure type every module raises so the API can degrade honestly."""

from __future__ import annotations


class ModuleFailure(Exception):
    """Raised by any pipeline module on failure.

    ``module`` is one of: extractor, context, forecaster, optimizer, explainer, signals.
    """

    def __init__(self, module: str, code: str, message: str, retryable: bool = False):
        super().__init__(f"[{module}] {code}: {message}")
        self.module = module
        self.code = code
        self.message = message
        self.retryable = retryable
