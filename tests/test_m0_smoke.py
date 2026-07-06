import pytest

from tennisdb import config


@pytest.mark.m0
def test_imports_tennisdb_config_module():
    assert config.PROJECT_ROOT.is_dir()


@pytest.mark.m0
def test_project_paths_exist():
    assert config.DATA_DIR.is_dir()
    assert config.SACKMANN_RAW_DIR.is_dir()
    assert config.TENNISDATA_RAW_DIR.is_dir()
    assert config.MIGRATIONS_DIR.is_dir()


@pytest.mark.m0
def test_duckdb_path_is_inside_data_directory():
    assert config.DUCKDB_PATH.parent == config.DATA_DIR
