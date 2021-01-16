"""
Tiny python script that can run in the background and submit SLURM jobs when they're written
to file by delegating to `subprocess.call`
"""

import json, subprocess, os, datetime, argparse, abc, threading, time, traceback as tb

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
            check=True, stdout=subprocess.PIPE,
            **kwargs
            )
        stdout = runny.stdout
        if stdout is not None:
            stdout = stdout.decode().splitlines()
        return stdout

class APIDriver:
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
                endpoint, list(self.endpoints.keys()))
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
            err_msg = tb.format_exc()
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
                    job['status']='complete'
                    with open(job['file'], 'w') as jf:
                        json.dump(job, jf, indent=4)
                    self._active = False
                    break
                else:
                    active.append([job, self.handle_job(job)])
            for job, thread in active:
                thread.join(timeout=timeout)
                if thread.is_alive():
                    job['status'] = "timeout"
                    job['output'] = ""
                    with open(job['file'], 'w') as jf:
                        json.dump(job, jf, indent=4)
                    print("ERROR: dangling thread never timed-out")
            time.sleep(poll_time)

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
    opts = parser.parse_args()
    jobdir = opts.jobdir
    archivedir = opts.archivedir
    if archivedir == "":
        archivedir = os.path.join(jobdir, 'archive')
    SLURMDriver = APIDriver(
        jobdir, archivedir,
        [
            SubprocessEndPoint('sbatch'),
            SubprocessEndPoint('squeue'),
            SubprocessEndPoint('sinfo'),
            SubprocessEndPoint('sinfo')
        ]
    )

    print("="*40, "STARTING SLURM DRIVER", "="*40)
    SLURMDriver.server_loop(poll_time=opts.polltime, timeout=opts.timeout)