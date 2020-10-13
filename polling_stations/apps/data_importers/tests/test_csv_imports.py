from django.test import TestCase

from addressbase.models import UprnToCouncil, Address
from councils.models import Council
from data_importers.tests.stubs import stub_addressimport


# High-level functional tests for import scripts
class ImporterTest(TestCase):
    opts = {"nochecks": True, "verbosity": 0}

    def set_up(self, addressbase, uprns, addresses_name):
        for address in addressbase:
            Address.objects.update_or_create(**address)

        for uprn in uprns:
            UprnToCouncil.objects.update_or_create(pk=uprn, lad="X01000000")

        Council.objects.update_or_create(pk="X01000000", identifiers=["X01000000"])

        cmd = stub_addressimport.Command()
        cmd.addresses_name = addresses_name

        cmd.handle(**self.opts)

    def test_duplicate_uprns(self):
        pass

    def test_uprn_not_in_addressbase(self):
        pass

    def test_uprn_assigned_to_wrong_council(self):
        pass

    def test_postcode_mismatch(self):
        pass

    def test_address_import(self):
        test_params = {
            "uprns": ["1", "2", "3", "4", "5", "6", "7"],
            "addressbase": [
                {"address": "Haringey Park, London", "uprn": "1", "postcode": "N8 9JG"},
                {
                    "address": "36 Abbots Park, London",
                    "uprn": "3",
                    "postcode": "SW2 3QD",
                },
                {"address": "3 Factory Rd, Poole", "uprn": "4", "postcode": "BH16 5HT"},
                {
                    "address": "5-6 Mickleton Dr, Southport",
                    "uprn": "5",
                    "postcode": "PR8 2QX",
                },
                {
                    "address": "80 Pine Vale Cres, Bournemouth",
                    "uprn": "6",
                    "postcode": "BH10 6BJ",
                },
                {
                    "address": "4 Factory Rd, Poole",
                    "uprn": "7",
                    "postcode": "BH16 5HT",  # postcode is 'BH17 5HT' in csv
                },
            ],
            "addresses_name": "addresses.csv",
        }
        self.set_up(**test_params)

        imported_uprns = (
            UprnToCouncil.objects.filter(lad="X01000000")
            .exclude(polling_station_id="")
            .order_by("uprn")
            .values_list("uprn", "polling_station_id")
        )

        self.assertEqual(3, len(imported_uprns))
        expected = {("3", "3"), ("4", "1"), ("6", "2")}
        self.assertEqual(set(imported_uprns), expected)
