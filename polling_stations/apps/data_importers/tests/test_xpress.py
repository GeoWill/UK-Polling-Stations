from django.test import TestCase

from councils.models import Council
from data_importers.tests.stubs import stub_xpress_democlub
from pollingstations.models import PollingStation
from addressbase.models import UprnToCouncil, Address


class XpressDemocracyClubImportTests(TestCase):

    opts = {"nochecks": True, "verbosity": 2}
    uprns = ["1", "2", "3", "4", "5"]
    addressbase = [
        {
            "address": "1 Abbots Way, Lancing, West Sussex",
            "postcode": "BN15 9DH",
            "uprn": "1",
        },
        {
            "address": "2 Abbots Way, Lancing, West Sussex",
            "postcode": "BN15 9DH",
            "uprn": "2",
        },
        {
            "address": "2 Freshbrook Mews, Freshbrook Road, Lancing, West Sussex",
            "postcode": "BN15 8DA",
            "uprn": "3",
        },
        {
            "address": "2 Freshbrook Mews, Freshbrook Road, Lancing, West Sussex",
            "postcode": "BN15 8DA",
            "uprn": "4",
        },
        {
            "address": "1 Freshbrook Mews, Freshbrook Road, Lancing, West Sussex",
            "postcode": "BN15 8DA",
            "uprn": "5",
        },
    ]

    def setUp(self):
        for address in self.addressbase:
            Address.objects.update_or_create(**address)

        Council.objects.update_or_create(pk="X01000000", identifiers=["X01000000"])
        for uprn in self.uprns:
            UprnToCouncil.objects.update_or_create(pk=uprn, lad="X01000000")
        cmd = stub_xpress_democlub.Command()
        cmd.handle(**self.opts)

    def test_addresses(self):
        imported_uprns = (
            UprnToCouncil.objects.filter(lad="X01000000")
            .exclude(polling_station_id="")
            .order_by("uprn")
            .values_list("uprn", flat=True)
        )

        # 4 records should have been inserted, and one discarded
        self.assertEqual(4, len(imported_uprns))
        expected = set(["1", "2", "4", "5"])
        self.assertEqual(set(imported_uprns), expected)

    def test_station_ids(self):
        self.assertEqual(
            "518", UprnToCouncil.objects.get(uprn="1").polling_station_id,
        )
        self.assertEqual(
            "518", UprnToCouncil.objects.get(uprn="2").polling_station_id,
        )
        self.assertEqual(
            "512", UprnToCouncil.objects.get(uprn="4").polling_station_id,
        )
        self.assertEqual(
            "512", UprnToCouncil.objects.get(uprn="5").polling_station_id,
        )

    def test_stations(self):
        stations = (
            PollingStation.objects.filter(council_id="X01000000")
            .order_by("internal_council_id")
            .values_list("address", flat=True)
        )

        # check we inserted 2 stations
        self.assertEqual(2, len(stations))
        expected = {
            "Lancing Parish Hall\nSouth Street\nLancing",
            "Monks Farm Hall\nNorth Road\nLancing",
        }
        self.assertEqual(set(stations), expected)