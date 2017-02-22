"""
Git Blueprint
=============

Installs git and contains useful git commands for other blueprints to use.

**Fabric environment:**

.. code-block:: yaml

    blueprints:
      - blues.git

"""
import os
import re

from fabric.context_managers import cd
from fabric.contrib import files
from fabric.decorators import task
from fabric.utils import warn
from fabric.operations import local

from refabric.api import run, info
from refabric.context_managers import sudo, silent
from refabric.contrib import blueprints

from . import debian

__all__ = ['setup']


blueprint = blueprints.get(__name__)


@task
def setup():
    """
    Install Git
    """
    install()


def install():
    with sudo():
        info('Installing: {}', 'Git')
        debian.apt_get('install', 'git')


def clone(url, branch=None, repository_path=None, **kwargs):
    """
    Clone repository and branch.

    :param url: Git url to clone
    :param branch: Branch to checkout
    :param repository_path: Destination
    :param kwargs: Not used but here for easier kwarg passing
    :return: (destination, got_cloned bool)
    """
    repository = parse_url(url, branch=branch)
    name = repository['name']
    branch = repository['branch']
    cloned = False

    if not repository_path:
        repository_path = os.path.join('.', name)

    if not files.exists(os.path.join(repository_path, '.git')):
        info('Cloning {}@{} into {}',
             url,
             branch or '<default>',  # if branch is None
             repository_path)

        with silent('warnings'):
            maybe_branch = ''

            if branch is not None:
                maybe_branch = ' -b {branch}'.format(branch=branch)

            cmd = 'git clone{maybe_branch} {remote} {name}'.format(
                maybe_branch=maybe_branch,
                remote=url,
                name=name)
            output = run(cmd)

        if output.return_code != 0:
            warn('Failed to clone repository "{}", probably permission denied!'.format(name))
            cloned = None
        else:
            cloned = True
    else:
        info('Git repository already cloned: {}', name)

    return repository_path, cloned


def fetch(repository_path=None):
    if not repository_path:
        repository_path = debian.pwd()

    with cd(repository_path), silent():
        run('git fetch origin', pty=False)


def lsremote(repo_url, reftype='branches'):
    """
    Get references from a remote repository.
    :param reftype: the reference types to return: 'branches' or 'tags'

    :return dict: {reference: revision, ...}
    """

    prefixes = {
        'branches': 'refs/heads/',
        'tags': 'refs/tags/'
    }
    prefix = prefixes[reftype]

    with silent():
        cmd = 'git -c color.ui=never --no-pager ls-remote {}'.format(repo_url)
        output = local(cmd, capture=True)
        ls = output.strip().split('\n')

    pattern = r'(?P<hash>\w+)\s+(?P<label>[\w\.\-\/]+)'
    return {match.group('label')[len(prefix):]: match.group('hash')
            for match in map(lambda x: re.match(pattern, x), ls)
            if match and match.group('label').startswith(prefix)}


def show_file(repository_path, filename, revision='HEAD'):
    """
    Get the contents of a file from a specific revision

    :return str: file contents
    """
    with cd(repository_path), silent():
        # pipe through cat to get rid of any ANSI codes
        output = run('git show {revision}:{filename} | cat'.format(
            revision=revision,
            filename=filename
        ))

    return output


def reset(revision, repository_path=None, **kwargs):
    """
    Fetch, reset, clean and checkout revision.

    :return str: commit short hash
    """
    if not repository_path:
        repository_path = debian.pwd()

    ignore = kwargs.pop('ignore', None) or []

    with cd(repository_path):
        name = os.path.basename(repository_path)
        info('Resetting git repository: {}@{}', name, revision or 'HEAD')

        with silent('warnings'):
            commands = [
                'git fetch origin',  # Fetch branches and tags
                'git reset --hard HEAD',  # Make hard reset to HEAD
                # Remove untracked files pyc, xxx~ etc
                'git clean {} -fdx'.format(' '.join(['-e {}'.format(ign)
                                                     for ign in ignore])),
                'git checkout HEAD',  # Checkout HEAD
                # Reset to the specified revision, or the tip of the remote repository.
                'git reset {} --hard'.format(revision or 'HEAD'),
            ]

            output = run(' && '.join(commands))

        if output.return_code != 0:
            warn('Failed to reset repository "{}", probably permission denied!'
                 .format(name))
            return None

        else:
            commit, _ = log()[0]
            return commit


def get_commit(repository_path=None, short=False):
    """
    Get current checked out commit for cloned repository path.

    :param repository_path: Repository path
    :param short: Format git commit hash in short (7) format
    :return str: Commit hash
    """
    if not repository_path:
        repository_path = debian.pwd()

    with cd(repository_path), silent():
        cmd = 'git rev-parse'
        if short:
            cmd += ' --short'

        commit = run('{} HEAD'.format(cmd)).strip()

    return commit


def get_local_commiter():
    """
    Retrieves the calling user's git name

    :return str: username
    """
    return local('git config user.name', capture=True)


def get_local_email():
    """
    Retrieves the calling user's git name

    :return str: username
    """
    return local('git config user.email', capture=True)


def diff_stat(repository_path=None, commit='HEAD^', path=None):
    """
    Get diff stats for path.

    :param repository_path: Repository path
    :param commit: Commit to diff against, ex 12345..67890
    :param path: Path or file to diff
    :return tuple: int(files changed), int(insertions), int(deletions)
    """
    if not repository_path:
        repository_path = debian.pwd()

    with cd(repository_path), silent():

        # Example output (note leading space):
        #    719 files changed, 104452 insertions(+), 29309 deletions(-)
        #    1 file changed, 1 insertion(+)
        output = run('git diff --shortstat {} -- {}'.format(commit, path), pty=False)
        parts = output.strip().split(', ') if output else []
        changed, insertions, deletions = 0, 0, 0

        for part in parts:
            match = re.match(r'^\s*(\d+)\s+(.+)$', part)
            if not match:
                raise ValueError('no regex match for {!r} in {!r}'.format(part, output))
            n, label = match.groups()
            if label.endswith('(+)'):
                insertions = int(n)
            elif label.endswith('(-)'):
                deletions = int(n)
            elif label.endswith('changed'):
                changed = int(n)
            else:
                raise ValueError('unexpected git output')

        return changed, insertions, deletions


def get_origin(repository_path):
    """
    Get the name of the remote (tracking) branch

    :return str: refspec
    """
    if not repository_path:
        repository_path = debian.pwd()

    with cd(repository_path), silent():
        origin = run('git rev-parse --abbrev-ref --symbolic-full-name @{u}', pty=False)

    return origin


def log(repository_path=None, refspec='HEAD', count=1, path=None, author=False):
    """
    Get log for repository and optional commit range.

    :param repository_path: Repository path
    :param commit: Commit to log, ex HEAD..origin
    :param path: Path or file to log
    :return: [(<commit>, <comment>), ...]
    """
    if not repository_path:
        repository_path = debian.pwd()

    with cd(repository_path), silent():
        cmd = 'git -c color.ui=never --no-pager log'
        cmd += ' --pretty="format:%h {}"'.format('%an: %s' if author else '%s')

        if count:
            cmd += ' -n{}'.format(count)

        cmd += ' {}'.format(refspec)

        if path:
            cmd += ' -- {}'.format(path)

        output = run(cmd, pty=False)

        git_log = output.stdout.strip().split('\n')
        git_log = [row.strip().split(' ', 1) for row in git_log if row.strip()]

    return git_log


def log_between_tags(repository_path, tag1, tag2):
    """
    get log for repository between 2 tags
    (--no-pager removes garbled text around the changelog)
    :param repository_path:
    :param tag1: oldest tag
    :param tag2: newset tag
    :return: changelog as a string
    """
    refspec = '{0}..{1}'.format(tag1, tag2)
    git_log = log(repository_path, refspec=refspec, count=False, author=True)
    return u'\n'.join([u' :: '.join(row) for row in git_log])


def current_tag(repository_path=None):
    """
    Get most recent tag
    :param repository_path: Repository path
    :return: The most recent tag, and the number of commits from HEAD
    """
    if not repository_path:
        repository_path = debian.pwd()

    with cd(repository_path), silent():
        output = run('git describe --long --tags --dirty --always', pty=False)
        # 20141114.1-306-g72354ae-dirty
        tag, delta, _ = output.strip().split('-')

        return tag, int(delta)


def get_two_most_recent_tags(repository_path):
    """
    Get two most recent tags
    :param repository_path:
    :return: new_tag, runner_up_tag
    """
    with cd(repository_path), silent():
        tags = run('git --no-pager describe --tags && '
                   'git --no-pager describe --tags '
                   '"`git --no-pager describe --tags`~1"')
        new_tag, runner_up_tag = tags.strip().split('\n')
        new_tag = new_tag.replace('\r', '')
        return new_tag, runner_up_tag


def parse_url(url, branch=None):
    """
    Parse a git repository definition to get

    - url
    - branch
    - GitHub repository owner
    - repository name
    - egg name

    .. note:
        The git URL has to be in the "Git over SSH" format. HTTP/HTTPS/GIT
        over HTTP are not accepted.

    :param url: The url to parse
    :param branch: Optional branch name, overrides branch found in URL.
    :return: url, name, branch, egg
    :rtype: dict()
    """
    egg = None
    url_branch = None  # branch found in URL, if found

    # Split out repository owner from GitHub URLs
    if 'git@github.com' in url:
        path = url.split(':', 1)[1]
        gh_owner = path.split('/', 1)[0]
    else:
        gh_owner = None

    # Check to see if @<branch> is in the url.
    if url and '@' in url.split(':', 1)[-1]:
        # Split out "@<branch>[...]" from the url.
        url, url_branch = url.rsplit('@', 1)

        # Split out "#egg=<egg>" from url_branch if it is "@<branch>#egg=<egg>"
        if '#' in url_branch:
            url_branch, egg = url_branch.split('#', 1)

    if url is None or not url:
        raise ValueError('The git URL is not, have you set it correctly?')

    if branch is None:
        branch = url_branch

    if branch is not None and not branch:
        raise ValueError('branch is not None, but is falsy, check your '
                         'git_url or git_branch options.')

    repository_name = url.rsplit('/', 1)[-1]

    return {
        'url': url,
        'gh_owner': gh_owner,
        'name': repository_name,
        'branch': branch,
        'egg': egg
    }
