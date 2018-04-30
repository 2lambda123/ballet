class PullRequestInfo:
    def __init__(self, pr_num):
        self.pr_num = pr_num

    def _format(self, str):
        return str.format(pr_num=self.pr_num)

    @property
    def local_ref_name(self):
        '''Shorthand name of local ref, e.g. 'pull/1' '''
        return self._format('pull/{pr_num}')

    @property
    def local_rev_name(self):
        '''Full name of revision, e.g. 'refs/heads/pull/1' '''
        return self._format('refs/heads/pull/{pr_num}')

    @property
    def remote_ref_name(self):
        '''Full name of remote ref (as on GitHub), e.g. 'refs/pull/1/head' '''
        return self._format('refs/pull/{pr_num}/head')


class HeadInfo:
    def __init__(self, repo):
        self.head = repo.head

    @property
    def path(self):
        return self.head.ref.path


def get_file_changes_by_revision(repo, from_revision, to_revision):
    '''Get file changes between two revisions

    For details on specifying revisions, see

        git help revisions
    '''
    diff_str = '{from_revision}..{to_revision}'.format(
        from_revision=from_revision, to_revision=to_revision)
    return get_file_changes_by_diff_str(repo, diff_str)


def get_file_changes_by_diff_str(repo, diff_str):
    # TODO implement name_status=True keyword
    return repo.git.diff(diff_str, name_only=True).split('\n')