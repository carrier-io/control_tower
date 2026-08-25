import pytest

import os
import shutil

from control_tower import git_clone

git_config_1 = {
    "repo": "https://github.com/carrier-io/demo-jmeter.git",
    "repo_user": "",
    "repo_pass": "",
    "repo_key": "",
    "repo_branch": "main"
}


@pytest.fixture(autouse=False)
def cleanup_git_dir():
    """Remove /tmp/git_dir before and after each test that uses it."""
    if os.path.exists('/tmp/git_dir'):
        shutil.rmtree('/tmp/git_dir')
    yield
    if os.path.exists('/tmp/git_dir'):
        shutil.rmtree('/tmp/git_dir')


def test_clone_http(cleanup_git_dir):
    # BasicEcommerce.jmx was removed from the demo-jmeter repo after the test
    # was originally written; Dummy.jmx is the root-level file present today.
    git_clone.clone_repo(git_config_1)
    assert os.path.exists('/tmp/git_dir/Dummy.jmx')
