---
name: query
description: Query a codebase with concise answers, code references, and ASCII diagrams
context: fork
agent: Explore
---

# Codebase Query

Answer the following question about this codebase:

**Question:** $ARGUMENTS

## Response Guidelines

1. **Lead with the answer** - State the direct answer in 1-2 sentences before elaborating

2. **Reference code locations** - Always use `file_path:line_number` format
   - Example: `src/auth/login.py:42`
   - Include 2-3 key snippets maximum, not exhaustive listings

3. **Use ASCII diagrams** when explaining:
   - Architecture or component relationships
   - Data flow or request/response cycles
   - Class hierarchies or module dependencies
   - State machines or workflows

   Example:
   ```
   Request --> Router --> Controller --> Service --> DB
                  |                          |
                  v                          v
              Middleware              Cache Layer
   ```

4. **Be concise** - Avoid boilerplate explanations. Assume the reader knows the language/framework basics.

## Search Strategy

- Start with targeted searches based on likely file/function names
- Check CLAUDE.md and README for project conventions
- Follow imports and references to trace data flow
- Look for tests to understand intended behavior
