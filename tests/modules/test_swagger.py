from bzt.modules.swagger import SwaggerConverter
from tests import BZTestCase, __dir__


class TestSwaggerConverter(BZTestCase):
    def test_requests_from_paths(self):
        obj = SwaggerConverter(__dir__() + "/../data/petstore.json")
        scenario = obj.convert_to_scenario()
        self.assertEqual(scenario['default-address'], 'petstore.swagger.io/v2')
        self.assertEqual(len(scenario['requests']), 14)
        self.assertEqual([req['url'] for req in scenario['requests']],
                         ['/pet',
                          '/pet/findByStatus',
                          '/pet/findByTags',
                          '/pet/{petId}',
                          '/pet/{petId}/uploadImage',
                          '/store/inventory',
                          '/store/order',
                          '/store/order/{orderId}',
                          '/user',
                          '/user/createWithArray',
                          '/user/createWithList',
                          '/user/login',
                          '/user/logout',
                          '/user/{username}'])
