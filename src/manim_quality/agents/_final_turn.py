"""Provider-neutral reminder for the final available model round."""


def final_turn_reminder(enabled: bool) -> dict[str, object]:
    if not enabled:
        return {}
    return {
        "continue_": True,
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": (
                "This is the final available model round. Stop new diagnosis and "
                "submit the current best conclusion through StructuredOutput now. "
                "Do not invent evidence or claim unsupported fixes."
            ),
        },
    }
