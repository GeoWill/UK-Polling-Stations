from django.contrib.gis.geos import Polygon, Point, MultiPolygon
from django.test import TestCase

from addressbase.models import Address, UprnToCouncil
from councils.models import Council
from data_importers.data_types import DistrictSet
from pollingstations.models import PollingDistrict


class DistrictSetTest(TestCase):
    def test_get_polling_station_lookup(self):
        """
        Not to scale...

        4├         ┌╶ ╴┐
        3├         ┊   ┊
        2├ ┌╶ ╴┐   └╶ ╴┘
        1├ ┊*  ┊   *
        0├ └╶ ╴┘
         └ ┴ ─ ┴ ─ ┴ ─ ┴
           0   1   2   3
        """

        Council.objects.update_or_create(pk="X01000001")

        polling_districts = [
            {
                "polling_station_id": "01",
                "area": MultiPolygon(Polygon(((0, 0), (0, 2), (1, 2), (1, 0), (0, 0)))),
                "council": Council.objects.get(pk="X01000001"),
                "internal_council_id": "A",
            },
            {
                "polling_station_id": "02",
                "area": MultiPolygon(Polygon(((2, 2), (2, 4), (3, 4), (3, 2), (2, 2)))),
                "council": Council.objects.get(pk="X01000001"),
                "internal_council_id": "B",
            },
        ]
        addressbase = [
            {"uprn": "1", "location": Point(0.25, 1),},
            {"uprn": "2", "location": Point(2, 1),},
        ]
        uprns = [
            {"uprn": "1", "lad": "X01000001"},
            {"uprn": "2", "lad": "X01000001"},
        ]

        for district in polling_districts:
            PollingDistrict.objects.update_or_create(**district)

        for address in addressbase:
            Address.objects.update_or_create(**address)

        for uprn in uprns:
            UprnToCouncil.objects.update_or_create(**uprn)

        district_set = DistrictSet()
        for element in polling_districts:
            district_set.add(element)

        expected = {"01": {"1"}}
        self.assertEqual(district_set.get_polling_station_lookup(), expected)

    def test_get_polling_station_lookup_uprn_in_districts_overlap(self):
        """
        Not to scale...

        4├    ┌╴╴╴╴┐
        3├ ┌╴╴┼ ┐ *┊
        2├ ┊  ┊*┊  ┊
        1├ ┊* └╴┼╴╴┘
        0├ └╴╴╴╴┘
         └ ┴ ─ ┴ ─ ┴ ─ ┴
           0   1   2   3

        Shows the case where a uprn is in a section of two overlapping districts.
        This can happen as a result of poor digitisation/generalisation errors, but should not
        affect many addresses. We should assign the UPRN to both polling stations, which should then
        be caught by the update_uprn_to_council_model.
        """

        Council.objects.update_or_create(pk="X01000001")

        polling_districts = [
            {
                "polling_station_id": "01",
                "area": MultiPolygon(Polygon(((0, 0), (0, 3), (1.25, 3), (1.25, 0), (0, 0)))),
                "council": Council.objects.get(pk="X01000001"),
                "internal_council_id": "A",
            },
            {
                "polling_station_id": "02",
                "area": MultiPolygon(Polygon(((0.75, 1), (0.75, 4), (2, 4), (2, 1), (0.75, 1)))),
                "council": Council.objects.get(pk="X01000001"),
                "internal_council_id": "B",
            },
        ]
        addressbase = [
            {"uprn": "1", "location": Point(0.25, 1),},
            {"uprn": "2", "location": Point(1, 2),},
            {"uprn": "3", "location": Point(1.75, 3),},
        ]
        uprns = [
            {"uprn": "1", "lad": "X01000001"},
            {"uprn": "2", "lad": "X01000001"},
            {"uprn": "3", "lad": "X01000001"},
        ]

        for district in polling_districts:
            PollingDistrict.objects.update_or_create(**district)

        for address in addressbase:
            Address.objects.update_or_create(**address)

        for uprn in uprns:
            UprnToCouncil.objects.update_or_create(**uprn)

        district_set = DistrictSet()
        for element in polling_districts:
            district_set.add(element)

        expected = {"01": {"1", "2"}, "02": {"2", "3"}}

        self.assertEqual(district_set.get_polling_station_lookup(), expected)


    def test_get_polling_station_lookup_uprn_on_district_boundaries(self):
        """
        Not to scale...

        4├     ┌╶ ╴┐
        3├ ┌╶ ╴┤  *┊
        2├ ┊   *   ┊
        1├ ┊* *├╶ ╴┘
        0├ └╶ ╴┘
         └ ┴ ─ ┴ ─ ┴ ─ ┴
           0   1   2   3

        Shows the case where a uprn is on the boundary of two districts
        This is very unlikely as the point will usually be just one side
        or the other, but we should make sure that we don't accept it when
        this is the case.

        This is why we join on ST_Contains because:
        |   Geometry A contains Geometry B iff no points of B
        |   lie in the exterior of A, and at least one point of
        |   the interior of B lies in the interior of A
        More detail: http://lin-ear-th-inking.blogspot.com/2007/06/subtleties-of-ogc-covers-spatial.html

        In the case of a point in polygon lookup this means the point has to fall inside
        the polygon, NOT on it's boundary.
        """

        Council.objects.update_or_create(pk="X01000001")

        polling_districts = [
            {
                "polling_station_id": "01",
                "area": MultiPolygon(Polygon(((0, 0), (0, 3), (1, 3), (1, 0), (0, 0)))),
                "council": Council.objects.get(pk="X01000001"),
                "internal_council_id": "A",
            },
            {
                "polling_station_id": "02",
                "area": MultiPolygon(Polygon(((1, 1), (1, 4), (2, 4), (2, 1), (1, 1)))),
                "council": Council.objects.get(pk="X01000001"),
                "internal_council_id": "B",
            },
        ]
        addressbase = [
            {"uprn": "1", "location": Point(0.25, 1),},
            {"uprn": "2", "location": Point(0.75, 1),},
            {"uprn": "3", "location": Point(1, 2),},
            {"uprn": "4", "location": Point(1.75, 3),},
        ]
        uprns = [
            {"uprn": "1", "lad": "X01000001"},
            {"uprn": "2", "lad": "X01000001"},
            {"uprn": "3", "lad": "X01000001"},
            {"uprn": "4", "lad": "X01000001"},
        ]

        for district in polling_districts:
            PollingDistrict.objects.update_or_create(**district)

        for address in addressbase:
            Address.objects.update_or_create(**address)

        for uprn in uprns:
            UprnToCouncil.objects.update_or_create(**uprn)

        district_set = DistrictSet()
        for element in polling_districts:
            district_set.add(element)

        expected = {"01": {"1", "2"}, "02": {"4"}}

        self.assertEqual(district_set.get_polling_station_lookup(), expected)

    def test_update_uprn_to_council_model(self):
        Council.objects.update_or_create(pk="X01000001")
        polling_districts = [
            {
                "polling_station_id": "01",
                "area": MultiPolygon(Polygon(((0, 0), (0, 3), (1.25, 3), (1.25, 0), (0, 0)))),
                "council": Council.objects.get(pk="X01000001"),
                "internal_council_id": "A",
            },
            {
                "polling_station_id": "02",
                "area": MultiPolygon(Polygon(((0.75, 1), (0.75, 4), (2, 4), (2, 1), (0.75, 1)))),
                "council": Council.objects.get(pk="X01000001"),
                "internal_council_id": "B",
            },
        ]

        uprns = [
            {"uprn": "1", "lad": "X01000001"},
            {"uprn": "2", "lad": "X01000001"},
            {"uprn": "3", "lad": "X01000001"},
            {"uprn": "4", "lad": "X01000001"},
        ]
        for uprn in uprns:
            UprnToCouncil.objects.update_or_create(**uprn)

        for district in polling_districts:
            PollingDistrict.objects.update_or_create(**district)

        # '2' fell in an overlapping section of the two districts.
        # '4' fell in no districts.
        polling_station_lookup = {"01": {"1", "2"}, "02": {"2", "3"}}
        district_set = DistrictSet()
        for element in polling_districts:
            district_set.add(element)
        district_set.update_uprn_to_council_model(polling_station_lookup=polling_station_lookup)
        updated_uprns = UprnToCouncil.objects.all().order_by('uprn').values_list('uprn', 'polling_station_id')
        self.assertListEqual(list(updated_uprns),
                             [('1', '01'), ('2', ''), ('3', '02'), ('4', '')])
