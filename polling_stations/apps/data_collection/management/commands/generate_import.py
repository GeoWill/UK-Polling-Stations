from data_collection.import_script import ImportScript
from django.core.management.base import BaseCommand
import subprocess
from pathlib import Path
import re


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument(
            "gss_code", help="The council gss code to generate an import script for."
        )
        parser.add_argument(
            "-w", "--write", action="store_true", help="Write a new script"
        )
        parser.add_argument(
            "-r",
            "--run",
            action="store_true",
            help="Don't just create a new script run it too",
        )
        parser.add_argument(
            "-c",
            "--commit",
            action="store_true",
            help="Don't just create a new script commit it too",
        )

        parser.add_argument(
            "-i",
            "--inspect",
            action="store_true",
            help="Open files in libreoffice, script and dashboard",
        )

        parser.add_argument(
            "-u",
            "--fix-uprns",
            action="store_true",
            help="Uncomment lines containing uprns which are in the new warnings file",
        )

    def handle(self, *args, **options):
        script = ImportScript(options["gss_code"])

        if options["write"]:
            print("writing a new script...")
            script.write_script()

        if options["inspect"]:
            print("Opening files in librecalc")
            print(list(script.files.values()))
            files = [f"{script.council_data_path}/{v}" for v in script.files.values()]
            subprocess.Popen(["libreoffice"] + files)

            # Open dashboard TODO Use webrowser module
            subprocess.run(
                f"firefox http://127.0.0.1:8000/dashboard/council/{script.council_id}/",
                shell=True,
            )

            # Open script in Sublime - TODO change to default editor
            subprocess.Popen(["subl", script.command_path])

        if options["run"]:
            # Run script
            print("running the new script")
            subprocess.run(
                f"./manage.py teardown --all && ./manage.py {script.command_path.stem} -p 2>&1 | tee warning.txt",
                shell=True,
            )

            # refresh materialized view
            subprocess.run(
                (
                    "psql -d polling_stations -U dc -c "
                    "'REFRESH MATERIALIZED VIEW pollingstations_lines_view;'"
                ),
                shell=True,
            )

            print("git grep-ing misc fixes")
            # Search misc fixes
            # Commit hashes are for commits just before misc fixes are deleted, or the last commit to add any.
            subprocess.run(
                (
                    f"git grep --line-number -C 5 '{script.council_id}' 1977a6 890908 972106 2cf506e -- "
                    "polling_stations/apps/data_collection/management/commands/misc_fixes.py"
                ),
                shell=True,
            )

        if options["commit"]:
            print("committing a new script")
            # Add the script
            subprocess.run(f"git add {script.command_path}", shell=True)
            # Commit
            gh_issue_number = script.github_issue.split("/")[-1]
            subprocess.run(
                f'git commit -m "Import script for {script.short_name} (closes #{gh_issue_number})"',
                shell=True,
            )

        if options["fix_uprns"]:
            print("Fixing uprns...")

            script.command_path.rename(f"{script.command_path}.old")

            warnings = (Path().cwd() / "warning.txt").open("r").read()
            warning_uprns = [
                x.group().strip('"') for x in re.finditer(r'"[0-9]*"', warnings)
            ]

            with Path(f"{script.command_path}.old").open(
                "r"
            ) as old_script, script.command_path.open("w") as new_script:
                for line in old_script.readlines():
                    if any(u in line for u in warning_uprns) and line.startswith("#"):
                        line = line[1:]

                    new_script.write(line)

            Path(f"{script.command_path}.old").unlink()

        print(
            f"./manage.py teardown --all && ./manage.py {script.command_path.stem} -p 2>&1 | tee warning.txt"
        )
