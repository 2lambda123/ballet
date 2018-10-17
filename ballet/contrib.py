import pkgutil
import types

from funcy import collecting, complement, isnone

from ballet.feature import Feature
from ballet.project import Project
from ballet.util import dfilter
from ballet.util.log import logger

__all__ = [
    'get_contrib_features',
]


def get_contrib_features(project_root):
    """Get contributed features for a project at project_root

    For a project ``foo``, walks modules within the ``foo.features.contrib``
    subpackage. A single object that is an instance of ``ballet.Feature`` is
    imported if present in each module. The resulting ``Feature`` objects are
    collected.

    Args:
        project_root (str, path): Path to project root
    """
    project = Project(project_root)
    contrib = project._resolve('.features.contrib')
    return _get_contrib_features(contrib)


@dfilter(complement(isnone))
@collecting
def _get_contrib_features(module):
    """Get contributed features from within given module

    Be very careful with untrusted code. The module/package will be
    walked, every submodule will be imported, and all the code therein will be
    executed. But why would you be trying to import from an untrusted package
    anyway?

    Args:
        contrib (module): module (standalone or package) that contains feature
            definitions

    Returns:
        List[Feature]: list of features
    """

    if isinstance(module, types.ModuleType):
        # any module that has a __path__ attribute is also a package
        if hasattr(module, '__path__'):
            yield from _get_contrib_features_from_package(module)
        else:
            yield _get_contrib_feature_from_module(module)
    else:
        raise ValueError('Input is not a module')


@collecting
def _get_contrib_features_from_package(package):
    logger.debug(
        'Walking package path {path} to detect modules...'
        .format(path=package.__path__))

    for importer, modname, _ in pkgutil.walk_packages(
            path=package.__path__,
            prefix=package.__name__ + '.',
            onerror=logger.error):

        try:
            mod = importer.find_module(modname).load_module(modname)
        except ImportError:
            logger.exception(
                'Failed to import module {modname}'
                .format(modname=modname))
            continue

        yield _get_contrib_feature_from_module(mod)


def _get_contrib_feature_from_module(mod):
    logger.debug(
        'Trying to import contributed feature from module {modname}...'
        .format(modname=mod.__name__))

    candidates = []
    for attr in dir(mod):
        obj = getattr(mod, attr)
        if isinstance(obj, Feature):
            candidates.append(obj)

    if len(candidates) == 1:
        feature = candidates[0]
        feature.source = mod.__name__
        logger.debug(
            'Imported 1 feature from {modname} from {Feature.__name__} object'
            .format(modname=mod.__name__, Feature=Feature))
        return feature
    elif len(candidates) > 1:
        logger.debug(
            'Found too many {Feature.__name__} objects in module {modname}, '
            'skipping; candidates were {candidates!r}'
            .format(Feature=Feature, modname=mod.__name__,
                    candidates=candidates))
        return None
    else:
        logger.debug(
            'Failed to import anything useful from module {modname}'
            .format(modname=mod.__name__))
        return None
