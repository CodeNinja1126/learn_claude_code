from utill.tools.filesystem import list_files


def test_list_files_current_directory() -> None:
    output = list_files(".")
    assert "pyproject.toml" in output
