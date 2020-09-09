import contextlib
import os
import platform
import pathlib
import subprocess
import threading

import carb
import carb.tokens


class _KitProcess(object):
    """ Kit application controller.
        Responsible for starting, monitoring and stopping instances of Kit on demand.
    """

    def __init__(self, command, experience, port, args, env=None, pid=None):
        self._command = command
        self._args = []
        self._args.append(experience)
        self._args.append(f"--/app/extensions/enabledCore=[]")
        self._args.append("--ext-folder")
        self._args.append(".\\_build\\windows-x86_64\\release\\experiences")
        self._args.append("--ext-folder")
        self._args.append(".\\_build\windows-x86_64\\release\\exts")
        self._port = port
        self._url = f"http://localhost:{port}"
        self._active_process = None
        self._active_thread = None
        self._stop = threading.Event()
        self._runtime_env = dict(os.environ)
        self._runtime_env.update(env or {})

    def spawn(self):
        # There already is an active process so exit without doing anything
        if self.is_active:
            return None
        self._active_thread = threading.Thread(target=self._run)
        self._active_thread.start()

    def _run(self):
        kwargs = {}
        if platform.system().lower() == "windows":
            kwargs = {
                # Detach process from parent process in Windows.
                # Without this flag, ctrl+c will be sent to the subprocess
                "creationflags": subprocess.CREATE_NEW_PROCESS_GROUP
            }

        if True:
            self._active_process = subprocess.Popen(
                [self._command, *self._args],
                env=self._runtime_env,
                # To capture this, change this to a PIPE.
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                **kwargs,
            )
            #print(self._active_process)
            self._active_process.communicate()

    @property
    def is_active(self):
        if self._active_process and not self._stop.is_set():
            if self._active_process.pid:
                return True
        return False

    def reset(self):
        self.stop()
        self._active_process = None
        self._active_thread = None
        self._stop = threading.Event()

    def stop(self, timeout=10):
        """ Stop the active process.
            Will send a SIGKILL after timeout to force close the process
        """
        self._stop.set()

        self._active_process.terminate()
        self._active_thread.join(timeout=timeout)
        self._active_process.kill()
        self._active_thread.join(timeout=timeout)


class KitSplash:
    """ Facility providing access to a controlled Kit instance.
        A Kit instance is launced from _KitProcess if not available.
    """

    def __init__(self, port=8012):
        extension = ".exe" if platform.system().lower() == "windows" else ""
        base_path = carb.tokens.get_tokens_interface().resolve("${kit}")
        self._command = os.path.join(base_path, f"omniverse-kit{extension}")
        self._experience = "create-splash.kit"
        self._host = "localhost"
        self._port = port
        self._args = []
        self._max = 1
        self._available = []
        self._controlled = []
        self._registered = {}
        self._in_use = []

    def start(self):
        self.start_instance()

    def start_instance(self):
        kit = _KitProcess(self._command, self._experience, self._host, self._port, self._args)
        kit.spawn()
        self._controlled.append(kit)
        self._available.append(kit)

    def stop(self):
        for instance in self._controlled:
            instance.stop()