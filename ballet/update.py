import git
import os
import tempfile
import yaml

from cookiecutter.main import cookiecutter

from ballet.compat import pathlib
from ballet.quickstart import generate_project

PROJECT_TEMPLATE_PATH = (
    pathlib.Path(__file__).resolve().parent.joinpath('project_template'))

YML_FILE = 'ballet.yml'

def _find_ballet_dir(path):
    '''
    Searches for the directory containing the ballet path,
    using the ballet.yml as a guide
    '''
    if os.path.exists(path / YML_FILE):
        return path
    for parent in path.parents:
        parent_path = pathlib.Path(parent)
        if os.path.exists( parent_path / YML_FILE):
            return parent_path
        else:
            continue
    return None

def _create_replay(tempdir, name):
    generate_project(replay=True, output_dir=tempdir)
    for x in pathlib.Path(tempdir).iterdir():
        print(x)
    return pathlib.Path(tempdir) / name

def update_project():
    path = _find_ballet_dir(pathlib.Path(os.getcwd()))
    yml_file = open(path / YML_FILE)
    ballet_yml = yaml.load(yml_file)
    try:
        current_repo = git.Repo(path, search_parent_directories=True) # for right now
    except Exception as e: print(e)

    _tempdir = tempfile.TemporaryDirectory()
    tempdir = _tempdir.name
    updated_project = _create_replay(tempdir, ballet_yml['problem']['name'])
    updated_repo = git.Repo(str(updated_project))
    current_repo.index.merge_tree(updated_repo.head)


def main():
    update_project()