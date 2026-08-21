from settings import DEFAULTS


def request_options(overrides=None):
    """Build options for an HTTP client whose timeout parameter is in seconds."""
    config = {**DEFAULTS, **(overrides or {})}
    return {
        "timeout": config["timeout_ms"],
        "retries": config["retries"],
    }
