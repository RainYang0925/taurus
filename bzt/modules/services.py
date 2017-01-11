"""
Implementations for small services

Copyright 2015 BlazeMeter Inc.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

   http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import copy
import os
import subprocess
import time
import zipfile

from bzt import NormalShutdown, ToolError, TaurusConfigError
from bzt.engine import Service, HavingInstallableTools
from bzt.modules.selenium import Node
from bzt.six import get_stacktrace
from bzt.utils import get_full_path, shutdown_process, shell_exec, RequiredTool
from bzt.utils import replace_in_config, JavaVM


class Unpacker(Service):
    UNPACK = 'unpacker'
    FILES = 'files'

    def __init__(self):
        super(Unpacker, self).__init__()
        self.files = []

    def prepare(self):
        packed_list = copy.deepcopy(self.parameters.get(Unpacker.FILES, self.files))
        unpacked_list = []
        for archive in packed_list:
            full_archive_path = self.engine.find_file(archive)
            self.log.debug('Unpacking %s', archive)
            with zipfile.ZipFile(full_archive_path) as zip_file:
                zip_file.extractall(self.engine.artifacts_dir)

            archive = os.path.basename(archive)
            unpacked_list.append(archive[:-4])  # TODO: replace with top-level archive content

        replace_in_config(self.engine.config, packed_list, unpacked_list, log=self.log)


class InstallChecker(Service):
    def prepare(self):
        modules = self.engine.config.get("modules")
        failure = None
        for mod_name in modules.keys():
            try:
                self._check_module(mod_name)
            except BaseException as exc:
                self.log.error("Failed to instantiate module %s", mod_name)
                self.log.debug("%s", get_stacktrace(exc))
                failure = exc if not failure else failure

        if failure:
            raise ToolError("There were errors while checking for installed tools, see messages above")

        raise NormalShutdown("Done checking for tools installed, will exit now")

    def _check_module(self, mod_name):
        mod = self.engine.instantiate_module(mod_name)

        if not isinstance(mod, HavingInstallableTools):
            self.log.debug("Module %s has no install needs")
            return

        self.log.info("Checking installation needs for: %s", mod_name)
        mod.install_required_tools()
        self.log.info("Module is fine: %s", mod_name)


class AndroidEmulatorLoader(Service):
    def __init__(self):
        super(AndroidEmulatorLoader, self).__init__()
        self.emulator_process = None
        self.tool_path = ''
        self.startup_timeout = None

    def prepare(self):
        self.startup_timeout = self.settings.get('timeout', 30)
        config_tool_path = self.settings.get('path', '')
        if config_tool_path:
            self.tool_path = get_full_path(config_tool_path)
            os.environ['ANDROID_HOME'] = get_full_path(config_tool_path, step_up=2)
            self.settings['path'] = self.tool_path
        else:
            # try to read sdk path from env..
            sdk_path = os.environ.get('ANDROID_HOME')
            if sdk_path:
                env_tool_path = os.path.join(sdk_path, 'tool', 'emulator')
                self.tool_path = get_full_path(env_tool_path)
                self.settings['path'] = self.tool_path
            else:
                message = 'Taurus can''t find Android SDK automatically, you must point to emulator with modules.'
                message += 'android-emulator.path config parameter or set ANDROID_HOME environment variable'
                raise TaurusConfigError(message)

        tool = AndroidEmulator(self.tool_path, "", self.log)
        if not tool.check_if_installed():
            tool.install()

    def startup(self):
        self.log.debug('Starting android emulator...')
        exc = TaurusConfigError('You must choose an emulator with modules.android-emulator.avd config parameter')
        avd = self.settings.get('avd', exc)
        self.emulator_process = shell_exec([self.tool_path, '-avd', avd])
        start_time = time.time()
        while not self.tool_is_started():
            time.sleep(1)
            if time.time() - start_time > self.startup_timeout:
                raise ToolError("Appium cannot be loaded")

        self.log.debug('Appium was started successfully')

    def tool_is_started(self):
        try:
            pass
            # look at adb in the system or in platform tools dir. warning if adb not found and return true
            # get output of 'adb devices'
            # check if avd in that list and return true/false accordingly
            return True
        except:
            return False

    def shutdown(self):
        if self.emulator_process:
            self.log.debug('Stopping android emulator...')
            shutdown_process(self.emulator_process, self.log)


class AppiumLoader(Service):
    def __init__(self):
        super(AppiumLoader, self).__init__()
        self.appium_process = None
        self.tool_path = ''
        self.startup_timeout = None
        self.addr = ''
        self.port = ''

    def prepare(self):
        self.startup_timeout = self.settings.get('timeout', 30)
        self.addr = self.settings.get('addr', '127.0.0.1')
        self.port = self.settings.get('port', 4723)
        self.settings.get('path', 'appium')

        required_tools = [Node(self.log),
                          JavaVM("", "", self.log),
                          Appium(self.tool_path, "", self.log)]

        for tool in required_tools:
            if not tool.check_if_installed():
                tool.install()

    def startup(self):
        self.log.debug('Starting appium...')
        self.appium_process = shell_exec([self.tool_path])

        start_time = time.time()
        while not self.tool_is_started():
            time.sleep(1)
            if time.time() - start_time > self.startup_timeout:
                raise ToolError("Appium cannot be loaded")

        self.log.debug('Appium was started successfully')

    def tool_is_started(self):
        try:
            pass
            # get self.addr:self.port/wd/hub/sessions
            # convert from string as json
            return True
        except:
            return False

    def shutdown(self):
        if self.appium_process:
            self.log.debug('Stopping appium...')
            shutdown_process(self.appium_process, self.log)


class Appium(RequiredTool):
    def __init__(self, tool_path, download_link, parent_logger):
        super(Appium, self).__init__("Appium", tool_path, download_link)
        self.log = parent_logger.getChild(self.__class__.__name__)

    def check_if_installed(self):
        cmd = [self.tool_path, '--version']
        self.log.debug("Trying %s: %s", self.tool_name, cmd)
        try:
            output = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
            self.log.debug("%s output: %s", self.tool_name, output)
            return True
        except (subprocess.CalledProcessError, IOError, OSError) as exc:
            self.log.debug("Failed to check %s: %s", self.tool_name, exc)
            return False

    def install(self):
        raise ToolError("Automatic installation of %s is not implemented. Install it manually" % self.tool_name)


class AndroidEmulator(RequiredTool):
    def __init__(self, tool_path, download_link, parent_logger):
        super(AndroidEmulator, self).__init__("AndroidEmulator", tool_path, download_link)
        self.log = parent_logger.getChild(self.__class__.__name__)

    def check_if_installed(self):
        cmd = [self.tool_path, '-list-avds']
        self.log.debug("Trying %s: %s", self.tool_name, cmd)
        try:
            output = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
            self.log.debug("%s output: %s", self.tool_name, output)
            return True
        except (subprocess.CalledProcessError, IOError, OSError) as exc:
            self.log.debug("Failed to check %s: %s", self.tool_name, exc)
            return False

    def install(self):
        raise ToolError("Automatic installation of %s is not implemented. Install it manually" % self.tool_name)
