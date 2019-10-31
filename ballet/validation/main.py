from funcy import decorator, ignore

from ballet.exc import (
    FeatureRejected, InvalidFeatureApi, InvalidProjectStructure,
    SkippedValidationTest)
from ballet.util.log import logger, stacklog
from ballet.validation.common import (
    get_accepted_features, get_proposed_feature)
from ballet.validation.feature_acceptance.validator import GFSSFAccepter
from ballet.validation.feature_api.validator import FeatureApiValidator
from ballet.validation.feature_pruning.validator import GFSSFPruner
from ballet.validation.project_structure.validator import (
    ProjectStructureValidator)

# helpful for log parsing
PRUNER_MESSAGE = 'Found Redundant Feature: '


@decorator
def validation_stage(call, message):
    call = stacklog(logger.info,
                    'Ballet Validation: {message}'.format(message=message),
                    conditions=[(SkippedValidationTest, 'SKIPPED')])(call)
    call = ignore(SkippedValidationTest)(call)
    return call()


@validation_stage('checking project structure')
def _check_project_structure(project, force=False):
    if not force and not project.on_pr():
        raise SkippedValidationTest('Not on PR')

    validator = ProjectStructureValidator(project)
    result = validator.validate()
    if not result:
        raise InvalidProjectStructure


@validation_stage('validating feature API')
def _validate_feature_api(project, force=False):
    """Validate feature API"""
    if not force and not project.on_pr():
        raise SkippedValidationTest('Not on PR')

    validator = FeatureApiValidator(project)
    result = validator.validate()
    if not result:
        raise InvalidFeatureApi


@validation_stage('evaluating feature performance')
def _evaluate_feature_performance(project, force=False):
    """Evaluate feature performance"""
    if not force and not project.on_pr():
        raise SkippedValidationTest('Not on PR')

    out = project.build()
    X_df, y, features = out['X_df'], out['y'], out['features']

    proposed_feature = get_proposed_feature(project)
    accepted_features = get_accepted_features(features, proposed_feature)
    evaluator = GFSSFAccepter(X_df, y, accepted_features)
    accepted = evaluator.judge(proposed_feature)

    if not accepted:
        raise FeatureRejected


@validation_stage('pruning existing features')
def _prune_existing_features(project, force=False):
    """Prune existing features"""
    if not force and not project.on_master_after_merge():
        raise SkippedValidationTest('Not on master')

    out = project.build()
    X_df, y, features = out['X_df'], out['y'], out['features']
    proposed_feature = get_proposed_feature(project)
    accepted_features = get_accepted_features(features, proposed_feature)
    evaluator = GFSSFPruner(
        X_df, y, accepted_features, proposed_feature)
    redundant_features = evaluator.prune()

    # propose removal
    for feature in redundant_features:
        logger.info(PRUNER_MESSAGE + feature.source)

    return redundant_features


def validate(project,
             check_project_structure,
             check_feature_api,
             evaluate_feature_acceptance,
             evaluate_feature_pruning):
    """Entrypoint for 'ballet validate' command in ballet projects"""
    if check_project_structure:
        _check_project_structure(project)
    if check_feature_api:
        _validate_feature_api(project)
    if evaluate_feature_acceptance:
        _evaluate_feature_performance(project)
    if evaluate_feature_pruning:
        _prune_existing_features(project)
