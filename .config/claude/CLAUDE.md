# Global Coding Context & Preferences

## About Me
**Primary Languages**: Python (PyTorch/ML focus), less often Bash, lua, C++. 
**Editor**: Neovim
**OS**: macOS (local) and Linux (remote)
**Shell**: [zsh/bash]

## Default Coding Style

### Python
- **Formatter**: Black (88 char line length)
- **Linter**: ruff or flake8
- **Type Checking**: Use type hints, prefer mypy-compatible syntax
- **Docstrings**: Google style preferred
- **Imports**: Organize with isort (stdlib, third-party, local)
- **Async**: Use `asyncio` when suggesting concurrent operations

### General Principles
- Prefer explicit over implicit
- Write self-documenting code with clear variable names
- Keep functions small and focused (single responsibility)
- Write tests for non-trivial logic
- Use meaningful commit messages (conventional commits style)

## ML/PyTorch Specific

### Model Development
- Always include type hints for tensor shapes when practical
- Use `torch.nn.Module` for all models
- Prefer composition over inheritance for complex architectures
- Include shape assertions during development
- Default to `torch.float32` unless specified otherwise
- Always show device placement in examples

### Training Conventions
- Use mixed precision training by default (`torch.amp`)
- Include learning rate schedulers in training suggestions
- Show checkpoint saving/loading patterns
- Use experiment tracking (prefer Weights & Biases or TensorBoard)
- Always set random seeds for reproducibility

### Code Structure Preferences
- Data loading: Separate `Dataset` classes from model code
- Configuration: Use Hydra or OmegaConf for complex configs
- Logging: Use Python's `logging` module, not print statements
- Paths: Use `pathlib.Path` instead of string concatenation

## Development Environment

### Python Setup
- Package manager: uv prefererred, or else pip 
- Virtual environments: uv 
- Default Python version: 3.11 

### Tools I Use
- Version control: Git
- Container platform: Docker (if applicable)
- CI/CD: GitHub Actions

## Response Preferences

### Critical Thinking
- Doubt, question, scrutinize, and verify everything I say.
- Challenge assumptions and look for potential errors or inconsistencies.

### Code Suggestions
- **Show imports**: Always include necessary imports in code blocks
- **Add comments**: Include brief inline comments for complex logic, but prefer informative function
  and variable names over using comments at all.
- **Error handling**: Include try/except for I/O and external API calls
- **Logging**: Add appropriate logging statements
- **Testing**: Suggest test cases for new functionality

### Explanations
- Start with a brief summary
- Use examples to illustrate concepts
- For complex topics, break into steps
- Link to relevant documentation when helpful
- Assume I have ML/PyTorch knowledge but may need reminders on details

### What to Avoid
- Don't use deprecated PyTorch APIs (check for torch 2.0+)
- Avoid suggesting pip install without version constraints
- Don't assume GPU is always available
- Avoid overengineering simple solutions
- Skip boilerplate explanations for basic Python/PyTorch concepts
- Try to keep comments to a minimum. Prefer informative function and variable names.
- Do not include emojis in code or code comments.

## Common Tasks

### When I ask for model code:
1. Include full imports
2. Show initialization and forward pass
3. Add example input/output shapes as comments
4. Include device placement
5. Show basic training loop if asked

### When I ask for debugging help:
1. Check tensor shapes first
2. Verify gradient flow
3. Look for device mismatches (CPU/GPU)
4. Check for in-place operations that might break autograd
5. Suggest adding assertions/logging

### When suggesting refactors:
1. Maintain existing functionality
2. Improve readability first, performance second
3. Keep changes minimal and focused
4. Suggest tests for changed behavior
5. Note any breaking changes

## Project Types I Work On
- Computer vision (image classification, detection, segmentation)
- NLP/LLMs (fine-tuning, inference optimization)
- Model optimization (quantization, pruning, distillation)
- Research implementations (reproducing papers)
- Production ML pipelines

## Quick References

### Tensor Shape Comments Style
```python
# x: (batch, channels, height, width)
x = torch.randn(32, 3, 224, 224)
```

### Preferred Error Messages
Use descriptive assertions:
```python
assert x.dim() == 4, f"Expected 4D tensor, got {x.dim()}D with shape {x.shape}"
```

### Device Handling Pattern
```python
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
model = model.to(device)
```

---

**Note**: When suggesting code, assume I want production-quality code unless I specify "quick prototype" or "experiment".
