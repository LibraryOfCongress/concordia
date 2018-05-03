import os
import logging
from invoke import task

PROJECT_NAME = 'concordia'

def setup_django(simple_logging=True):
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "{}.settings".format(PROJECT_NAME))
    import django
    from django.conf import settings
    if simple_logging:
        settings.LOGGING_CONFIG = None
        logging.basicConfig(level=logging.INFO)
        
    django.setup()


def remove_directories(ctx, *dirpaths):
    for dirpath in dirpaths:
        assert not dirpath.startswith('/')
        ctx.run('rm -rf {}'.format(dirpath))


@task
def clean(ctx):
    ctx.run('find . -type d -name __pycache__ | xargs rm -rf')
    ctx.run('find . -type d -name *.egg-info | xargs rm -rf')
    ctx.run('rm -f logs/*.log')
    remove_directories(
        ctx,
        '.cache',
    )


@task
def check(ctx):
    '''
    Run PEP8 checks
    '''
    ctx.run('pycodestyle transcribr/transcribr concordia')

@task
def docs(ctx,):
    '''
    Generate documentation
    '''
    from sphinx import cmdline
    setup_django()
    ctx.run('sphinx-apidoc -f -o docs/modules/concordia concordia', pty=True)
    ctx.run('sphinx-apidoc -f -o docs/modules/transcribr transcribr', pty=True)
    ctx.run(
        'sphinx-build -b html -d docs/_build/doctrees'
        'docs/'
        'docs/_build/html',
        pty=True
    )
