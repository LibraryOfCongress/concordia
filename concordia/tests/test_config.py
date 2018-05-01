# TODO: Add copyright header
import os
import sys

import unittest

from shutil import copyfile

scriptDir = os.path.dirname(os.path.realpath(__file__))
sys.path.append(os.path.join(scriptDir, "../"))
sys.path.append(os.path.join(scriptDir, "../../config"))


from config import Config


class ConfigTest(unittest.TestCase):
    """
    This is a standard python unit test, not a django TestCase. We don't want to run a django environment where a
    test_database is created.
    """
    def setUpClass(cls):
        with open("../../config/config-optional-override.json", "w") as override_file:
            override_file.write('{"mode":"production"}')

    def setUp(self):
        # save existing override value
        with open("../../config/config-optional-override.json", "r") as override_file:
            self.current_override_settings = override_file.read()

    def tearDown(self):
        # restore existing override settings
        with open("../../config/config-optional-override.json", "w") as override_file:
            override_file.write(self.current_override_settings)

        # copy the default config.json
        copyfile('../../config/config.json.default', '../../config/config.json')


    def test_get_production(self):
        """
        Test settings using Config are from the production stanza
        :return:
        """

        # Arrange
        # make sure the config-optional-override.json value is set to "production"
        with open("../../config/config-optional-override.json", "w") as override_file:
            override_file.write('{"mode":"production"}')

        # Act
        database_port = Config.Get("database")["port"]

        # Assert
        self.assertEqual(database_port, '5432')

    def xtest_get_alternate_file_path(self):
        """
        Test init and get using an alternate config.json file
        :return:
        """

        # Arrange

        # save exisitng config.json
        copyfile('../../config/config.json.default', 'config.jsonTMP')


        # Create alternate config.json
        with open("config-alternate.json", "w") as alternate_file:
            alternate_file.write('{"production": {"logLevel"  : "ALTERNATE"}}')

        # Act
        Config.init("config-alternate.json")
        log_level = Config.Get('logLevel')

        # Assert
        self.assertEqual(log_level, 'ALTERNATE')

    def test_get_bad_lookup(self):
        """
        Test trying to get a config value using a bad key
        :return:
        """
        # Arrange
        # make sure the config-optional-override.json value is set to "production"
        with open("../../config/config-optional-override.json", "w") as override_file:
            override_file.write('{"mode":"production"}')

        # Act
        with self.assertRaises(LookupError) as context:
            database_port = Config.Get("blah")

        # Asset
        self.assertTrue('Missing config key blah' in context.exception.args)

    def test_get_mode(self):
        """
        Test getting the mode
        :return:
        """
        # make sure the config-optional-override.json value is set to "production"
        with open("../../config/config-optional-override.json", "w") as override_file:
            override_file.write('{"mode":"production"}')

        # Act
        mode = Config.GetOverrideMode()

        # Assert
        self.assertEqual(mode, 'production')

    def test_set_value(self):
        """
        Test setting a value in config.json
        :return:
        """

        # Arrange
        # make sure the config-optional-override.json value is set to "production"
        with open("../../config/config-optional-override.json", "w") as override_file:
            override_file.write('{"mode":"production"}')

        # Act
        Config.Set('foo', 'bar')
        foo_value = Config.Get('foo')

        # Assert
        self.assertEqual(foo_value, 'bar')

    def test_get_with_mode(self):
        """
        Test getting a config for a mode stanza
        :return:
        """

        # Arrange
        # make sure the config-optional-override.json value is set to "production"
        with open("../../config/config-optional-override.json", "w") as override_file:
            override_file.write('{"mode":"production"}')

        # Act
        port = Config.GetMode('logLevel', 'production')

        # Assert
        self.assertEqual(port, 'INFO')
