# Code originally from
# https://github.com/mozilla-services/axe-selenium-python/blob/3cfbdd67c9b40ab03f37b3ba2521f77c2071827b/axe_selenium_python/axe.py
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import json
import os
from io import open

from django.conf import settings

_DEFAULT_SCRIPT = settings.DEFAULT_AXE_SCRIPT or os.path.join(
    os.path.dirname(__file__), "node_modules", "axe-core", "axe.min.js"
)


class Axe:
    def __init__(self, py, script_path=_DEFAULT_SCRIPT):
        self.script_path = script_path
        self.py = py

    def violations(self, report=None):
        """
        Injects aXe into the current document then runs it and returns
        any violations found.

        :param report: Whether to generate a report or not. Can be None,
                       True or a string. If True, write_results is run with
                       the default filename, otherwise used as the filename
                       for write_results. If None or False, write_result is
                       not called.
        :type report: bool, str or None
        :returns: Response from aXe
        :rtype: Dict
        """
        self.inject()
        results = self.run()
        if report:
            if report is True:
                self.write_results(results)
            else:
                self.write_results(results, report)
        return results["violations"]

    def inject(self):
        """
        Recursively inject aXe into all iframes and the top level document.
        """
        with open(self.script_path, "r", encoding="utf8") as f:
            self.py.execute_script(f.read())

    def run(self, context=None, options=None):
        """
        Run axe against the current page.

        :param context: which page part(s) to analyze and/or what to exclude.
        :param options: dictionary of aXe options.
        """
        template = (
            "var callback = arguments[arguments.length - 1];"
            + "axe.run(%s).then(results => callback(results))"
        )
        args = ""

        # If context parameter is passed, add to args
        if context is not None:
            args += "%r" % context
        # Add comma delimiter only if both parameters are passed
        if context is not None and options is not None:
            args += ","
        # If options parameter is passed, add to args
        if options is not None:
            args += "%s" % options

        command = template % args
        response = self.py.execute_async_script(command)
        return response

    def report(self, violations):
        """
        Return readable report of accessibility violations found.

        :param violations: Dictionary of violations.
        :type violations: dict
        :return report: Readable report of violations.
        :rtype: string
        """
        string = ""
        string += "Found " + str(len(violations)) + " accessibility violations:"
        for violation in violations:
            string += (
                "\n\n\nRule Violated:\n"
                + violation["id"]
                + " - "
                + violation["description"]
                + "\n\tURL: "
                + violation["helpUrl"]
                + "\n\tImpact Level: "
                + violation["impact"]
                + "\n\tTags:"
            )
            for tag in violation["tags"]:
                string += " " + tag
            string += "\n\tElements Affected:"
            i = 1
            for node in violation["nodes"]:
                for target in node["target"]:
                    string += "\n\t" + str(i) + ") Target: " + target
                    i += 1
                for item in node["all"]:
                    string += "\n\t\t" + item["message"]
                for item in node["any"]:
                    string += "\n\t\t" + item["message"]
                for item in node["none"]:
                    string += "\n\t\t" + item["message"]
            string += "\n\n\n"
        return string

    def write_results(self, data, name=None):
        """
        Write JSON to file with the specified name.

        :param name: Path to the file to be written to. If no path is passed
                     a new JSON file "results.json" will be created in the
                     current working directory.
        :param output: JSON object.
        """

        if name:
            filepath = os.path.abspath(name)
        else:
            filepath = os.path.join(os.path.getcwd(), "results.json")

        with open(filepath, "w", encoding="utf8") as f:
            try:
                f.write(unicode(json.dumps(data, indent=4)))
            except NameError:
                f.write(json.dumps(data, indent=4))
