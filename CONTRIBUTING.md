# Contributing to GraphSelect

Thank you for your interest in contributing to **GraphSelect** — an Automated Literature Review System that discovers relevant academic papers using citation graph traversal, Gemini embeddings, cosine similarity, and PageRank.

We welcome contributions of all kinds: bug fixes, new features, documentation improvements, and more.

---

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Docker Development Workflow](#docker-development-workflow)
- [Code Style Guidelines](#code-style-guidelines)
- [Running Tests](#running-tests)
- [Pull Request Process](#pull-request-process)
- [Reporting Issues](#reporting-issues)

---

## Code of Conduct

This project adheres to the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code. Please report unacceptable behavior as described in the Code of Conduct.

---

## Getting Started

1. **Fork** the repository on GitHub:
   ```
   https://github.com/HosamKsbaa/GraphSelect--Advancing-Research-Papers-Semantic-Search-with-Embedding-and-Knowledge-Graphs
   ```

2. **Clone** your fork locally:
   ```bash
   git clone https://github.com/<your-username>/GraphSelect--Advancing-Research-Papers-Semantic-Search-with-Embedding-and-Knowledge-Graphs.git
   cd GraphSelect--Advancing-Research-Papers-Semantic-Search-with-Embedding-and-Knowledge-Graphs
   ```

3. **Add the upstream remote** to stay in sync:
   ```bash
   git remote add upstream https://github.com/HosamKsbaa/GraphSelect--Advancing-Research-Papers-Semantic-Search-with-Embedding-and-Knowledge-Graphs.git
   ```

4. **Create a feature branch** from `main`:
   ```bash
   git checkout -b feature/your-feature-name
   ```

---

## Development Setup

### Prerequisites

- **Python 3.11+** (required)
- **pip** (Python package manager)
- **Docker & Docker Compose** (optional, for containerized development)
- A **Gemini API key** (for embedding functionality)

### Local Setup

1. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   
   # Windows
   venv\Scripts\activate
   
   # macOS / Linux
   source venv/bin/activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Configure environment variables:
   ```bash
   cp .env.example .env
   # Edit .env with your API keys and configuration
   ```

4. Start the development server:
   ```bash
   uvicorn code.main:app --reload --host 0.0.0.0 --port 8000
   ```

---

## Docker Development Workflow

For a fully containerized development environment:

1. **Build and start** all services:
   ```bash
   docker-compose up --build
   ```

2. **Run in detached mode**:
   ```bash
   docker-compose up -d
   ```

3. **View logs**:
   ```bash
   docker-compose logs -f
   ```

4. **Stop services**:
   ```bash
   docker-compose down
   ```

5. **Rebuild after dependency changes**:
   ```bash
   docker-compose build --no-cache
   docker-compose up
   ```

---

## Code Style Guidelines

We strive for clean, readable, and maintainable code. Please follow these guidelines:

### General

- **Type hints**: All function signatures must include type hints for parameters and return values.
  ```python
  def compute_similarity(query_embedding: list[float], doc_embedding: list[float]) -> float:
      ...
  ```

- **Docstrings**: All public modules, classes, and functions must have Google-style docstrings.
  ```python
  def fetch_citations(paper_id: str, depth: int = 1) -> list[dict]:
      """Fetches citation data for a given paper.

      Args:
          paper_id: The Semantic Scholar paper ID.
          depth: How many levels of citations to traverse.

      Returns:
          A list of citation records as dictionaries.

      Raises:
          APIError: If the Semantic Scholar API returns an error.
      """
  ```

- **Naming conventions**: Use `snake_case` for functions and variables, `PascalCase` for classes.
- **Line length**: Maximum 100 characters per line.
- **Imports**: Group imports in the order: standard library, third-party, local — separated by blank lines.

### Project-Specific

- Keep API route handlers thin — delegate logic to service modules.
- Use Pydantic models for all request/response schemas.
- Avoid hardcoded values; use configuration or environment variables.

---

## Running Tests

We use **pytest** for testing. Run the full test suite with:

```bash
pytest code/tests/ -v
```

### Additional test commands:

```bash
# Run with coverage report
pytest code/tests/ -v --cov=code --cov-report=term-missing

# Run a specific test file
pytest code/tests/test_similarity.py -v

# Run tests matching a keyword
pytest code/tests/ -v -k "test_pagerank"
```

### Before submitting a PR, ensure:

- All existing tests pass.
- New features include corresponding tests.
- No test regressions are introduced.

---

## Pull Request Process

1. **Sync your fork** with upstream before starting work:
   ```bash
   git fetch upstream
   git rebase upstream/main
   ```

2. **Make your changes** on a feature branch (not `main`).

3. **Write or update tests** for your changes.

4. **Run the full test suite** and ensure all tests pass.

5. **Commit with clear, descriptive messages**:
   ```
   feat: add BFS citation traversal with depth limiting
   fix: correct cosine similarity normalization edge case
   docs: update API endpoint documentation
   ```
   We follow [Conventional Commits](https://www.conventionalcommits.org/) format.

6. **Push your branch** and open a Pull Request against `main`.

7. **Fill out the PR template** completely.

8. **Respond to review feedback** promptly.

### PR Review Criteria

- Code follows the style guidelines above.
- Tests are included and passing.
- Documentation is updated if applicable.
- No unnecessary dependencies are added.
- The PR addresses a single concern (avoid mega-PRs).

---

## Reporting Issues

Found a bug or have a feature idea? Please open an issue using one of our templates:

- 🐛 [Bug Report](.github/ISSUE_TEMPLATE/bug_report.yml) — for reporting bugs and unexpected behavior
- ✨ [Feature Request](.github/ISSUE_TEMPLATE/feature_request.yml) — for proposing new features or improvements

### Tips for effective bug reports:

- Include steps to reproduce the issue.
- Provide your environment details (OS, Python version, Docker version).
- Include relevant logs or error messages.
- Attach screenshots if the issue involves the UI.

### Security vulnerabilities

If you discover a security vulnerability, **do not open a public issue**. Instead, follow the process described in our [Security Policy](SECURITY.md).

---

## Questions?

If you have questions about contributing, feel free to open a [Discussion](https://github.com/HosamKsbaa/GraphSelect--Advancing-Research-Papers-Semantic-Search-with-Embedding-and-Knowledge-Graphs/discussions) on GitHub.

Thank you for helping make GraphSelect better! 🚀
