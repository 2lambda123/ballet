import funcy
import numpy as np
import pandas as pd
from scipy.special import boxcox1p
from scipy.stats import skew
from sklearn.utils.validation import check_is_fitted

from ballet.eng.base import BaseTransformer, SimpleFunctionTransformer
from ballet.util import get_arr_desc

__all__ = [
    'IdentityTransformer',
    'BoxCoxTransformer',
    'ValueReplacer',
    'NamedFramer']


class IdentityTransformer(SimpleFunctionTransformer):
    """Simple transformer that passes through its input"""

    def __init__(self):
        super().__init__(funcy.identity)


class BoxCoxTransformer(BaseTransformer):
    """Conditionally apply the Box-Cox transformation

    In the fit stage, determines which variables (columns) have absolute skew
    above ``threshold``. In the transform stage, applies the Box-Cox
    transformation of 1+x to each variable selected previously.

    Args:
        threshold: skew threshold.
        lmbda (float, default=0.0): Power parameter of the Box-Cox transform.

    See also:
        https://docs.scipy.org/doc/scipy/reference/generated/scipy.special.boxcox1p.html
    """

    def __init__(self, threshold, lmbda=0):
        super().__init__()
        self.threshold = threshold
        self.lmbda = lmbda

    def fit(self, X, y=None, **fit_args):
        # features_to_transform_ is a bool or array[bool]
        self.features_to_transform_ = abs(skew(X)) > self.threshold
        return self

    def transform(self, X, **transform_args):
        check_is_fitted(self, 'features_to_transform_')

        if isinstance(X, pd.DataFrame):
            X = X.copy()
            X.loc[:, self.features_to_transform_] = boxcox1p(
                X.loc[:, self.features_to_transform_], self.lmbda)
            return X
        elif np.ndim(X) == 1:
            return boxcox1p(
                X, self.lmbda) if self.features_to_transform_ else X
        elif isinstance(X, np.ndarray):
            if self.features_to_transform_.any():
                X = X.copy()
                X = X.astype('float')
                mask = np.tile(self.features_to_transform_, (X.shape[0], 1))
                np.putmask(X, mask, boxcox1p(
                    X[:, self.features_to_transform_], self.lmbda))
            return X
        elif not self.features_to_transform_:
            # if we wouldn't otherwise have known what to do, we can pass
            # through X if transformation was not necessary anyways
            return X
        else:
            raise TypeError(
                "Couldn't use Box-Cox transform on features in {}."
                .format(get_arr_desc(X)))


class ValueReplacer(BaseTransformer):
    """Replace instances of some value with some replacement

    Args:
        value: value to replace (checked by equality testing)
        replacement: replacement
    """

    def __init__(self, value, replacement):
        super().__init__()
        self.value = value
        self.replacement = replacement

    def transform(self, X, **transform_kwargs):
        X = X.copy()
        mask = X == self.value
        X[mask] = self.replacement
        return X


class NamedFramer(BaseTransformer):
    """Convert object to named 1d DataFrame

    If transformation is successful, the resulting object is a DataFrame with a
    ``name`` attribute as given.

    Args:
        name: name for resulting DataFrame
    """

    def __init__(self, name):
        super().__init__()
        self.name = name

    def transform(self, X, **transform_kwargs):
        msg = "Couldn't convert object {} to named 1d DataFrame."
        if isinstance(X, pd.Index):
            return X.to_series().to_frame(name=self.name)
        elif isinstance(X, pd.Series):
            return X.to_frame(name=self.name)
        elif isinstance(X, pd.DataFrame):
            if X.shape[1] == 1:
                X = X.copy()
                X.columns = [self.name]
                return X
            else:
                raise ValueError(msg.format(get_arr_desc(X)))
        elif isinstance(X, np.ndarray):
            if X.ndim == 1:
                return pd.DataFrame(data=X.reshape(-1, 1), columns=[self.name])
            elif X.ndim == 2 and X.shape[1] == 1:
                return pd.DataFrame(data=X, columns=[self.name])
            else:
                raise ValueError(msg.format(get_arr_desc(X)))

        raise TypeError(msg.format(get_arr_desc(X)))


class NullTransformer(BaseTransformer):

    def transform(self, X, **transform_kwargs):
        n = np.size(X, 0)
        return np.empty((n, 0))