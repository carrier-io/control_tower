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

def test_clone_http():
    git_clone.clone_repo(git_config_1)
    assert os.path.exists('/tmp/git_dir/BasicEcommerce.jmx')
    shutil.rmtree('/tmp/git_dir')
