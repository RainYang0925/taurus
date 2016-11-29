"""
Swagger converter for Taurus project.

Copyright 2016 BlazeMeter Inc.

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
import json
import os
from collections import OrderedDict

import yaml
import yaml.constructor

from bzt.engine import Service
from bzt.six import iteritems


class SwaggerConverterService(Service):
    def __init__(self):
        super(SwaggerConverterService, self).__init__()
        self.swagger_spec = None
        self.converter = None

    def prepare(self):
        self.swagger_spec = self.parameters.get("spec", ValueError("'spec' parameter is required"))
        self.converter = SwaggerConverter(self.converter)

    def startup(self):
        pass

    def check(self):
        pass

    def shutdown(self):
        pass

    def post_process(self):
        pass


class OrderedDictYAMLLoader(yaml.Loader):
    """
    A YAML loader that loads mappings into ordered dictionaries.
    """

    def __init__(self, *args, **kwargs):
        yaml.Loader.__init__(self, *args, **kwargs)

        self.add_constructor(u'tag:yaml.org,2002:map', type(self).construct_yaml_map)
        self.add_constructor(u'tag:yaml.org,2002:omap', type(self).construct_yaml_map)

    def construct_yaml_map(self, node):
        data = OrderedDict()
        yield data
        value = self.construct_mapping(node)
        data.update(value)

    def construct_mapping(self, node, deep=False):
        if isinstance(node, yaml.MappingNode):
            self.flatten_mapping(node)
        else:
            tmpl = 'expected a mapping node, but found %s'
            raise yaml.constructor.ConstructorError(None, None, tmpl % node.id, node.start_mark)

        mapping = OrderedDict()
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            try:
                hash(key)
            except TypeError, exc:
                raise yaml.constructor.ConstructorError(
                    'while constructing a mapping',
                    node.start_mark,
                    'found unacceptable key (%s)' % exc,
                    key_node.start_mark)
            value = self.construct_object(value_node, deep=deep)
            mapping[key] = value
        return mapping


class SwaggerConverter(object):
    def __init__(self, spec_file):
        self.spec_file = spec_file
        self.spec_dict = None

    def _read_spec(self):
        if not os.path.exists(self.spec_file):
            raise ValueError("File %s doesn't exist" % self.spec_file)
        with open(self.spec_file) as fds:
            self.spec_dict = json.load(fds, object_pairs_hook=OrderedDict)
            # self.spec_dict = yaml.load(fds, OrderedDictYAMLLoader)

    def convert_to_scenario(self):
        """
        Converts Swagger spec to Taurus-style scenario dict.
        :return: dict
        """
        self._read_spec()

        scenario = {}
        if self.spec_dict.get('host'):
            scenario['default-address'] = self.spec_dict['host']
        if self.spec_dict.get('basePath'):
            scenario['default-address'] += self.spec_dict['basePath']

        scenario['requests'] = []
        for path, path_info in iteritems(self.spec_dict.get('paths')):
            request = {}
            request['url'] = path  # TODO: handle path object 'parameters'
            scenario['requests'].append(request)

        return scenario
