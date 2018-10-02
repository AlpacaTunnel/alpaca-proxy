import os
import sys
import traceback
from datetime import datetime


def print_log(*msgs):
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    filename, lineno, func, _text = traceback.extract_stack()[-2]
    filename = os.path.basename(filename)

    full_log = '{now} [{filename}:{lineno}/{func}]'.format(
        now=now, filename=filename, lineno=lineno, func=func)

    for msg in msgs:
        full_log += ' ' + str(msg)
    full_log += '\n'

    sys.stdout.write(full_log)
    sys.stdout.flush()
