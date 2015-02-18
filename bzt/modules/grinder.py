"""
Module holds all stuff regarding Grinder tool usage
"""
import os
import time
import signal

from bzt.modules import ScenarioExecutor, Scenario
from bzt.modules.aggregator import ConsolidatingAggregator, ResultsReader
from bzt.utils import shell_exec


class GrinderExecutor(ScenarioExecutor):
    """
    Grinder executor module
    """

    def __init__(self):
        super(GrinderExecutor, self).__init__()
        self.script = None

        self.properties_file = None
        self.kpi_file = None
        self.process = None
        self.start_time = None
        self.end_time = None
        self.retcode = None
        self.reader = None
        self.stdout_file = None
        self.stderr_file = None

    def __write_base_props(self, fds):
        # base props file
        base_props_file = self.settings.get("properties_file", "")
        if base_props_file:
            fds.write("# Base Properies File Start: %s\n" % base_props_file)
            with open(base_props_file) as bpf:
                fds.write(bpf.read())
            fds.write("# Base Properies File End: %s\n\n" % base_props_file)

        # base props
        base_props = self.settings.get("properties")
        if base_props:
            fds.write("# Base Properies Start\n")
            for key, val in base_props.iteritems():
                fds.write("%s=%s\n" % (key, val))
            fds.write("# Base Properies End\n\n")

    def __write_scenario_props(self, fds, scenario):
        # scenario props file
        script_props_file = scenario.get("properties_file", "")
        if script_props_file:
            fds.write(
                "# Script Properies File Start: %s\n" % script_props_file)
            with open(script_props_file) as spf:
                fds.write(spf.read())
            fds.write(
                "# Script Properies File End: %s\n\n" % script_props_file)

        # scenario props
        local_props = scenario.get("properties")
        if local_props:
            fds.write("# Scenario Properies Start\n")
            for key, val in local_props.iteritems():
                fds.write("%s=%s\n" % (key, val))
            fds.write("# Scenario Properies End\n\n")

    def __write_bzt_props(self, fds):
        # BZT props
        fds.write("# BZT Properies Start\n")
        fds.write("grinder.hostID=grinder-bzt\n")
        fds.write("grinder.script=%s\n" % os.path.realpath(self.script))
        dirname = os.path.realpath(self.engine.artifacts_dir)
        fds.write("grinder.logDirectory=%s\n" % dirname)

        load = self.get_load()
        if load.concurrency:
            if load.ramp_up:
                interval = int(1000 * load.ramp_up / load.concurrency)
                fds.write("grinder.processIncrementInterval=%s\n" % interval)
            fds.write("grinder.processes=%s\n" % int(load.concurrency))
            fds.write("grinder.runs=%s\n" % load.iterations)
            fds.write("grinder.processIncrement=1\n")
            if load.duration:
                fds.write("grinder.duration=%s\n" % int(load.duration * 1000))
        fds.write("# BZT Properies End\n")

    def prepare(self):
        """

        :return:
        """
        scenario = self.get_scenario()
        # TODO: install the tool if missing, just like JMeter

        if Scenario.SCRIPT in scenario:
            self.script = self.engine.find_file(scenario[Scenario.SCRIPT])
            self.engine.existing_artifact(self.script)
        elif "requests" in scenario:
            self.script = self.__scenario_from_requests()
        else:
            raise ValueError("There must be a scenario file to run Grinder")

        self.properties_file = self.engine.create_artifact("grinder", ".properties")

        with open(self.properties_file, 'w') as fds:
            self.__write_base_props(fds)
            self.__write_scenario_props(fds, scenario)
            self.__write_bzt_props(fds)

        self.kpi_file = self.engine.artifacts_dir + os.path.sep
        self.kpi_file += "grinder-bzt-kpi.log"

        self.reader = DataLogReader(self.kpi_file, self.log)
        if isinstance(self.engine.aggregator, ConsolidatingAggregator):
            self.engine.aggregator.add_underling(self.reader)

    def startup(self):
        """
        Should start the tool as fast as possible.
        """
        cmdline = "java -classpath " + os.path.dirname(__file__)
        cmdline += os.path.pathsep + os.path.realpath(self.settings.get("path"))
        cmdline += os.path.sep + "lib" + os.path.sep + "grinder.jar"
        cmdline += " net.grinder.Grinder " + self.properties_file

        self.start_time = time.time()
        out = self.engine.create_artifact("grinder-stdout", ".log")
        err = self.engine.create_artifact("grinder-stderr", ".log")
        self.stdout_file = open(out, "w")
        self.stderr_file = open(err, "w")
        self.process = shell_exec(cmdline, cwd=self.engine.artifacts_dir,
                                  stdout=self.stdout_file,
                                  stderr=self.stderr_file)

    def check(self):
        """
        Checks if tool is still running. Also checks if resulting logs contains
        any data and throws exception otherwise.

        :return: bool
        :raise RuntimeWarning:
        """
        self.retcode = self.process.poll()
        if self.retcode is not None:
            if self.retcode != 0:
                self.log.info("Grinder exit code: %s", self.retcode)
                raise RuntimeError("Grinder exited with non-zero code")

            if self.kpi_file:
                if not os.path.exists(self.kpi_file) \
                        or not os.path.getsize(self.kpi_file):
                    msg = "Empty results log, most likely the tool failed: %s"
                    raise RuntimeWarning(msg % self.kpi_file)
            return True
        return False

    def post_process(self):
        """
        Collect data file artifact
        """
        if self.kpi_file:
            self.engine.existing_artifact(self.kpi_file)

    def shutdown(self):
        """
        If tool is still running - let's stop it.
        """
        while self.process and self.process.poll() is None:
            self.log.info("Terminating Grinder PID: %s", self.process.pid)
            time.sleep(1)
            try:
                os.killpg(self.process.pid, signal.SIGTERM)
            except OSError, exc:
                self.log.debug("Failed to terminate: %s", exc)

            if self.stdout_file:
                self.stdout_file.close()
            if self.stderr_file:
                self.stderr_file.close()

        if self.start_time:
            self.end_time = time.time()
            self.log.debug("Grinder worked for %s seconds",
                           self.end_time - self.start_time)

    def __scenario_from_requests(self):
        script = self.engine.create_artifact("requests", ".py")
        tpl = os.path.dirname(__file__) + os.path.sep + "grinder-requests.tpl"
        self.log.debug("Generating grinder scenario: %s", tpl)
        with open(script, 'w') as fds:
            with open(tpl) as tds:
                fds.write(tds.read())
            for request in self.get_scenario().get_requests():
                line = '\t\trequest.%s("%s")\n' % (request.method, request.url)
                fds.write(line)
        return script


class DataLogReader(ResultsReader):
    """ Class to read KPI from data log """

    def __init__(self, filename, parent_logger):
        super(DataLogReader, self).__init__()
        self.log = parent_logger.getChild(self.__class__.__name__)
        self.filename = filename
        self.fds = None
        self.idx = {}
        self.partial_buffer = ""
        self.delimiter = ","

    def _read(self, last_pass=False):
        """
        Generator method that returns next portion of data

        :param last_pass:
        """
        while not self.fds and not self.__open_fds():
            self.log.debug("No data to start reading yet")
            yield None

        self.log.debug("Reading grinder results")
        if last_pass:
            lines = self.fds.readlines()  # unlimited
        else:
            lines = self.fds.readlines(1024 * 1024)  # 1MB limit to read

        for line in lines:
            if not line.endswith("\n"):
                self.partial_buffer += line
                continue

            line = "%s%s" % (self.partial_buffer, line)
            self.partial_buffer = ""

            line = line.strip()
            fields = line.split(self.delimiter)
            if not fields[1].strip().isdigit():
                self.log.debug("Skipping line: %s", line)
                continue
            ts = int(fields[self.idx["Start time (ms since Epoch)"]]) / 1000.0
            label = ""
            rt = int(fields[self.idx["Test time"]]) / 1000.0
            lt = int(fields[self.idx["Time to first byte"]]) / 1000.0
            rc = fields[self.idx["HTTP response code"]].strip()
            cn = int(fields[self.idx["Time to resolve host"]]) / 1000.0
            cn += int(fields[self.idx["Time to establish connection"]]) / 1000.0
            if int(fields[self.idx["Errors"]]):
                error = "There were some errors in Grinder test"
            else:
                error = None
            concur = None  # TODO: how to get this for grinder
            yield int(ts), label, concur, rt, cn, lt, rc, error

    def __open_fds(self):
        if not os.path.isfile(self.filename):
            self.log.debug("File not appeared yet")
            return False

        if not os.path.getsize(self.filename):
            self.log.debug("File is empty: %s", self.filename)
            return False

        self.fds = open(self.filename)
        header = self.fds.readline().strip().split(self.delimiter)
        for ix, field in enumerate(header):
            self.idx[field.strip()] = ix
        return True