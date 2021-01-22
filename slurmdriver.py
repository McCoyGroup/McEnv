"""
Tiny python script that can run in the background and submit SLURM jobs when they're written
to file by delegating to `subprocess.call`
"""

import json, subprocess, os, threading, time, abc
import pathlib, hashlib # folder server
import socket, base64, re # socket server
import datetime, argparse, code # client setup

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
        runny = subprocess.run(
            [self.name, *args],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            **kwargs
            )
        if runny.returncode > 0:
            out = runny.stderr.decode()
            if len(out) == 0:
                out = runny.stdout.decode()

            raise IOError(out)

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

class JobServer(metaclass=abc.ABCMeta):
    """
    Minimal abstract job server that can listen for jobs and write results
    """
    @abc.abstractmethod
    def get_jobs(self):
        """
        :return:
        :rtype: Iterable[dict]
        """
    def lock_job(self, job):
        """
        :return:
        :rtype: Iterable[dict]
        """
        pass
    @abc.abstractmethod
    def write_result(self, res):
        """
        :return:
        :rtype: Iterable[dict]
        """
class TCPJobServer(JobServer):
    """
    JobServer that delegates to a TCP job socket
    """
    def __init__(self, job_spec, res_spec, socket_type=(socket.AF_UNIX, socket.SOCK_STREAM)):
        """

        :param job_spec: speci
        :type job_spec:
        :param res_spec:
        :type res_spec:
        """

        self.job_socket = socket.socket(*socket_type)
        self._job_conn, self._job_addr = None, None
        self._job_spec = job_spec
        self.results_socket = socket.socket(*socket_type)
        self._res_conn, self._res_addr = None, None
        self._res_spec = res_spec
        self._connected = False
        self.chunk_size = 2**16

    def bind(self):
        """
        Connects to both the job and results sockets
        :return:
        :rtype:
        """
        if not self._connected:
            print('CONNECTING TO JOB SOCKET:', self._job_spec)
            self.job_socket.bind(self._job_spec)
            self.job_socket.listen(1)
            self._job_conn, self._job_addr = self.job_socket.accept()

            print('CONNECTING TO RESULTS SOCKET:', self._job_spec)
            self.results_socket.bind(self._res_spec)
            self.results_socket.listen(1)
            self._res_conn, self._res_addr = self.results_socket.accept()

            self._connected = True

    job_parser_regex = "\[[\w=+/]+\]"
    def get_jobs(self):
        """
        Listens for a job or series of jobs to process
        as JSON
        :return:
        :rtype:
        """
        self.bind()
        # print("GETTING JOBS OFF SOCKET: (chunksize {})".format(self.chunk_size))
        request_block = self._job_conn.recv(self.chunk_size).decode('ascii')

        # jobs are sent as base-64 blobs wrapped in brackets
        if isinstance(self.job_parser_regex, str):
            self.job_parser_regex = re.compile(self.job_parser_regex)

        requests = re.findall(self.job_parser_regex, request_block)

        # print("PARSED", requests)

        jobs = []
        for req in requests:
            req = req[1:-1]
            # print("GOT", req)
            req = base64.b64decode(req)
            try:
                job = json.loads(req)
            except:
                pass
            else:
                jobs.append(job)

        return jobs

    def write_result(self, res):
        """
        :param res:
        :type res: dict
        """
        sub = base64.b64encode(json.dumps(res).encode('ascii')).decode('ascii')
        sub = '{'+sub+'}'
        self.bind()
        send_bytes = sub.encode('ascii')
        if len(send_bytes) > self.chunk_size:
            raise ValueError("job too large to be sent with default chunk size {} (for {})".format(self.chunk_size, res))
        # print("PUTTING RESULTS IN SOCKET: (chunksize {})".format(self.chunk_size))
        self._res_conn.send(send_bytes)

class FolderJobServer(JobServer):
    """
    JobServer that looks for JSON files in a folder
    """

    def __init__(self, job_source, job_archive):
        self.source = job_source
        self.archive = job_archive
        os.makedirs(self.source, exist_ok=True)
        os.makedirs(self.archive, exist_ok=True)
        self.last_poll_time = None
    def get_jobs(self):
        """
        Pulls jobs from job directory
        :return:
        :rtype: Iterable[dict]
        """
        jobs = []
        for f in os.listdir(self.source):
            f = os.path.join(self.source, f)
            if os.path.isfile(f) and (
                    self.last_poll_time is None
                    or os.stat(f).st_mtime > self.last_poll_time
            ):
                with open(f) as src:
                    try:
                        job = json.load(src)
                    except:
                        pass
                    else:
                        job['file'] = f
                        jobs.append(f)
        return jobs
    def write_job(self, job):
        """
        Writes out a job to file
        :param job:
        :type job:
        :return:
        :rtype:
        """
        with open(job['file'], 'w') as jf:
            json.dump(job, jf, indent=4)
    write_result = write_job
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
        self.write_result(job_spec)

class APIServer:
    """
    A minimal API driver that can parse jobs from JSON,
    then delegate to some sort of caller
    """
    def __init__(self, socket, endpoints):
        """
        :param socket:
        :type socket: JobServer
        :param endpoints:
        :type endpoints:
        """
        self.endpoints = {e.name:e for e in endpoints}
        self.socket = socket
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
        for job in self.socket.get_jobs():
            if self.validate_job_schema(job):
                if 'status' in job:
                    if job['status'] != 'ready':
                        continue
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
            self.socket.write_result(job_spec)
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
            self.socket.write_result(job_spec)

    def handle_job(self, jspec):
        """
        :return:
        :rtype:
        """
        endpoint = self.resolve_endpoint(jspec['endpoint'])
        # we do evaluations on separate threads because I hate myself
        if endpoint is not None:
            self.socket.lock_job(jspec)
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
                    self.socket.write_result(job)
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
                        self.socket.write_result(job)
            for job, thread in active:
                thread.join(timeout=timeout)
                if thread.is_alive():
                    job['status'] = "timeout"
                    job['output'] = ""
                    self.socket.write_result(job)
                    print("ERROR: dangling thread never timed-out")
            time.sleep(poll_time)

class JobClient(metaclass=abc.ABCMeta):
    """
    Abstract client that provides a simple interface
    for writing jobs and listen for results
    """
    def get_job_name(self, job):
        """
        Gets name for a job to write to the server
        :param job:
        :type job:
        :return:
        :rtype:
        """
        base_name = job['endpoint']
        arg_hash = hashlib.sha1(str(tuple(job['arguments'])).encode()).hexdigest()
        return "{}_{}".format(base_name, arg_hash)
    @abc.abstractmethod
    def write_job(self, job):
        """
        :param job:
        :type job: dict
        :return:
        :rtype: str
        """
    def submit_job(self, job):
        """
        :param job:
        :type job: dict
        :return:
        :rtype: str
        """
        job['name'] = self.get_job_name(job)
        self.write_job(job)
        return job
    @abc.abstractmethod
    def get_results(self):
        """
        :return:
        :rtype: Iterable[dict]
        """

class FolderJobClient(JobClient):
    """
    A job client that reads from a folder
    """
    def __init__(self, jobdir):
        # cache of previous modification times
        # so that we can track multiple job results at once
        self.source = jobdir
        self._modtime_cache = {}

    def get_job_name(self, job):
        return "{}.json".format(super().get_job_name(job))

    def write_job(self, job):
        """
        Writes job to a JSON file
        that can be handled by the server

        :return:
        :rtype: str
        """
        name = self.get_job_name(job)
        job_file = os.path.join(self.source, name)
        with open(job_file, "w+") as js:
            json.dump(job, js)
        write_time = os.stat(job_file).st_mtime
        self._modtime_cache[job_file] = write_time
        return job_file

    def get_jobs(self):
        """
        Pulls jobs from job directory
        :return:
        :rtype: Iterable[dict]
        """
        jobs = []
        for f in os.listdir(self.source):
            f = os.path.join(self.source, f)
            if os.path.isfile(f) and (
                    self.last_poll_time is None
                    or os.stat(f).st_mtime > self.last_poll_time
            ):
                with open(f) as src:
                    try:
                        job = json.load(src)
                    except:
                        pass
                    else:
                        job['file'] = f
                        jobs.append(f)
        return jobs

    def get_results(self):
        """
        Gets all the results that have been written & which
        are formatted properly
        :return:
        :rtype:
        """

        mod_times = self._modtime_cache
        results = []
        for f in os.listdir(self.source):
            f = os.path.join(self.source, f)
            if os.path.isfile(f) and (
                    f not in mod_times
                    or os.stat(f).st_mtime > mod_times[f]
            ):
                with open(f) as src:
                    try:
                        res = json.load(src)
                    except:
                        pass
                    else:
                        results.append(res)

class TCPJobClient(JobClient):
    """
    A job client (i.e. the write job/get result branch)
    which uses a TCP socket
    """
    def __init__(self, job_spec, res_spec, socket_type=(socket.AF_UNIX, socket.SOCK_STREAM)):
        """

        :param job_spec: speci
        :type job_spec:
        :param res_spec:
        :type res_spec:
        """

        self.job_socket = socket.socket(*socket_type)
        self._job_spec = job_spec
        self.results_socket = socket.socket(*socket_type)
        self._res_spec = res_spec
        self._connected = False
        self.chunk_size = 2**16

    def bind(self, retries=5):
        """
        Connects to both the job and results sockets
        :return:
        :rtype:
        """
        if not self._connected:
            try:
                self.job_socket.connect(self._job_spec)
            except FileNotFoundError:
                raise IOError("Server must be initialized before client")
            else:
                time.sleep(.1)
                while not self._connected and retries > 0:
                    try:
                        self.results_socket.connect(self._res_spec)
                    except FileNotFoundError:
                        retries -= 1
                        time.sleep(.1)
                    else:
                        self._connected = True

    def write_job(self, job):
        """
        :param job:
        :type job: dict
        :return:
        :rtype: str
        """
        sub = base64.b64encode(json.dumps(job).encode('ascii')).decode('ascii')
        sub = '['+sub+']'
        self.bind()
        send_bytes = sub.encode('ascii')
        if len(send_bytes) > self.chunk_size:
            raise ValueError("job too large to be sent with default chunk size {} (for {})".format(self.chunk_size, job))
        # print("PUTTING JOB IN SOCKET: (chunksize {})".format(self.chunk_size))
        self.job_socket.send(send_bytes)
    res_parser_regex = "\{[\w=+/]+\}"
    def get_results(self):
        """
        Listens for results
        :return:
        :rtype:
        """
        self.bind()
        # print("GETTING RESULTS OFF SOCKET: (chunksize {})".format(self.chunk_size))
        request_block = self.results_socket.recv(self.chunk_size).decode('ascii')

        # jobs are sent as base-64 blobs wrapped in brackets
        if isinstance(self.res_parser_regex, str):
            self.res_parser_regex = re.compile(self.res_parser_regex)

        requests = re.findall(self.res_parser_regex, request_block)

        # print("PARSED", request_block)

        results = []
        for req in requests:
            req = req[1:-1]
            # print("GOT", req)
            req = base64.b64decode(req)
            try:
                res = json.loads(req)
            except:
                pass
            else:
                results.append(res)

        return results

class APIClient(code.InteractiveConsole):
    """
    Sets up a little API client that reads command-line input,
    submits jobs, listens for responses, and prints output
    """

    def __init__(self, socket, banner=None):
        """
        :param socket:
        :type socket: JobClient
        :param banner:
        :type banner:
        """
        super().__init__()
        self.banner = banner
        self.compile = self._parse_job

        self.socket = socket
        self._res_buffer = {}

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

    complete_statuses = {'complete', 'error'}
    def read_result(self, job, polltime=.5, timeout=20):
        """
        Periodically pulls all updates, checks to see if `job` has been updated (or if `job` is in the buffer)
        and if not, sleeps for `polltime` and, finally, hits a `timeout` if necessary

        Waits to read output from the job_file, checking the `mod_time` to
        make sure that file contents aren't reloaded unnecessarily.
        Should probably use a lockfile but I'm feeling lazy so we're just gonna
        query the mod times.

        :param job:
        :type job:
        :param polltime:
        :type polltime:
        :param timeout:
        :type timeout:
        :return:
        :rtype:
        """

        status = 'ready'
        result = None
        start_time = time.time()
        elapsed = (time.time() - start_time)
        # loop, check mod time, pull content, etc.
        while elapsed < timeout:
            if job['name'] not in self._res_buffer:
                updates = self.socket.get_results()
                for res in updates:
                    name = res['name']
                    self._res_buffer[name] = res
                # print("BUFFER:", job['name'], self._res_buffer)
            if job['name'] in self._res_buffer:
                result = self._res_buffer[job['name']]
                del self._res_buffer[job['name']]
                if 'status' not in result:
                    if 'output' in result:
                        result['status'] = 'complete'
                    else:
                        result['status'] = 'error'
                status = result['status']

            if status in self.complete_statuses:
                break
            elapsed = (time.time() - start_time)
            if elapsed < timeout:
                time.sleep(polltime)
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
                print("ERROR ({}):".format(result['endpoint']), out)
            else:
                print("ERROR ({}):".format(result['endpoint']), "no output")

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
        job = self.socket.submit_job(job)
        out = self.read_result(job, polltime=poll_time, timeout=timeout)
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
    parser.add_argument('--jobmode',
                        type=str,
                        default="socket",
                        dest='jobmode'
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
        if opts.jobmode=='socket':
            jobs, results = os.path.join(jobdir, '.jobs'), os.path.join(jobdir, '.results')
            job_client = TCPJobClient(jobs, results)
        else:
            job_client = FolderJobClient(jobdir)
        SLURMClient = APIClient(
            job_client,
            banner="="*40 + "STARTING NODE CLIENT" + "="*40
        )
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

        if opts.jobmode=='socket':
            jobs, results = os.path.join(jobdir, '.jobs'), os.path.join(jobdir, '.results')
            try:
                os.remove(jobs)
            except OSError:
                pass
            try:
                os.remove(results)
            except OSError:
                pass
            job_server = TCPJobServer(jobs, results)
        else:
            job_server = FolderJobServer(jobdir, archivedir)
        SLURMDriver = APIServer(
            job_server,
            endpoints
        )

        print("="*40, "STARTING NODE DRIVER", "="*40)
        SLURMDriver.server_loop(poll_time=opts.polltime, timeout=opts.timeout)