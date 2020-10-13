"""
Defines the base importer classes to implement
"""
import abc
import json
import glob
import logging
import os

from django.apps import apps
from django.core.management.base import BaseCommand
from django.conf import settings
from django.contrib.gis.geos import Point, GEOSGeometry

from addressbase.models import UprnToCouncil
from councils.models import Council
from data_importers.data_types import AddressList, StationSet
from data_importers.data_quality_report import (
    DataQualityReportBuilder,
    StationReport,
    DistrictReport,
    AddressReport,
)
from data_importers.contexthelpers import Dwellings
from data_importers.filehelpers import FileHelperFactory
from data_importers.loghelper import LogHelper
from data_importers.s3wrapper import S3Wrapper
from pollingstations.models import PollingDistrict, PollingStation
from data_importers.models import DataQuality


class CsvMixin:
    csv_encoding = "utf-8"
    csv_delimiter = ","

    def get_csv_options(self):
        return {"csv_encoding": self.csv_encoding, "csv_delimiter": self.csv_delimiter}


class BaseImporter(BaseCommand, metaclass=abc.ABCMeta):

    """
    Turn off auto system check for all apps
    We will manually run system checks only for the
    'data_importers' and 'pollingstations' apps
    """

    requires_system_checks = False

    srid = 27700
    council_id = None
    base_folder_path = None
    logger = None
    batch_size = None
    imports_districts = False
    use_postcode_centroids = False

    def write_info(self, message):
        if self.verbosity > 0:
            self.stdout.write(message)

    def add_arguments(self, parser):

        parser.add_argument(
            "--nochecks",
            help="<Optional> Do not perform validation checks or display context information",
            action="store_true",
            required=False,
            default=False,
        )

        parser.add_argument(
            "-p",
            "--use-postcode-centroids",
            help="<optional> Use postcode centroids to derive a location for polling stations",
            action="store_true",
            required=False,
            default=False,
        )

    def teardown(self, council):
        PollingStation.objects.filter(council=council).delete()
        PollingDistrict.objects.filter(council=council).delete()
        UprnToCouncil.objects.filter(lad=council).update(polling_station_id="")

    def get_council(self, council_id):
        return Council.objects.get(identifiers__contains=[council_id])

    def get_data(self, filetype, filename):
        options = {}
        if hasattr(self, "get_csv_options"):
            options.update(self.get_csv_options())
        if hasattr(self, "get_shp_options"):
            options.update(self.get_shp_options())

        helper = FileHelperFactory.create(filetype, filename, options)
        return helper.get_features()

    def get_srid(self, type=None):
        if (
            hasattr(self, "districts_srid")
            and type == "districts"
            and self.districts_srid is not None
        ):
            return self.districts_srid
        else:
            return self.srid

    @abc.abstractmethod
    def import_data(self):
        pass

    def post_import(self):
        raise NotImplementedError

    def report(self):
        pass
        # build report
        report = DataQualityReportBuilder(
            self.council_id, expecting_districts=self.imports_districts
        )
        station_report = StationReport(self.council_id)
        district_report = DistrictReport(self.council_id)
        address_report = AddressReport(self.council_id)
        report.build_report()

        # save a static copy in the DB that we can serve up on the website
        record = DataQuality.objects.get_or_create(council_id=self.council_id)
        record[0].report = report.generate_string_report()
        record[0].num_stations = station_report.get_stations_imported()
        record[0].num_districts = district_report.get_districts_imported()
        record[0].num_addresses = address_report.get_addresses_with_station_id()
        record[0].save()

        # output to console
        report.output_console_report()

    @property
    def data_path(self):
        if getattr(settings, "PRIVATE_DATA_PATH", None):
            path = settings.PRIVATE_DATA_PATH
        else:
            s3 = S3Wrapper()
            s3.fetch_data_by_council(self.council_id)
            path = s3.data_path
        return os.path.abspath(path)

    def get_base_folder_path(self):
        if getattr(self, "local_files", True):
            if self.base_folder_path is None:
                path = os.path.join(self.data_path, self.council_id)
                return glob.glob(path)[0]
        return self.base_folder_path

    def handle(self, *args, **kwargs):
        """
        Manually run system checks for the
        'data_importers' and 'pollingstations' apps
        Management commands can ignore checks that only apply to
        the apps supporting the website part of the project
        """
        self.check(
            [
                apps.get_app_config("data_importers"),
                apps.get_app_config("pollingstations"),
            ]
        )

        self.verbosity = kwargs.get("verbosity")
        self.logger = LogHelper(self.verbosity)
        self.validation_checks = not (kwargs.get("nochecks"))
        self.allow_station_point_from_postcode = kwargs.get("use_postcode_centroids")

        if self.council_id is None:
            self.council_id = args[0]

        self.council = self.get_council(self.council_id)
        self.write_info("Importing data for %s..." % self.council.name)

        # Delete old data for this council
        self.teardown(self.council)

        self.base_folder_path = self.get_base_folder_path()

        self.import_data()

        # Optional step for post import tasks
        try:
            self.post_import()
        except NotImplementedError:
            pass

        # save and output data quality report
        if self.verbosity > 0:
            self.report()


class BaseStationsImporter(BaseImporter, metaclass=abc.ABCMeta):

    stations = None

    @property
    @abc.abstractmethod
    def stations_filetype(self):
        pass

    @property
    @abc.abstractmethod
    def stations_name(self):
        pass

    def get_stations(self):
        stations_file = os.path.join(self.base_folder_path, self.stations_name)
        return self.get_data(self.stations_filetype, stations_file)

    @abc.abstractmethod
    def station_record_to_dict(self, record):
        pass

    def get_station_hash(self, station):
        raise NotImplementedError

    def check_station_point(self, station_record):
        if station_record["location"]:
            try:
                council = Council.objects.get(area__covers=station_record["location"])
                if council.council_id != self.council_id:
                    self.logger.log_message(
                        logging.WARNING,
                        "Polling station %s is in %s (%s) but target council is %s (%s) - manual check recommended\n",
                        variable=(
                            station_record["internal_council_id"],
                            council.name,
                            council.council_id,
                            self.council.name,
                            self.council.council_id,
                        ),
                    )
            except Council.DoesNotExist:
                self.logger.log_message(
                    logging.WARNING,
                    "Polling station %s is not covered by any council area - manual check recommended\n",
                    variable=(station_record["internal_council_id"]),
                )

    def import_polling_stations(self):
        stations = self.get_stations()
        if not isinstance(self, BaseAddressesImporter):
            self.write_info(
                "Stations: Found %i features in input file" % (len(stations))
            )
        seen = set()
        for station in stations:
            """
            We can optionally define a function get_station_hash()

            This is useful if residential addresses and polling
            station details are embedded in the same input file

            We can use this to avoid calling station_record_to_dict()
            (which is potentially quite a slow operation)
            on a record where we have already processed the station data
            to make the import process run more quickly.
            """
            try:
                station_hash = self.get_station_hash(station)
                if station_hash in seen:
                    continue
                else:
                    self.logger.log_message(
                        logging.INFO,
                        "Polling station added to set:\n%s",
                        variable=station,
                        pretty=True,
                    )
                    seen.add(station_hash)
            except NotImplementedError:
                pass

            if self.stations_filetype in ["shp", "shp.zip"]:
                record = station.record
            else:
                record = station
            station_info = self.station_record_to_dict(record)

            """
            station_record_to_dict() will usually return a dict
            but it may also optionally return a list of dicts.

            This is helpful if we encounter a polling station record
            with a delimited list of polling districts served by this
            polling station: it allows us to add the same station
            address/point many times with different district ids.
            """
            if isinstance(station_info, list):
                self.logger.log_message(
                    logging.INFO,
                    "station_record_to_dict() returned list with input:\n%s",
                    variable=record,
                    pretty=True,
                )
                station_records = station_info
            else:
                # If station_info is a dict, create a singleton list
                station_records = [station_info]

            for station_record in station_records:

                """
                station_record_to_dict() may optionally return None
                if we want to exclude a particular station record
                from being imported
                """
                if station_record is None:
                    self.logger.log_message(
                        logging.INFO,
                        "station_record_to_dict() returned None with input:\n%s",
                        variable=record,
                        pretty=True,
                    )
                    continue

                if "council" not in station_record:
                    station_record["council"] = self.council

                """
                If the file type is shp, we can usually derive 'location'
                automatically, but we can return it if necessary.
                For other file types, we must return the key
                'location' from station_record_to_dict()
                """
                if (
                    self.stations_filetype in ["shp", "shp.zip"]
                    and "location" not in station_record
                ):
                    if len(station.shape.points) == 1:
                        # we've got a point
                        station_record["location"] = Point(
                            *station.shape.points[0], srid=self.get_srid()
                        )
                    else:
                        # its a polygon: simplify it to a centroid and warn
                        self.logger.log_message(
                            logging.WARNING,
                            "Implicitly converting station geometry to point",
                        )
                        geojson = json.dumps(station.shape.__geo_interface__)
                        poly = self.clean_poly(GEOSGeometry(geojson))
                        poly.srid = self.get_srid()
                        station_record["location"] = poly.centroid

                if self.validation_checks:
                    self.check_station_point(station_record)
                self.add_polling_station(station_record)

    def add_polling_station(self, station_info):
        self.stations.add(station_info)


class BaseAddressesImporter(BaseImporter, metaclass=abc.ABCMeta):

    addresses = None

    @property
    @abc.abstractmethod
    def addresses_filetype(self):
        pass

    @property
    @abc.abstractmethod
    def addresses_name(self):
        pass

    def get_addresses(self):
        addresses_file = os.path.join(self.base_folder_path, self.addresses_name)
        return self.get_data(self.addresses_filetype, addresses_file)

    @abc.abstractmethod
    def address_record_to_dict(self, record):
        pass

    def write_context_data(self):
        dwellings = Dwellings()
        self.write_info("----------------------------------")
        self.write_info("Contextual Data:")
        self.write_info(
            "Total UPRNs in AddressBase: {:,}".format(
                dwellings.from_addressbase(self.council.area)
            )
        )
        self.write_info(
            "Total Dwellings from 2011 Census: {:,}".format(
                dwellings.from_census(self.council_id)
            )
        )
        self.write_info("----------------------------------")

    def import_residential_addresses(self):
        if self.validation_checks:
            self.write_context_data()
        addresses = self.get_addresses()
        self.write_info(
            "Addresses: Found {:,} rows in input file".format(len(addresses))
        )
        self.write_info("----------------------------------")
        for address in addresses:
            address_info = self.address_record_to_dict(address)

            if address_info is None:
                self.logger.log_message(
                    logging.INFO,
                    "address_record_to_dict() returned None with input:\n%s",
                    variable=address,
                    pretty=True,
                )
                continue

            self.add_residential_address(address_info)

    def add_residential_address(self, address_info):

        if "council" not in address_info:
            address_info["council"] = self.council

        if "uprn" not in address_info:
            address_info["uprn"] = ""
        else:
            # UPRNs less than 12 characters long may be left padded with zeros
            # Making sure uprns in our addresslist are not left padded will help with matching them
            # and catching duplicates.
            address_info["uprn"] = str(address_info["uprn"]).lstrip("0")

        self.addresses.append(address_info)


class BaseStationsAddressesImporter(BaseStationsImporter, BaseAddressesImporter):
    def pre_import(self):
        raise NotImplementedError

    def import_data(self):

        # Optional step for pre import tasks
        try:
            self.pre_import()
        except NotImplementedError:
            pass

        self.stations = StationSet()
        self.addresses = AddressList(self.logger)
        self.import_residential_addresses()
        self.import_polling_stations()
        self.addresses.check_records()
        self.addresses.update_uprn_to_council_model()
        self.stations.save()


class BaseCsvStationsCsvAddressesImporter(BaseStationsAddressesImporter, CsvMixin):
    """
    Stations in CSV format
    Addresses in CSV format
    """

    stations_filetype = "csv"
    addresses_filetype = "csv"

