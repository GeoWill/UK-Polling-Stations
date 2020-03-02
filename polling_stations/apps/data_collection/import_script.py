from data_collection.s3wrapper import S3Wrapper
from datetime import datetime
from django.conf import settings
from pathlib import Path
import json


class ImportScript(object):
    """
    # Automate Import script creation

    ## Workflow

    * CSV uploaded and trigger creates an issue on github.
    * Run a command locally that takes a gss code as an argument e.g. `python manage.py generate_import E07000092`:
        - Get the most recent `report.json` from the data directory
        - if there is no local branch then create one.
        - create a commit which contains an attempt to update the script

    ## ImportScript class

    Class to represent an import script.

    Import scripts have a few distinct sections which determine the sort of data the class should hold.
    * Imports
    * Properties
        - council_id
        - addresses_name
        - stations_name
        - districts_name
        - elections
        - csv_delimiter
    * Methods
        - district_record_to_dict
        - address_record_to_dict
        - station_record_to_dict

    There are also a few things that will be helpful to know about (which are usefully in the report):
    * Report (where the report is to get most of the below)
    * Github issue (to make the commit message)
    * Council Name (to make a command if required)
    * EMS (to expose the right methods and properties)
    * Path (where the script module is - not derived from report)

    TODO
    * Write some tests
    * Imports aren't handled well at the moment
    * Methods aren't handled at all.
        * specifically it would be great to check for uprns that are being used for  setting the 'accept suggestion'
          flag that still appear in the output when the command is run. However that requires a second pass over the
          script with a 'warning.txt' file present. This probably means that the ImportScript class should be able to
          parse such a file.
    * Doesn't handle democracy counts at all.
    * There should be an option in instantiate from a script, then perhaps an 'update method' so that we can get the old script and the new script.
    """

    def __init__(self, council_id):
        self.council_id = council_id
        self._report = ""
        self._command_path = ""
        self.elections = ["2020-05-07"]
        self.files = self.get_files()
        self.methods = {
            "district_record_to_dict": [],
            "address_record_to_dict": [],
            "station_record_to_dict": [],
        }

    import_lookup = {
        "Idox Eros (Halarose)": "BaseHalaroseCsvImporter",
        "Xpress WebLookup": "BaseXpressWebLookupCsvImporter",
        "Xpress DC": "BaseXpressDemocracyClubCsvImporter",
        "Democracy Counts": "BaseDemocracyCountsCsvImporter",
    }

    @property
    def ems(self):
        return self.report["file_set"][0]["ems"]

    @property
    def github_issue(self):
        return self.report["github_issue"]

    @property
    def council_data_path(self):
        if getattr(settings, "PRIVATE_DATA_PATH", None):
            path = settings.PRIVATE_DATA_PATH
        else:
            s3 = S3Wrapper()
            s3.fetch_data_by_council(self.council_id)
            path = s3.data_path
        return (Path(path) / self.council_id).resolve()

    @property
    def report(self):
        def valid_date(date_str):
            try:
                datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S.%f")
            except ValueError:
                return False
            return True

        report_path = None
        if not self._report:
            dirs = [
                d
                for d in self.council_data_path.iterdir()
                if d.is_dir() and valid_date(d.name)
            ]
            newest_dir = sorted(dirs, key=lambda d: d.name)[-1]
            try:
                report_path = newest_dir / "report.json"
                with report_path.open() as fp:
                    self._report = json.load(fp)
            except FileNotFoundError as e:
                print(e)

        if self._report["gss"] != self.council_id:
            print(
                f'WARNING: Report gss ({self._report["gss"]}) does not match self.council_id ({self.council_id})\n',
                f"Report path: {report_path.name}",
            )
        return self._report

    @property
    def short_name(self):
        short_name = self.report["council_name"]
        extras = [
            " London Borough of",  # Don't throw away 'London'
            " City & District Council",  # Don't throw away 'City'
            " City Council",  # Don't throw away 'City'
            " Metropolitan",
            " Borough",
            " Council",
        ]
        for extra in extras:
            short_name = short_name.replace(extra, "")
        return short_name

    @property
    def command_path(self):
        if self._command_path:
            return self._command_path

        scripts = Path(
            "./polling_stations/apps/data_collection/management/commands/"
        ).glob("import_*.py")
        for script in scripts:
            with Path(script).open() as f:
                for line in f:
                    if self.council_id in line:
                        self._command_path = script
        if not self._command_path:
            self._command_path = Path(
                f'./polling_stations/apps/data_collection/management/commands/import_{self.short_name.lower().replace(" ", "_")}'
            )
            self._command_path.touch()

        return self._command_path

    def get_files(self):
        if self.ems in ["Idox Eros (Halarose)", "Xpress DC"]:
            file = "/".join(self.report["file_set"][0]["key"].split("/")[1:])
            files = {
                "addresses_name": file,
                "stations_name": file,
            }
        else:
            files = {}
            # TODO Deal with Democracy Counts

        return files

    @property
    def cmd_import(self):
        return f"from data_collection.management.commands import {self.import_lookup[self.ems]}\n"

    def write_script(self):
        self.command_path.rename(f"{self.command_path}.old")
        tmp_command_path = Path(f"{self.command_path}.old")
        with tmp_command_path.open("r") as old_f, self.command_path.open("w") as new_f:
            new_f.write(self.cmd_import)
            for line in old_f.readlines():
                if line == self.cmd_import:
                    line = ""
                elif line.startswith("class"):
                    line = f"class Command({self.import_lookup[self.ems]}):\n"
                elif line.startswith("    addresses_name"):
                    line = f"    addresses_name = \"{self.files['addresses_name']}\"\n"
                elif line.startswith("    stations"):
                    line = f"    stations_name = \"{self.files['stations_name']}\"\n"
                elif line.startswith("    elections"):
                    line = '    elections = ["2020-05-07"]\n'
                elif line.startswith("    csv_delimiter"):
                    if self.files["addresses_name"].endswith("tsv"):
                        delim = "\\t"
                    else:
                        delim = ","
                    line = f'    csv_delimiter = "{delim}"\n'
                # Comment out everything else
                elif line != "\n" and "council_id" not in line:
                    line = f"# {line}"
                new_f.write(line)

            new_f.write("\n")

        tmp_command_path.unlink()
