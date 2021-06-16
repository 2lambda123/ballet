import funcy as fy
import numpy as np
import pandas as pd
import pytest

from ballet.eng.misc import IdentityTransformer
from ballet.feature import Feature
from ballet.pipeline import FeatureEngineeringPipeline

with_input = pytest.mark.parametrize(
    'input',
    [
        ['foo', 'bar'],
        lambda df: ['foo', 'bar'],
    ],
    ids=[
        'list of string',
        'callable to list of string'
    ]
)
with_transformer = pytest.mark.parametrize(
    'transformer',
    [
        IdentityTransformer(),
        [IdentityTransformer()],
        [None, IdentityTransformer(), lambda x: x],
        Feature(['foo', 'bar'], IdentityTransformer()),
        [None, IdentityTransformer(), Feature(
            ['foo', 'bar'], IdentityTransformer())],
    ],
    ids=[
        'scalar',
        'list of transformer',
        'list of mixed',
        'nested feature',
        'list of mixed and nested features',
    ]
)


@with_input
@with_transformer
def test_init(input, transformer):
    feature = Feature(input, transformer)
    mapper = FeatureEngineeringPipeline(feature)
    assert isinstance(mapper, FeatureEngineeringPipeline)


@with_input
@with_transformer
def test_fit(input, transformer):
    feature = Feature(input, transformer)
    mapper = FeatureEngineeringPipeline(feature)
    df = pd.util.testing.makeCustomDataframe(5, 2)
    df.columns = ['foo', 'bar']
    mapper.fit(df)


@with_input
@with_transformer
def test_transform(input, transformer):
    feature = Feature(input, transformer)
    mapper = FeatureEngineeringPipeline(feature)
    df = pd.util.testing.makeCustomDataframe(5, 2)
    df.columns = ['foo', 'bar']
    mapper.fit(df)
    X = mapper.transform(df)
    assert np.shape(X) == (5, 2)


@with_input
@with_transformer
@pytest.mark.parametrize(
    'output',
    [
        None,
        'baz',
        ['foobaz', 'barbaz'],
    ]
)
def test_df_colnames(input, transformer, output):
    feature = Feature(input, transformer, output=output)
    mapper = FeatureEngineeringPipeline(feature)
    entities_df = pd.util.testing.makeCustomDataframe(5, 2)
    entities_df.columns = ['foo', 'bar']
    feature_matrix = mapper.fit_transform(entities_df)
    feature_frame = pd.DataFrame(
        feature_matrix,
        columns=mapper.transformed_names_,
        index=entities_df.index,
    )
    assert fy.all(fy.isa(str), feature_frame.columns)
