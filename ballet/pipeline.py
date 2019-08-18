from funcy import iterable
from sklearn_pandas import DataFrameMapper

import ballet.feature
from ballet.eng.misc import NullTransformer


class FeatureEngineeringPipeline(DataFrameMapper):
    """Make a DataFrameMapper from a feature or list of features

    Args:
        features (Union[Feature, List[Feature]]): feature or list of features

    Returns:
        DataFrameMapper: mapper made from features
    """

    def __init__(self, features):
        if not features:
            features = ballet.feature.Feature(input=[],
                                              transformer=NullTransformer())

        if not iterable(features):
            features = (features, )

        super().__init__(
            [t.as_input_transformer_tuple() for t in features],
            input_df=True)
