import subprocess
from test import exceptions


class run_command:
    def __init__(self, *args, **kwargs):
        result = subprocess.run(
            *args, **kwargs, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )

        if result.returncode != 0:
            raise exceptions.BadExitCode(
                f"Command exited with {result.returncode}"
                + ", "
                + str(args[0])
                + ", "
                + "\n"
                + result.stderr.decode()
            )

        self.stdout = result.stdout.decode()
        self.stderr = result.stderr.decode()
        self.returncode = result.returncode
