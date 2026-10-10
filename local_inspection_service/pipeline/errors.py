"""Shared pipeline cancellation signal; one class for all applications."""

class PipelineAdvanceCancelled(Exception):
    """Raised inside advance_pipeline_task when the task's cancel event fires."""
