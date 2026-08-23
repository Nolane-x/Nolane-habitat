"""TOML reader compatibility for Habitat's supported Python versions."""

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib
