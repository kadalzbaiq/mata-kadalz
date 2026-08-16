# Public-release research

This note records release-readiness requirements from the sources that own the
relevant standards. It is research, not a release plan or an assertion that
this repository currently meets every item.

## MCP SDK compatibility and transport

- The official MCP Python SDK documents Python 3.10+ as its requirement and
  lists stdio, Streamable HTTP, and SSE as standard transports. A project that
  publishes an MCP server should therefore state its supported Python version
  and test each transport it advertises against its pinned SDK version.
  Source: <https://py.sdk.modelcontextprotocol.io/>.

## Python distribution readiness

- PyPA's packaging flow builds a source distribution and wheel from a
  `pyproject.toml` build-system declaration, then makes those artifacts
  available for users to install from an index. Before publishing, build the
  artifacts, validate their metadata with `twine check`, inspect their
  contents, and test installation plus the console command in a clean virtual
  environment. Sources: <https://packaging.python.org/en/latest/flow/> and
  <https://packaging.python.org/en/latest/guides/section-build-and-publish/>.
- The package metadata specification defines project metadata such as the
  summary, readme, license, `requires-python`, classifiers, keywords, and
  project URLs. The README is the long project description shown by package
  indexes when it is declared as project metadata. Sources:
  <https://packaging.python.org/en/latest/guides/writing-pyproject-toml/> and
  <https://packaging.python.org/en/latest/specifications/declaring-project-metadata/>.

## Publishing security

- PyPI Trusted Publishing uses GitHub Actions OIDC with short-lived tokens,
  avoiding a manually generated, long-lived PyPI API token. Source:
  <https://docs.pypi.org/trusted-publishers/>.
- For GitHub Actions, PyPI documents a dedicated publish job with
  `permissions: id-token: write`; it strongly encourages an isolated `pypi`
  environment. PyPI must be configured with the exact repository owner,
  repository name, and workflow filename authorized to publish. Sources:
  <https://docs.pypi.org/trusted-publishers/using-a-publisher/> and
  <https://docs.pypi.org/trusted-publishers/adding-a-publisher/>.
- PyPI recommends treating a Trusted Publisher like an API token: trust only a
  controlled repository and the smallest dedicated release workflow, review
  changes to that workflow, use per-job permissions, and use a protected
  environment where appropriate. Source:
  <https://docs.pypi.org/trusted-publishers/security-model/>.

## GitHub public-project baselines

- GitHub CodeQL supports Python and GitHub Actions workflows. Default setup
  selects languages, query suite, and triggering events automatically; the
  enabled languages should be checked after setup. Source:
  <https://docs.github.com/en/code-security/concepts/code-scanning/codeql/codeql-code-scanning>.
- On public repositories, GitHub runs secret scanning for free and scans all
  branches and Git history. Source:
  <https://docs.github.com/en/code-security/concepts/secret-security/secret-scanning>.
- A GitHub release is based on a tag and can provide a user-facing release
  description and downloadable source archives. Source:
  <https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases>.
