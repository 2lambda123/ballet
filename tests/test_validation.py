import unittest
from textwrap import dedent
from unittest.mock import patch

import numpy as np
import pandas as pd
from funcy import contextmanager

from ballet.compat import SimpleImputer
from ballet.eng.base import BaseTransformer
from ballet.eng.misc import IdentityTransformer
from ballet.feature import Feature
from ballet.util.ci import TravisPullRequestBuildDiffer
from ballet.util.git import get_diff_str_from_commits
from ballet.validation import (
    FeatureApiValidator, FileChangeValidator, SingleFeatureApiValidator)

from .util import (
    FragileTransformer, make_mock_commit, make_mock_commits, mock_repo)


@contextmanager
def mock_project(path_content):
    with mock_repo() as repo:
        for path, content in path_content:
            make_mock_commit(repo, path=path, content=content)
        yield repo


@contextmanager
def null_file_change_validator(pr_num):
    with mock_repo() as repo:
        commit_range = 'HEAD^..HEAD'
        contrib_module_path = None
        X = None
        y = None

        travis_env_vars = {
            'TRAVIS_BUILD_DIR': repo.working_tree_dir,
            'TRAVIS_PULL_REQUEST': str(pr_num),
            'TRAVIS_COMMIT_RANGE': commit_range,
        }

        with patch.dict('os.environ', travis_env_vars, clear=True):
            yield FileChangeValidator(
                repo, pr_num, contrib_module_path, X, y)


@contextmanager
def mock_file_change_validator(
    path_content, pr_num, contrib_module_path, X, y
):
    """FileChangeValidator for mock repo and mock project content

    Args:
        path_content: iterable of (relative path, file content)
    """
    with mock_project(path_content) as repo:
        travis_build_dir = repo.working_tree_dir
        travis_pull_request = str(pr_num)
        travis_commit_range = get_diff_str_from_commits(
            repo.head.commit.parents[0], repo.head.commit)

        travis_env_vars = {
            'TRAVIS_BUILD_DIR': travis_build_dir,
            'TRAVIS_PULL_REQUEST': travis_pull_request,
            'TRAVIS_COMMIT_RANGE': travis_commit_range,
        }

        with patch.dict('os.environ', travis_env_vars, clear=True):
            yield FileChangeValidator(
                repo, pr_num, contrib_module_path, X, y)


@contextmanager
def mock_feature_api_validator(
    path_content, pr_num, contrib_module_path, X, y
):
    """FileChangeValidator for mock repo and mock project content

    Args:
        path_content: iterable of (relative path, file content)
    """
    with mock_project(path_content) as repo:
        travis_build_dir = repo.working_tree_dir
        travis_pull_request = str(pr_num)
        travis_commit_range = get_diff_str_from_commits(
            repo.head.commit.parents[0], repo.head.commit)

        travis_env_vars = {
            'TRAVIS_BUILD_DIR': travis_build_dir,
            'TRAVIS_PULL_REQUEST': travis_pull_request,
            'TRAVIS_COMMIT_RANGE': travis_commit_range,
        }

        with patch.dict('os.environ', travis_env_vars, clear=True):
            yield FeatureApiValidator(
                repo, pr_num, contrib_module_path, X, y)


class SampleDataMixin:
    def setUp(self):
        self.df = pd.DataFrame(
            data={
                'country': ['USA', 'USA', 'Canada', 'Japan'],
                'year': [2001, 2002, 2001, 2002],
                'size': [np.nan, -11, 12, 0.0],
                'strength': [18, 110, np.nan, 101],
                'happy': [False, True, False, False]
            }
        ).set_index(['country', 'year'])
        self.X = self.df[['size', 'strength']]
        self.y = self.df[['happy']]
        super().setUp()


class SingleFeatureApiValidatorTest(SampleDataMixin, unittest.TestCase):

    def test_good_feature(self):
        feature = Feature(
            input='size',
            transformer=SimpleImputer(),
        )

        validator = SingleFeatureApiValidator(self.X, self.y)
        result, failures = validator.validate(feature)
        self.assertTrue(result)
        self.assertEqual(len(failures), 0)

    def test_bad_feature_input(self):
        # bad input
        feature = Feature(
            input=3,
            transformer=SimpleImputer(),
        )
        validator = SingleFeatureApiValidator(self.X, self.y)
        result, failures = validator.validate(feature)
        self.assertFalse(result)
        self.assertIn('has_correct_input_type', failures)

    def test_bad_feature_transform_errors(self):
        # transformer throws errors
        feature = Feature(
            input='size',
            transformer=FragileTransformer(
                (lambda x: True, ), (RuntimeError, ))
        )
        validator = SingleFeatureApiValidator(self.X, self.y)
        result, failures = validator.validate(feature)
        self.assertFalse(result)
        self.assertIn('can_transform', failures)

    def test_bad_feature_wrong_transform_length(self):
        class _WrongLengthTransformer(BaseTransformer):
            def transform(self, X, **transform_kwargs):
                new_shape = list(X.shape)
                new_shape[0] += 1
                output = np.arange(np.prod(new_shape)).reshape(new_shape)
                return output

        # doesn't return correct length
        feature = Feature(
            input='size',
            transformer=_WrongLengthTransformer(),
        )
        validator = SingleFeatureApiValidator(self.X, self.y)
        result, failures = validator.validate(feature)
        self.assertFalse(result)
        self.assertIn('has_correct_output_dimensions', failures)

    def test_bad_feature_deepcopy_fails(self):
        class _CopyFailsTransformer(IdentityTransformer):
            def __deepcopy__(self):
                raise RuntimeError
        feature = Feature(
            input='size',
            transformer=_CopyFailsTransformer(),
        )
        validator = SingleFeatureApiValidator(self.X, self.y)
        result, failures = validator.validate(feature)
        self.assertFalse(result)
        self.assertIn('can_deepcopy', failures)


class ProjectStructureValidatorTest(SampleDataMixin, unittest.TestCase):

    def setUp(self):
        super().setUp()
        self.pr_num = 73

        self.valid_feature_str = dedent(
            '''
            from sklearn.base import BaseEstimator, TransformerMixin
            class IdentityTransformer(BaseEstimator, TransformerMixin):
                def fit(self, X, y=None, **fit_kwargs):
                    return self
                def transform(self, X, **transform_kwargs):
                    return X
            input = 'size'
            transformer = IdentityTransformer()
            '''
        ).strip()
        self.invalid_feature_str = dedent(
            '''
            from sklearn.base import BaseEstimator, TransformerMixin
            class RaisingTransformer(BaseEstimator, TransformerMixin):
                def fit(self, X, y=None, **fit_kwargs):
                    raise RuntimeError
                def transform(self, X, **transform_kwargs):
                    raise RuntimeError
            input = 'size'
            transformer = RaisingTransformer()
            '''
        ).strip()

    def test_init(self):
        with null_file_change_validator(self.pr_num) as validator:
            self.assertIsInstance(
                validator.differ, TravisPullRequestBuildDiffer)

    def test_collect_file_diffs(self):
        n = 10
        filename = 'file{i}.py'
        with mock_repo() as repo:
            commits = make_mock_commits(repo, n=n, filename=filename)
            contrib_module_path = None
            X = None
            y = None
            commit_range = get_diff_str_from_commits(
                commits[0], commits[-1])

            travis_env_vars = {
                'TRAVIS_BUILD_DIR': repo.working_tree_dir,
                'TRAVIS_PULL_REQUEST': str(self.pr_num),
                'TRAVIS_COMMIT_RANGE': commit_range,
            }

            with patch.dict('os.environ', travis_env_vars, clear=True):
                validator = FileChangeValidator(
                    repo, self.pr_num, contrib_module_path, X, y)
                file_diffs = validator._collect_file_diffs()

                # checks on file_diffs
                self.assertEqual(len(file_diffs), n - 1)

                for diff in file_diffs:
                    self.assertEqual(diff.change_type, 'A')
                    self.assertTrue(diff.b_path.startswith('file'))
                    self.assertTrue(diff.b_path.endswith('.py'))

    @unittest.expectedFailure
    def test_categorize_file_diffs(self):
        raise NotImplementedError

    @unittest.expectedFailure
    def test_collect_features(self):
        raise NotImplementedError

    @unittest.expectedFailure
    def test_collect_changes(self):
        raise NotImplementedError


class FileChangeValidatorTest(ProjectStructureValidatorTest):

    def test_validation_failure_no_features_found(self):
        path_content = [
            ('readme.txt', None),
            ('src/__init__.py', None),
            ('src/contrib/__init__.py', None),
            ('src/contrib/foo.py', None),
            ('src/contrib/baz.py', None),
        ]
        contrib_module_path = 'src/contrib/'
        with mock_file_change_validator(
            path_content, self.pr_num, contrib_module_path, self.X, self.y
        ) as validator:
            result = validator.validate()
            self.assertFalse(result)

    def test_validation_failure_inadmissible_file_diffs(self):
        path_content = [
            ('readme.txt', None),
            ('src/__init__.py', None),
            ('src/contrib/__init__.py', None),
            ('src/contrib/foo.py', None),
            ('invalid.py', None),
        ]
        contrib_module_path = 'src/contrib/'
        with mock_file_change_validator(
            path_content, self.pr_num, contrib_module_path, self.X, self.y
        ) as validator:
            result = validator.validate()
            self.assertFalse(result)
            self.assertEqual(
                len(validator.file_diffs), 1)
            self.assertEqual(
                len(validator.file_diffs_admissible), 0)
            self.assertEqual(
                len(validator.file_diffs_inadmissible), 1)
            self.assertEqual(
                validator.file_diffs_inadmissible[0].b_path, 'invalid.py')
            self.assertFalse(
                validator.file_diffs_validation_result)

    def test_validation_failure_bad_package_structure(self):
        path_content = [
            ('foo.jpg', None),
            ('src/contrib/bar/baz.py', self.valid_feature_str),
        ]
        contrib_module_path = 'src/contrib/'
        with mock_file_change_validator(
            path_content, self.pr_num, contrib_module_path, self.X, self.y
        ) as validator:
            result = validator.validate()
            self.assertFalse(result)
            self.assertEqual(
                len(validator.file_diffs), 1)
            self.assertEqual(
                len(validator.file_diffs_admissible), 1)
            self.assertEqual(
                len(validator.file_diffs_inadmissible), 0)
            self.assertTrue(
                validator.file_diffs_validation_result)
            self.assertEqual(
                len(validator.features), 0)
            self.assertFalse(
                validator.features_validation_result)

    def test_validation_success(self):
        path_content = [
            ('bob.xml', '<><> :: :)'),
            ('src/__init__.py', None),
            ('src/contrib/__init__.py', None),
            ('src/contrib/bean.py', self.valid_feature_str),
        ]
        contrib_module_path = 'src/contrib/'
        with mock_file_change_validator(
            path_content, self.pr_num, contrib_module_path, self.X, self.y
        ) as validator:
            result = validator.validate()
            self.assertTrue(result)


class FeatureApiValidatorTest(ProjectStructureValidatorTest):

    def test_validation_failure_invalid_feature(self):
        path_content = [
            ('foo.jpg', None),
            ('src/__init__.py', None),
            ('src/contrib/__init__.py', None),
            ('src/contrib/foo.py', self.invalid_feature_str),
        ]
        contrib_module_path = 'src/contrib/'
        with mock_feature_api_validator(
            path_content, self.pr_num, contrib_module_path, self.X, self.y
        ) as validator:
            file_diffs, diffs_admissible, diffs_inadmissible, new_features = \
                validator.collect_changes()

            self.assertEqual(len(file_diffs), 1)
            self.assertEqual(len(diffs_admissible), 1)
            self.assertEqual(len(diffs_inadmissible), 0)
            self.assertEqual(len(new_features), 1)

            result = validator.validate()
            self.assertFalse(result)
