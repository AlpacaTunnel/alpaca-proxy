#!/usr/bin/env python3

# Run cmd on the host where the python script lives.

# Author: twitter.com/alpacatunnel


import os
import sys
import subprocess
import shutil
import signal
import getpass
import socket
import time


class Command():
    """
    Run a cmd and wait it to terminate by itself or be terminated by a thread.
    """

    def __init__(self, cmd=None):
        bash_cmd = ['bash', '-c', cmd]
        self.child = subprocess.Popen(bash_cmd,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            universal_newlines=True, shell=False)

    def wait(self, split=False, realtime_print=True, collect_output=True):
        stream = ''

        while self.child.poll() is None:
            line = self.child.stdout.readline()

            if realtime_print and line:
                sys.stdout.write(line)
                sys.stdout.flush()

            if collect_output:
                stream += line

        left_lines = self.child.communicate()[0]
        if realtime_print:
            sys.stdout.write(left_lines)
            sys.stdout.flush()

        stream += left_lines

        rc = self.child.returncode

        if split:
            data = (stream.split('\n'))
        else:
            data = stream

        return (rc, data)

    def terminate(self):
        self.child.send_signal(signal.SIGTERM)


def _get_shell_prompt():
    # return: alpaca@ubuntu:/home/alpaca/test$
    username = getpass.getuser()
    if username == 'root':
        promtp = '#'
    else:
        promtp = '$'
    hostname = socket.gethostname()
    cwd = os.getcwd()
    return '{}@{}:{}{}'.format(username, hostname, cwd, promtp)


def _create_tmp_shell_script(cmds):
    mode = 0o777

    tmp_dir = '/tmp/exec_cmd/'
    if not os.path.exists(tmp_dir):
        os.makedirs(tmp_dir)
    os.chmod(tmp_dir, mode)

    shell_dir = os.path.join(tmp_dir, str(time.time()))
    if os.path.exists(shell_dir):
        # avoid possible conflict
        shell_dir += str(time.time())
    os.makedirs(shell_dir)
    os.chmod(shell_dir, mode)

    shell_script = os.path.join(shell_dir, 'cmd.sh')
    with open(shell_script, 'w+') as f:
        f.writelines('#!/bin/bash\n')
        f.writelines('set -e\n')
        for c in cmds:
            f.writelines(c + '\n')

    os.chmod(shell_script, mode)
    return shell_script


def _delete_tmp_shell_script(shell_script):
    base_dir = os.path.dirname(shell_script)
    shutil.rmtree(base_dir)


def exec_cmd(c, realtime_print=True):
    """
    Run a cmd, print the output, and return (return_code, output_string).
    The shell prompt is printed out, but not included in the return string.

    Note: each exec_cmd() runs in a separate shell context.
    exec_cmd('cd /etc/') or exec_cmd('export VAR=somevar') takes no effect.
    To run a batch of cmds, use exec_cmds().

    TODO: use threading and add timeout.
    """

    if realtime_print:
        shell = _get_shell_prompt()
        sys.stdout.write('{} {}\n'.format(shell, c))
        sys.stdout.flush()

    cmd = Command(c)
    results = cmd.wait(split=False, realtime_print=realtime_print, collect_output=True)

    if realtime_print:
        sys.stdout.write('{}\n'.format(shell))
        sys.stdout.flush()

    return results


def exec_cmds(cmds, strict=False):
    """
    Run a list of cmds in the same shell context.
    exec_cmds(['cd /usr', 'ls']) equals to exec_cmd('ls /usr').
    """

    shell_script = _create_tmp_shell_script(cmds)
    exec_cmd('cat {}'.format(shell_script))

    rc, _output = exec_cmd('bash -x {}'.format(shell_script))
    if strict and int(rc) != 0:
        raise Exception('cmds {} failed with return_code {}.'.format(cmds, rc))

    _delete_tmp_shell_script(shell_script)


def _test_main():
    exec_cmd('ls /tmp/')
    exec_cmds([
        'cd /tmp/exec_cmd',
        'ls -l',
        'cd /tmp/',
        'ls',
        ], strict=True)


if __name__ == '__main__':
    _test_main()
