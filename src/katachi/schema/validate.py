from katachi.validation.core import ValidationReport


def format_validation_results(report: ValidationReport) -> str:
    """Format validation results into a user-friendly message."""
    return report.format_report()
