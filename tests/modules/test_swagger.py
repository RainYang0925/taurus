import logging

from bzt.modules.swagger import SwaggerConverter
from tests import BZTestCase, __dir__


class TestSwaggerConverter(BZTestCase):
    def test_requests_from_paths(self):
        obj = SwaggerConverter(__dir__() + "/../data/petstore.json", logging.getLogger())
        scenario = obj.convert_to_scenario()
        self.assertEqual(scenario['default-address'], 'http://petstore.swagger.io/v2')
        self.assertEqual(len(scenario['requests']), 5)
        self.assertEqual([req['url'] for req in scenario['requests']],
                         ['http://petstore.swagger.io/v2/pet/findByStatus',
                          'http://petstore.swagger.io/v2/pet/findByTags',
                          'http://petstore.swagger.io/v2/store/inventory',
                          'http://petstore.swagger.io/v2/user/login',
                          'http://petstore.swagger.io/v2/user/logout'])
