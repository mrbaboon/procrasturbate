"""Claude API client for code reviews."""

import json
from dataclasses import dataclass

import anthropic

from ..config import settings
from ..schemas.repo_config import ReviewConfig

REVIEW_SYSTEM_PROMPT = """You are an expert code reviewer. Review the provided pull request diff and provide:

1. A summary of the changes (2-3 sentences)
2. An overall risk level: low, medium, high, or critical
3. Specific comments on issues you find

For each comment, provide:
- file: The file path
- line: The line number in the NEW version of the file (not the old version)
- severity: critical, warning, suggestion, or nitpick
- category: One of: security, bug, performance, style, documentation, maintainability
- message: Clear explanation of the issue
- suggested_fix: (optional) Code suggestion to fix the issue

Focus on:
{focus_areas}

Additional context about this codebase:
{additional_context}

{custom_instructions}

Respond with valid JSON in this exact format:
{{
  "summary": "Brief summary of the PR",
  "risk_level": "low|medium|high|critical",
  "comments": [
    {{
      "file": "path/to/file.py",
      "line": 42,
      "severity": "warning",
      "category": "security",
      "message": "Explanation of the issue",
      "suggested_fix": "Optional code fix"
    }}
  ]
}}

If the code looks good with no issues, return an empty comments array.
Only comment on lines that exist in the diff (additions or context lines).
Do not comment on removed lines."""


@dataclass
class ClaudeReviewResponse:
    """Structured response from Claude."""

    summary: str
    risk_level: str  # low, medium, high, critical
    comments: list[dict]  # [{file, line, severity, category, message, suggested_fix?}]
    input_tokens: int
    output_tokens: int


class ClaudeClient:
    """Client for Claude code review API."""

    def __init__(self) -> None:
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def review_diff(
        self,
        diff_content: str,
        pr_title: str,
        pr_description: str | None,
        config: ReviewConfig,
        context_content: str | None = None,
    ) -> ClaudeReviewResponse:
        """Generate a review for the given diff."""
        # Build focus areas from config
        focus_areas: list[str] = []
        if config.rules.security:
            focus_areas.append("- Security vulnerabilities, injection risks, auth issues")
        if config.rules.performance:
            focus_areas.append(
                "- Performance problems, inefficient algorithms, N+1 queries"
            )
        if config.rules.style:
            focus_areas.append("- Code style, naming conventions, readability")
        if config.rules.bugs:
            focus_areas.append("- Logic errors, edge cases, null handling")
        if config.rules.documentation:
            focus_areas.append("- Missing or outdated documentation, unclear code")

        for name, description in config.rules.custom.items():
            focus_areas.append(f"- {name}: {description}")

        # Build context
        additional_context = ""
        if config.languages:
            additional_context += f"Languages: {', '.join(config.languages)}\n"
        if config.frameworks:
            additional_context += f"Frameworks: {', '.join(config.frameworks)}\n"
        if context_content:
            additional_context += f"\nRepository documentation:\n{context_content}\n"

        system_prompt = REVIEW_SYSTEM_PROMPT.format(
            focus_areas="\n".join(focus_areas) if focus_areas else "General code quality",
            additional_context=additional_context or "No additional context provided.",
            custom_instructions=config.additional_instructions or "",
        )

        description_section = ""
        if pr_description:
            description_section = f"\n## Description\n{pr_description}"

        user_message = f"""# Pull Request: {pr_title}
{description_section}

## Diff

```diff
{diff_content}
```

Please review this pull request and provide your analysis as JSON."""

        model = config.model or settings.default_model

        response = await self.client.messages.create(
            model=model,
            max_tokens=settings.max_tokens_per_review,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )

        # Parse response
        response_text = response.content[0].text

        # Handle potential markdown code blocks
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0]
        elif "```" in response_text:
            parts = response_text.split("```")
            if len(parts) >= 2:
                response_text = parts[1]

        try:
            data = json.loads(response_text.strip())
        except json.JSONDecodeError:
            # Fallback if JSON parsing fails
            data = {
                "summary": (
                    "Failed to parse structured response. Raw output: "
                    + response_text[:500]
                ),
                "risk_level": "medium",
                "comments": [],
            }

        return ClaudeReviewResponse(
            summary=data.get("summary", ""),
            risk_level=data.get("risk_level", "medium"),
            comments=data.get("comments", []),
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
