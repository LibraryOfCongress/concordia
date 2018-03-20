import os
import io
import sys
import csv
from pathlib import Path
from configparser import ConfigParser, ExtendedInterpolation

MISSING = object()
REQUIRED = object()
BOOLEANS = {
    '1': True, 'yes': True, 'true': True, 'on': True,
    '0': False, 'no': False, 'false': False, 'off': False, '': False, 'null': False
}


def get_caller_path(frames=1):
    frame = sys._getframe()
    while frames:
        frame = frame.f_back
        frames -= 1

    return Path(frame.f_code.co_filename).absolute()


def find_file(filename):
    if filename.startswith('/'):
        return filename

    checked = []
    path = Path(get_caller_path(frames=4), filename)
    for parent in path.parents:
        current = parent / filename
        checked.append(str(current))
        if current.exists():
            return current

    raise FileNotFoundError('Reached root without finding {} (checked {})'.format(
        filename,
        ','.join(checked)
    ))


def env_transform(section, option):
    return '{}_{}'.format(section, option).upper()


def csv_factory(post_process=list):

    def csv(value):
        if not isinstance(value, str):
            return value

        with io.StringIO(value) as fs:
            reader = csv.reader(fs)
            lines = [post_process(row) for row in reader]
            if len(lines) == 1:
                lines = lines[0]

        return lines

    return csv


def transform(value, cast):
    if not cast:
        return value

    if cast is bool:
        value = BOOLEANS.get(str(value).lower())
        if value is None:
            raise ValueError('Not a boolean: %s' % value)

        return value

    return cast(value)


class Config:

    def __init__(self, filename='env.ini'):
        filename = filename or 'env.ini'
        self.filename = find_file(filename)
        self._config_opts = {}
        self.csvlist = csv_factory()
        self.csvtuple = csv_factory(post_process=tuple)
        self.parser = ConfigParser(interpolation=ExtendedInterpolation())
        with open(self.filename) as fobj:
            self.parser.readfp(fobj)

    def has_option(self, section, option):
        return (
            env_transform(section, option) in os.environ or
            self.parser.has_option(section, option)
        )
    
    def get(self, section, option, default=MISSING, cast=None):
        env_var = env_transform(section, option)

        if env_var in os.environ:
            value = os.environ[env_var]
        
        elif self.has_option(section, option):
            value = self.parser.get(section, option)
        
        else:
            if default is MISSING:
                raise ValueError(
                    '{}:{} not found. '
                    'Declare as {} in ENV or provide default value'.format(
                        ':'.format(section, option),
                        env_var
                    )
                )

            value = default

        return transform(value, cast)

    def dumps(self, filename='env.ini_template'):
        print('Read from {}'.format(self.filename))
        print('Writing {} entries to {}'.format(len(self._config_opts), filename))
        cp = ConfigParser()

        for section in self._config_opts:
            if not cp.has_section(section):
                cp[section] = {}

            for option, value in sorted(self._config_opts[section]):
                if value is REQUIRED or value is MISSING:
                    value = ''
                
                cp.set(section, option, str(value))

        ini = io.StringIO()
        cp.write(ini)
        with open('env.ini_template', 'w') as fp:
            for line in ini.getvalue().splitlines():
                if line.startswith('['):
                    print(line, file=fp)
                    section = line.strip('[]').upper()
                elif line.strip():
                    option, value = line.split(' = ', 1)
                    option = option.upper()
                    print('{}\n{} = {}\n'.format(
                        '# ENV var: {}'.format(
                            '{}_{}'.format(section, option).upper()
                        ),
                        option,
                        value,
                    ), file=fp)
                else:
                    print('', file=fp)


    def __call__(self, section, option, default=MISSING, cast=None):
        section, option = section.lower(), option.lower()
        self._config_opts.setdefault(section, []).append([option, default])
        return self.get(section, option, default=default, cast=cast)


