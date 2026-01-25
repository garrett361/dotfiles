---
name: review
description: Review a GitHub pull request for quality, security, and best practices
context: fork
agent: Explore
allowed-tools: Bash(gh:*)
---

# Code Review Workflow

Review the GitHub pull request with focus on:

1. **Code Quality**
   - Readability and clarity
   - Adherence to project conventions (check CLAUDE.md)
   - Proper error handling
   - Function/variable naming

2. **Security**
   - No hardcoded secrets or credentials
   - Input validation and sanitization
   - No SQL injection or XSS vulnerabilities
   - Proper authentication/authorization

3. **Performance**
   - Algorithmic efficiency
   - Resource usage
   - Unnecessary computations

4. **Best Practices**
   - Test coverage
   - Documentation updates
   - Breaking changes
   - Backward compatibility

## Review Process

PR Number/URL: $ARGUMENTS

First, fetch the PR information:

```bash
# Get PR details
gh pr view $ARGUMENTS --json title,body,author,baseRefName,headRefName

# View the diff
gh pr diff $ARGUMENTS

# Get PR comments if any
gh pr view $ARGUMENTS --comments
```

Then analyze the changes thoroughly.

## Output Format

Organize findings by severity:

- **Critical Issues** (must fix)
- **Warnings** (should fix)
- **Suggestions** (nice to have)

Include specific file names, line numbers, and code examples for each finding.

Provide constructive feedback with explanations and suggested fixes.
