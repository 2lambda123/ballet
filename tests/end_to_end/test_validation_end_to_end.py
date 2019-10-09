import os
from subprocess import CalledProcessError, check_call
from textwrap import dedent
from types import ModuleType
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from ballet.compat import safepath
from ballet.eng.misc import IdentityTransformer
from ballet.feature import Feature
from ballet.pipeline import FeatureEngineeringPipeline
from ballet.project import make_feature_path
from ballet.templating import start_new_feature
from ballet.util import get_enum_values
from ballet.util.code import get_source
from ballet.util.git import make_commit_range, switch_to_new_branch
from ballet.util.log import logger
from ballet.util.mod import import_module_at_path, modname_to_relpath
from ballet.validation.main import TEST_TYPE_ENV_VAR, BalletTestTypes
from tests.util import load_regression_data


def submit_feature(repo, contrib_dir, username, featurename, new_feature_str):
    feature_path = make_feature_path(contrib_dir, username, featurename)
    cc_kwargs = {
        'extra_context': {'username': username, 'featurename': featurename},
        'no_input': True,
    }
    result = start_new_feature(contrib_dir=contrib_dir, **cc_kwargs)
    with feature_path.open('w') as f:
        f.write(new_feature_str)

    added_files = [str(fn) for (fn, kind) in result if kind == 'file']
    repo.index.add(added_files)
    repo.index.commit('Add {} feature'.format(feature_path))


def make_feature_str(input):
    return dedent("""
        from ballet import Feature
        from ballet.eng.misc import IdentityTransformer
        input = {input!r}
        transformer = IdentityTransformer()
        feature = Feature(input, transformer)
    """.format(input=input)).strip()


@pytest.mark.skip
@pytest.mark.slow
def test_validation_end_to_end(quickstart):
    project = quickstart.project
    modname = 'foo'
    base = project.path
    repo = project.repo

    def _import(modname):
        relpath = modname_to_relpath(modname,
                                     project_root=base,
                                     add_init=False)
        abspath = base.joinpath(relpath)
        return import_module_at_path(modname, abspath)

    foo = _import('foo')
    assert isinstance(foo, ModuleType)

    foo_features = _import('foo.features')
    assert isinstance(foo_features, ModuleType)

    collect_contrib_features = foo_features.collect_contrib_features
    features = collect_contrib_features()
    assert len(features) == 0

    # first providing a mock feature, call build
    with patch.object(
        foo_features, 'collect_contrib_features',
        return_value=[Feature(input='A_1', transformer=IdentityTransformer())]
    ):
        X_df = pd.util.testing.makeCustomDataframe(5, 2)
        X_df.columns = ['A_0', 'A_1']
        out = foo_features.build(X_df=X_df, y_df=[])
        assert np.shape(out['X']) == (5, 1)
        assert isinstance(out['mapper_X'], FeatureEngineeringPipeline)

    # write a new version of foo.load_data.load_data
    new_load_data_str = get_source(load_regression_data)

    p = base.joinpath(modname, 'load_data.py')
    with p.open('w') as f:
        f.write(new_load_data_str)

    # commit changes
    repo.index.add([str(p)])
    repo.index.commit('Load mock regression dataset')

    # call different validation routines
    def call_validate(ballet_test_type):
        with patch.dict(os.environ,
                        {TEST_TYPE_ENV_VAR: ballet_test_type}):
            check_call('ballet validate', cwd=safepath(base), env=os.environ)

    def call_validate_all(pr=None):
        envvars = {
            'TRAVIS_BUILD_DIR': repo.working_tree_dir,
        }
        if pr is None:
            envvars['TRAVIS_PULL_REQUEST'] = 'false'
            envvars['TRAVIS_COMMIT_RANGE'] = make_commit_range(
                repo.commit('HEAD@{-1}').hexsha, repo.commit('HEAD').hexsha)
            envvars['TRAVIS_PULL_REQUEST_BRANCH'] = ''
            envvars['TRAVIS_BRANCH'] = repo.heads.master.name
        else:
            envvars['TRAVIS_PULL_REQUEST'] = str(pr)
            envvars['TRAVIS_COMMIT_RANGE'] = make_commit_range(
                repo.heads.master.name,
                repo.commit('pull/{pr}'.format(pr=pr)).hexsha)

        with patch.dict(os.environ, envvars):
            for ballet_test_type in get_enum_values(BalletTestTypes):
                call_validate(ballet_test_type)

    call_validate_all()

    # branch to a fake PR and write a new feature
    contrib_dir = base.joinpath(modname, 'features', 'contrib')
    logger.info('Switching to pull request 1, User Bob, Feature A')
    switch_to_new_branch(repo, 'pull/1')
    new_feature_str = make_feature_str('A_0')
    username = 'bob'
    featurename = 'A_0'
    submit_feature(repo, contrib_dir, username, featurename, new_feature_str)

    # call different validation routines
    logger.info('Validating pull request 1, User Bob, Feature A')
    call_validate_all(pr=1)

    # merge PR with master
    logger.info('Merging into master')
    repo.git.checkout('master')
    repo.git.merge('pull/1', no_ff=True)

    # call different validation routines
    logger.info('Validating after merge')
    call_validate_all()

    # write another new feature
    logger.info('Switching to pull request 2, User Charlie, Feature Z_1')
    switch_to_new_branch(repo, 'pull/2')
    new_feature_str = make_feature_str('Z_1')
    username = 'charlie'
    featurename = 'Z_1'
    submit_feature(repo, contrib_dir, username, featurename, new_feature_str)

    # if we expect this feature to fail
    with pytest.raises(CalledProcessError):
        logger.info('Validating pull request 2, User Charlie, Feature Z_1')
        call_validate_all(pr=2)

    # write another new feature - redudancy
    repo.git.checkout('master')
    switch_to_new_branch(repo, 'pull/3')
    new_feature_str = make_feature_str('A_0')
    username = 'charlie'
    featurename = 'A_0'
    submit_feature(repo, contrib_dir, username, featurename, new_feature_str)

    with pytest.raises(CalledProcessError):
        call_validate_all(pr=3)
