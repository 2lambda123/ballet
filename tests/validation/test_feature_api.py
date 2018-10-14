import unittest

import numpy as np

from ballet.compat import SimpleImputer
from ballet.eng.base import BaseTransformer
from ballet.eng.misc import IdentityTransformer
from ballet.feature import Feature
from ballet.util import has_nans
from ballet.validation.feature_api import (
    CanDeepcopyCheck, CanTransformCheck, HasCorrectInputTypeCheck,
    HasCorrectOutputDimensionsCheck, NoMissingValuesCheck, validate)

from ..util import FragileTransformer
from .util import SampleDataMixin


class ProjectStructureTest(SampleDataMixin, unittest.TestCase):

    def test_good_feature(self):
        feature = Feature(
            input='size',
            transformer=SimpleImputer(),
        )

        result, failures = validate(feature, self.X, self.y)
        self.assertTrue(result)
        self.assertEqual(len(failures), 0)

    def test_bad_feature_input(self):
        # bad input
        feature = Feature(
            input=3,
            transformer=SimpleImputer(),
        )
        result, failures = validate(feature, self.X, self.y)
        self.assertFalse(result)
        self.assertIn(HasCorrectInputTypeCheck.__name__, failures)

    def test_bad_feature_transform_errors(self):
        # transformer throws errors
        feature = Feature(
            input='size',
            transformer=FragileTransformer(
                (lambda x: True, ), (RuntimeError, ))
        )
        result, failures = validate(feature, self.X, self.y)
        self.assertFalse(result)
        self.assertIn(CanTransformCheck.__name__, failures)

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
        result, failures = validate(feature, self.X, self.y)
        self.assertFalse(result)
        self.assertIn(HasCorrectOutputDimensionsCheck.__name__, failures)

    def test_bad_feature_deepcopy_fails(self):
        class _CopyFailsTransformer(IdentityTransformer):
            def __deepcopy__(self):
                raise RuntimeError
        feature = Feature(
            input='size',
            transformer=_CopyFailsTransformer(),
        )
        result, failures = validate(feature, self.X, self.y)
        self.assertFalse(result)
        self.assertIn(CanDeepcopyCheck.__name__, failures)

    def test_producing_missing_values_fails(self):
        assert has_nans(self.X)
        feature = Feature(
            input='size',
            transformer=IdentityTransformer()
        )
        result, failures = validate(feature, self.X, self.y)
        self.assertFalse(result)
        self.assertIn(NoMissingValuesCheck.__name__, failures)