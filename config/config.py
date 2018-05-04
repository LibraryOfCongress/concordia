# TODO: Add correct copyright header

import os
import json

    
class Config():
    """ Singleton that wraps config.json file.
        Has accessor methods for injection. Can override mode and will read override file.
        Mode can be overridden by setting mode in local file named config-optional-override.json.
    """

    doc = None
    mode = "production"
    script_dir = os.path.dirname(os.path.realpath(__file__))
    config_file_name = "config.json"
    config_mode_override_file_name = "config-optional-override.json"

    @classmethod
    def init(cls, path=None):
        """
        init method for class. Finds the config.json file reads the config into doc, using SetFile.

        :param path: Optional, if provided, use it to locate the config.json
        :return:
        """

        if not cls.doc:
            if path:
                cls.SetFile(path)
            else:
                # find config.json file
                found = False
                for path in [cls.config_file_name, os.path.join(cls.script_dir, cls.config_file_name),
                             os.path.join(os.getcwd(), cls.config_file_name)]:
                    if os.path.exists(path):
                        cls.SetFile(path)
                        found = True
                        break
                if not found:
                    raise FileNotFoundError("missing " + cls.config_file_name)

        # if mode override file present, read the mode and set mode
        for path in [cls.config_mode_override_file_name, os.path.join(cls.script_dir, cls.config_mode_override_file_name), os.path.join(os.getcwd(), cls.config_mode_override_file_name)]:
            if os.path.exists(path):
                fi = open(path, 'r')
                try:
                    override = json.load(fi)
                    cls.mode = override["mode"]
                finally:
                    fi.close()
                break

    @classmethod
    def Get(cls, name):
        """
        Accessor method to read value of the name param

        :param name: key to use to lookup value
        :throws: LookupError when key not found in config.json
        :return: value from config.json based on key
        """
        if not cls.doc:
            cls.init()

        if name not in cls.doc[cls.mode]:
            raise LookupError("Missing config key " + name)
        return cls.doc[cls.mode][name]

    @classmethod
    def GetMode(cls, name, mode):
        """
        Accessor method to read value based on the mode

        :param name: key to use to lookup value
        :param mode: mode value to use for lookup
        :return: value from config.json based on key
        :throws: LookupError when key not found in config.json
        """
        if not cls.doc: cls.init()
        if name not in cls.doc[mode]:
            raise LookupError("Missing config key " + name)
        return cls.doc[mode][name]

    @classmethod
    def GetOverrideMode(cls):
        """
        Accessor method to get the override mode

        :return: the mode
        """
        return cls.mode

    @classmethod
    def Set(cls, name, val):
        """
        Setter method to set a key value

        :param name: key
        :param val: value to set
        :return: None
        """
        if not cls.doc: cls.init() 
        cls.doc[cls.mode][name] = val

    @classmethod
    def SetFile(cls, path):
        """
        Setter method to override the config.json file

        When doc is set with the contents of the json values, it is subsequently used as an indicator the class has been
        initialized

        :param path: Full path to the alternate config.json file
        :throws: FileNotFoundError
        :return: None
        """
        if not os.path.exists(path):
            raise FileNotFoundError("missing config file " + path)
        fi = open(path, 'r')
        try:
            cls.doc = json.load(fi)
        finally:
            fi.close()

    @classmethod
    def SetMode(cls, mode):
        """
        Setter to set the mode to read the config.json file

        :param mode: mode to set
        :return:
        """
        cls.mode = mode

    @classmethod
    def __contains__(cls, key):
        """
        Override of __contains__ to check for key in doc

        :param key:
        :return: True if key in doc, otherwise False
        """
        return key in cls.doc[cls.mode]

