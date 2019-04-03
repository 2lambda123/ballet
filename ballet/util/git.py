import re

import git
import requests
from funcy import collecting, re_find, re_test, silent

from ballet.compat import pathlib, safepath
from ballet.util import one_or_raise

FILE_CHANGES_COMMIT_RANGE = '{a}...{b}'
REV_REGEX = r'[a-zA-Z0-9_/^@{}-]+'
COMMIT_RANGE_REGEX = re.compile(
    r'(?P<a>{rev})\.\.(?P<thirddot>\.?)(?P<b>{rev})'
    .format(rev=REV_REGEX))
PR_REF_PATH_REGEX = re.compile(r'refs/heads/pull/(\d+)')
GIT_PUSH_FAILURE = (
    git.PushInfo.REJECTED |
    git.PushInfo.REMOTE_REJECTED |
    git.PushInfo.REMOTE_FAILURE |
    git.PushInfo.ERROR
)


class Differ:

    def diff(self):
        a, b = self._get_diff_endpoints()
        return a.diff(b)

    def _get_diff_endpoints(self):
        raise NotImplementedError


class CustomDiffer(Differ):

    def __init__(self, endpoints):
        self.endpoints = endpoints

    def _get_diff_endpoints(self):
        return self.endpoints


class PullRequestBuildDiffer(Differ):
    """Diff files from this pull request against a comparison ref

    Args:
        pr_num (str, int): pull request number
        repo (git.Repo): repo
    """

    def __init__(self, pr_num, repo):
        self.pr_num = int(pr_num)
        self.repo = repo
        self._check_environment()

    def _check_environment(self):
        raise NotImplementedError


class LocalPullRequestBuildDiffer(PullRequestBuildDiffer):

    @property
    def _pr_name(self):
        return self.repo.head.ref.name

    @property
    def _pr_path(self):
        return self.repo.head.ref.path

    def _check_environment(self):
        assert re_test(PR_REF_PATH_REGEX, self._pr_path)

    def _get_diff_endpoints(self):
        a = self.repo.rev_parse('master')
        b = self.repo.rev_parse(self._pr_name)
        return a, b


class LocalMergeBuildDiffer(Differ):
    """Diff files on a merge commit on the
    current active branch. Merge parent order is guaranteed
    such that parent 1 is HEAD and parent 2 is topic[1]

    Attributes:
        repo (git.Repo): The repository to check the merge diff on.
            Must be currently on a branch where the most recent commit
            is a merge.

    References:
        [1] https://git-scm.com/book/en/v2/Git-Tools-Advanced-Merging
    """

    def __init__(self, repo):
        self.repo = repo
        self._check_environment()

    def _check_environment(self):
        assert len(self.repo.head.commit.parents) == 2

    def _get_diff_endpoints(self):
        a = self.repo.head.commit.parents[0]
        b = self.repo.head.commit.parents[1]
        return a, b


def make_commit_range(a, b):
    return FILE_CHANGES_COMMIT_RANGE.format(a=a, b=b)


def get_diff_endpoints_from_commit_range(repo, commit_range):
    """Get endpoints of a diff given a commit range

    The resulting endpoints can be diffed directly::

        a, b = get_diff_endpoints_from_commit_range(repo, commit_range)
        a.diff(b)

    For details on specifying git diffs, see ``git diff --help``.
    For details on specifying revisions, see ``git help revisions``.

    Args:
        repo (git.Repo): Repo object initialized with project root
        commit_range (str): commit range as would be interpreted by ``git
            diff`` command. Unfortunately only patterns of the form ``a..b``
            and ``a...b`` are accepted. Note that the latter pattern finds the
            merge-base of a and b and uses it as the starting point for the
            diff.

    Returns:
        Tuple[git.Commit, git.Commit]: starting commit, ending commit (
            inclusive)

    Raises:
        ValueError: commit_range is empty or ill-formed

    See also:

        <https://stackoverflow.com/q/7251477>
    """
    if not commit_range:
        raise ValueError('commit_range cannot be empty')

    result = re_find(COMMIT_RANGE_REGEX, commit_range)
    if not result:
        raise ValueError(
            'Expected diff str of the form \'a..b\' or \'a...b\' (got {})'
            .format(commit_range))
    a, b = result['a'], result['b']
    a, b = repo.rev_parse(a), repo.rev_parse(b)
    if result['thirddot']:
        a = one_or_raise(repo.merge_base(a, b))
    return a, b


def get_repo(repo=None):
    if repo is None:
        repo = git.Repo(safepath(pathlib.Path.cwd()),
                        search_parent_directories=True)
    return repo


@silent
def get_pr_num(repo=None):
    repo = get_repo(repo)
    pr_num = re_find(PR_REF_PATH_REGEX, repo.head.ref.path)
    return int(pr_num)


@silent
def get_branch(repo=None):
    repo = get_repo(repo)
    branch = repo.head.ref.name
    return branch


def switch_to_new_branch(repo, name):
    new_branch = repo.create_head(name)
    repo.head.ref = new_branch


def set_config_variables(repo, variables):
    """Set config variables

    Args:
        repo (git.Repo): repo
        variables (dict): entries of the form 'user.email': 'you@example.com'
    """
    with repo.config_writer() as writer:
        for k, value in variables.items():
            section, option = k.split('.')
            writer.set_value(section, option, value)
        writer.release()


def get_pull_requests(owner, repo, state='closed'):
    base = 'https://api.github.com'
    q = '/repos/{owner}/{repo}/pulls'.format(owner=owner, repo=repo)
    url = base + q
    headers = {
        'Accept': 'application/vnd.github.v3+json'
    }
    params = {
        'state': state,
        'base': 'master',
        'sort': 'created',
        'direction': 'asc',
    }
    res = requests.get(url, headers=headers, params=params)
    res.raise_for_status()
    return res.json()


@collecting
def get_pull_request_outcomes(owner, repo):
    prs = get_pull_requests(owner, repo, state='closed')
    for pr in prs:
        if pr['merged_at'] is not None:
            yield 'accepted'
        else:
            yield 'rejected'


def did_git_push_succeed(push_info):
    """Check whether a git push succeeded

    A git push succeeded if it was not "rejected" or "remote rejected",
    and if there was not a "remote failure" or an "error".

    Args:
        push_info (git.remote.PushInfo): push info
    """
    return push_info.flags & GIT_PUSH_FAILURE == 0
