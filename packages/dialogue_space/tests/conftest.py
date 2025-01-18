from pathlib import Path

# Import all the fixtures from every file in the tests/fixtures dir.
pytest_plugins = [
    fixture_file.as_posix().replace("/", ".").replace(".py", "")
    for fixture_file in Path().rglob("tests/fixtures/**/[!__]*.py")
]
