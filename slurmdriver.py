"""
Tiny python script that can run in the background and submit SLURM jobs when they're written
to file by delegating to `subprocess.call`
"""

import json, subprocess, os, pathlib, code
import datetime, argparse, abc, threading, time, traceback as tb

class EndPoint:
    """
    Simple named end point spec that can be called.
    Mostly just to provide a base class
    """
    def __init__(self, name):
        self.name = name
    @abc.abstractmethod
    def __call__(self, *args, **kwargs):
        """
        Calls into the endpoint
        :param args:
        :type args:
        :param kwargs:
        :type kwargs:
        :return:
        :rtype:
        """

class SubprocessEndPoint(EndPoint):
    """
    Endpoint that just calls a binary on the
    system
    """
    def __call__(self, *args, **kwargs):
        try:
            runny = subprocess.run(
                [self.name, *args],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                **kwargs
                )
        except subprocess.CalledProcessError as e:
            raise IOError(e.output.decode())

        out = runny.stdout

        if out is not None:
            out = out.decode().splitlines()
        return out

class PythonEndPoint(EndPoint):
    """
    Endpoint that just evaluates some python code
    """
    def __init__(self, name, cmd, escape=False):
        super().__init__(name)
        self.cmd = cmd
        self.escape = escape
    def fmt_arg(self, arg):
        return "'{}'".format(arg) if self.escape else "{}".format(arg)
    def fmt_kwarg(self, k, v):
        return "{}='{}'".format(k, v) if self.escape else "{}={}".format(k, v)
    def __call__(self, *args, **kwargs):
        return eval("{}({})".format(
            self.cmd,
            ", ".join(self.fmt_arg(x) for x in args))
             + ", ".join(self.fmt_kwarg(k, v) for k,v in kwargs.items())
             )

class ExecEndPoint(EndPoint):
    """
    Endpoint that executes arbitrary python code.
    Very dangerous, so only turned on if flag is passed
    """
    def __call__(self, *args, **kwargs):
        exec(*args, **kwargs)

class APIServer:
    """
    A minimal API driver that can parse jobs from JSON,
    then delegate to some sort of caller
    """
    def __init__(self, job_source, job_archive, endpoints):
        self.source = job_source
        self.archive = job_archive
        os.makedirs(self.source, exist_ok=True)
        os.makedirs(self.archive, exist_ok=True)
        self.endpoints = {e.name:e for e in endpoints}
        self._active = False
    schema_keys = ['endpoint', 'arguments']
    def validate_job_schema(self, job):
        """
        Validates that the job format is clean
        :param job:
        :type job: dict
        """
        return all(x in job for x in self.schema_keys)
    def get_jobs(self):
        """
        Loads the job specifications
        """
        jobs = []
        for f in os.listdir(self.source):
            f = os.path.join(self.source, f)
            if os.path.isfile(f):
                with open(f) as src:
                    try:
                        job = json.load(src)
                    except:
                        pass
                    else:
                        if self.validate_job_schema(job):
                            if 'status' in job:
                                if job['status'] != 'ready':
                                    continue
                            job['file'] = f
                            jobs.append(job)
        return jobs
    def resolve_endpoint(self, endpoint):
        """
        Just a dict lookup with error messages
        """
        if endpoint in self.endpoints:
            return self.endpoints[endpoint]
        else:
            print("WARNING: (skipping job) API endpoint {} unknown; valid endpoints {}".format(
                endpoint, list(self.endpoints.keys()) + [self.kill_endpoint])
            )
    def call_endpoint(self, endpoint, job_spec, *args):
        """
        Explicit call into an endpoint
        :param endpoint:
        :type endpoint:
        :param args:
        :type args:
        :return:
        :rtype:
        """
        print("CALLING: {}({})".format(endpoint.name, args))
        try:
            res = endpoint(*args)
        except Exception as e:
            # err_msg = tb.format_exc()
            err_msg = str(e)
            job_spec['status'] = 'error'
            job_spec['output'] = err_msg
            with open(job_spec['file'], 'w') as jf:
                json.dump(job_spec, jf, indent=4)
            print("ERROR:\n{}".format(err_msg))
        else:
            job_spec['status'] = 'complete'
            if res is not None:
                try:
                    dump_test = json.dumps(res)
                except:
                    job_spec['output'] = str(res)
                else:
                    job_spec['output'] = res
            with open(job_spec['file'], 'w') as jf:
                json.dump(job_spec, jf, indent=4)
    def archive_job(self, jobfile):
        """
        Archives the job file so it doesn't keep getting resubmitted
        :param jobfile:
        :type jobfile:
        :return:
        :rtype:
        """
        time_stamp = datetime.datetime.now().isoformat()
        basename = os.path.basename(jobfile)
        out_file = os.path.join(self.archive, time_stamp+"_"+basename)
        os.rename(jobfile, out_file)
    def lock_job(self, job_spec):
        """
        Sets job status to 'running'
        """
        job_spec['status'] = 'running'
        with open(job_spec['file'], 'w') as jf:
            json.dump(job_spec, jf, indent=4)
    def handle_job(self, jspec):
        """
        :return:
        :rtype:
        """
        endpoint = self.resolve_endpoint(jspec['endpoint'])
        # we do evaluations on separate threads because I hate myself
        if endpoint is not None:
            if 'archive' in jspec and jspec['archive']:
                self.archive_job(jspec['file'])
            else:
                self.lock_job(jspec)
            thread = threading.Thread(
                target=self.call_endpoint,
                daemon=True,
                args=((endpoint, jspec) + tuple(jspec['arguments']))
            )
            thread.start()
            return thread
    kill_endpoint = 'stop_server'
    def server_loop(self, poll_time=.5, timeout=5): # how often to poll for jobs
        """
        Starts a main-loop to server data
        :return:
        :rtype:
        """
        self._active = True
        while self._active:
            jobs = self.get_jobs()
            active = []
            for job in jobs:
                if job['endpoint'] == self.kill_endpoint:
                    job['status'] = 'complete'
                    with open(job['file'], 'w') as jf:
                        json.dump(job, jf, indent=4)
                    self._active = False
                    break
                else:
                    thread = self.handle_job(job)
                    if thread is not None:
                        active.append([job, thread])
                    else:
                        job['status'] = 'complete'
                        job['output'] = 'no endpoint {}; valid endpoints {}'.format(
                            job['endpoint'],
                            list(self.endpoints.keys()) + [self.kill_endpoint]
                        )
                        with open(job['file'], 'w') as jf:
                            json.dump(job, jf, indent=4)
            for job, thread in active:
                thread.join(timeout=timeout)
                if thread.is_alive():
                    job['status'] = "timeout"
                    job['output'] = ""
                    with open(job['file'], 'w') as jf:
                        json.dump(job, jf, indent=4)
                    print("ERROR: dangling thread never timed-out")
            time.sleep(poll_time)

class APIClient(code.InteractiveConsole):
    """
    Sets up a little API client that reads command-line input,
    submits jobs, listens for responses, and prints output
    """

    def __init__(self, job_source, banner=None):
        super().__init__()
        self.banner = banner
        self.compile = self._parse_job
        self.source = job_source
        # just to pass stuff through...
        self._poll_time = .5
        self._timeout = 20

    def parse_arguments(self, arg_str):
        """
        Parses arguments to a job.
        Right now totally unsophisticated but the hook is here in case
        we want to spiff stuff up

        :param arg_str:
        :type arg_str:
        :return:
        :rtype:
        """
        import shlex

        return shlex.split(arg_str)
    schema_keys = ['endpoint', 'arguments']
    def validate_job_schema(self, job):
        """
        Validates that the job format is clean
        :param job:
        :type job: dict
        """
        return all(x in job for x in self.schema_keys)
    def _parse_job(self, job_str, *args):
        """
        Hooks for self.compile
        :param job_str:
        :type job_str:
        :param args:
        :type args:
        :return:
        :rtype:
        """
        return self.parse_job(job_str)
    def parse_job(self, job_str):
        """
        Parses a job string and returns a dict that
        can be converted into JSON to submit a request

        :param job_str:
        :type job_str: str
        :return:
        :rtype:
        """
        jstrp = job_str.strip()
        if jstrp.startswith("{") or jstrp.startswith("["):
            # treat as JSON
            try:
                job = json.loads(job_str)
            except:
                # wait for more input
                job = None
            else:
                if not self.validate_job_schema:
                    raise ValueError("ERROR: invalid job schema, got keys {} but needs {}".format(
                        list(job.keys()), self.schema_keys
                    ))
                    job = None
        else:
            splits = job_str.split(" ", 1)
            if len(splits) == 1:
                job = {"endpoint":splits[0], "arguments":[]}
            else:
                job = {"endpoint":splits[0], "arguments":self.parse_arguments(splits[1])}

        return job

    def compile_input(self, read=None):
        """
        Parses input as a job

        :return:
        :rtype:
        """
        if read is None:
            read = self.default_read
        cmd = read()
        job = self.parse_job(cmd)
        while isinstance(job, str):
            cmd += read()
            job = self.parse_job(cmd)
        return job
    def get_job_name(self, job):
        """
        Gets name for a job to write to the server
        :param job:
        :type job:
        :return:
        :rtype:
        """
        base_name = job['endpoint']
        arg_hash = hash(tuple(job['arguments']))
        return "{}_{}.json".format(base_name, arg_hash)
    def submit_job(self, job):
        """
        Writes job to a JSON file
        that can be handled by the server

        :return:
        :rtype:
        """
        name = self.get_job_name(job)
        job_file = os.path.join(self.source, name)
        with open(job_file, "w+") as js:
            json.dump(job, js)
        job_file = pathlib.Path(job_file)
        write_time = job_file.stat().st_mtime
        return job_file, write_time

    complete_statuses = {'complete', 'error'}
    def read_output(self, job_file, mod_time=None, poll_time=.5, timeout=20):
        """
        Waits to read output from the job_file, checking the `mod_time` to
        make sure that file contents aren't reloaded unnecessarily.
        Should probably use a lockfile but I'm feeling lazy so we're just gonna
        query the mod times.

        :param job_file:
        :type job_file: pathlib.Path
        :return:
        :rtype:
        """

        if mod_time is None:
            mod_time = job_file.stat().st_mtime

        status = 'ready'
        result = None
        start_time = time.time()
        elapsed = (time.time() - start_time)
        # loop, check mod time, pull content, etc.
        while elapsed < timeout:
            new_mod = job_file.stat().st_mtime
            if new_mod != mod_time:
                with job_file.open() as js:
                    result = json.load(js)
                    if 'status' not in result:
                        if 'output' in result:
                            result['status'] = 'complete'
                        else:
                            result['status'] = 'error'
                    status = result['status']
                mod_time = new_mod
            if status in self.complete_statuses:
                break
            elapsed = (time.time() - start_time)
            if elapsed < timeout:
                time.sleep(poll_time)
        else:
            if result is None:
                result = {"status":"error", "endpoint":"unknown", "output":["timeout"]}
            else:
                result['status'] = 'error'
                result["output"] = ["timeout"]
        return result

    def handle_result(self, result):
        """
        Handles the result returned by the
        :param result:
        :type result:
        :return:
        :rtype:
        """

        if result['status'] == 'complete':
            if 'output' not in result:
                result['output'] = ""
            out = result['output']
            if isinstance(out, list):
                out = "\n".join(out)
            if len(out) > 0:
                print(out)
        elif result['status'] == 'error':
            if 'output' in result:
                out = result['output']
                if isinstance(out, list):
                    out = "\n".join(out)
                print("ERROR:", out, "from", result['endpoint'])
            else:
                print("ERROR:", "no output from", result['endpoint'])

    def runcode(self, job):
        return self.run_job(job, poll_time=self._poll_time, timeout=self._timeout)
    def run_job(self, job, poll_time=.5, timeout=20):
        """
        Equivalent of `runsource` in interactive console

        :param job:
        :type job:
        :param poll_time:
        :type poll_time:
        :param timeout:
        :type timeout:
        :return:
        :rtype:
        """
        file, mod_time = self.submit_job(job)
        out = self.read_output(file,
                               mod_time=mod_time,
                               poll_time=poll_time,
                               timeout=timeout
                               )
        self.handle_result(out)

    default_prompt = "<api-client> $ "
    def client_loop(self, poll_time=.5, timeout=20):
        """
        Sets up a loop to forward command line input to the API server

        :param poll_time:
        :type poll_time:
        :param timeout:
        :type timeout:
        :return:
        :rtype:
        """
        import sys, readline

        # just to pass stuff through...
        self._poll_time = poll_time
        self._timeout = timeout

        readline.parse_and_bind("tab: complete")

        try:
            sys.ps1
        except AttributeError:
            sys.ps1 = ">>> "
        try:
            sys.ps2
        except AttributeError:
            sys.ps2 = "... "

        try:
            og_ps1 = sys.ps1
            sys.ps1 = self.default_prompt
            og_ps2 = sys.ps2
            sys.ps2 = " "
            self.interact(banner=self.banner)
        finally:
            sys.ps1 = og_ps1
            sys.ps2 = og_ps2


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--jobdir',
                        default='jobs',
                        dest='jobdir'
                        )
    parser.add_argument('--archivedir',
                        default='',
                        dest='archivedir'
                        )
    parser.add_argument('--polltime',
                        type=float,
                        default=1,
                        dest='polltime'
                        )
    parser.add_argument('--timeout',
                        type=float,
                        default=10,
                        dest='timeout'
                        )
    parser.add_argument('--mode',
                        type=str,
                        default="server",
                        dest='mode'
                        )
    boolz = lambda s: False if len(s) == 0 else bool(eval(s))
    parser.add_argument('--exec',
                        type=boolz,
                        default="False",
                        dest='allow_exec'
                        )
    opts = parser.parse_args()
    jobdir = opts.jobdir
    archivedir = opts.archivedir
    if archivedir == "":
        archivedir = os.path.join(jobdir, 'archive')
    if opts.mode == "client":
        SLURMClient = APIClient(jobdir, banner="="*40 + "STARTING NODE CLIENT" + "="*40)
        SLURMClient.client_loop(poll_time=opts.polltime, timeout=opts.timeout)
    else:
        endpoints = [
                PythonEndPoint("pwd", 'os.getcwd'),
                PythonEndPoint("ls", 'os.listdir'),
                PythonEndPoint("cd", 'os.chdir', escape=True),
                SubprocessEndPoint('sbatch'),
                SubprocessEndPoint('squeue'),
                SubprocessEndPoint('sinfo'),
                SubprocessEndPoint('scancel'),
                SubprocessEndPoint('git')
            ]
        if opts.allow_exec:
            endpoints.append(ExecEndPoint("exec"))
        SLURMDriver = APIServer(
            jobdir, archivedir,
            endpoints
        )

        print("="*40, "STARTING NODE DRIVER", "="*40)
        SLURMDriver.server_loop(poll_time=opts.polltime, timeout=opts.timeout)