"""Compatibility exports for document jobs and their explicit HTTP registration."""
from .text_inspection.document_jobs import DocumentJobs
from .text_inspection.document_api import register

__all__ = ["DocumentJobs", "register"]
