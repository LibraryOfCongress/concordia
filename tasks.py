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
def dumpenv(ctx):
    '''
    Dump an INI template file of all decoupled config settings with defaults
    '''
    setup_django()
    from concordia.experiments.importer.models import Importer
    from config import config
    Importer()
    config.dumps()
    ctx.run('cat {}'.format('env.ini_template'), pty=True)
