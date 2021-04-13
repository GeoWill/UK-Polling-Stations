from data_importers.management.commands import BaseDemocracyCountsCsvImporter


class Command(BaseDemocracyCountsCsvImporter):
    council_id = "WKF"
    addresses_name = (
        "2021-03-24T10:33:03.462547/Democracy Club Polling Districts 24_03_21.csv"
    )
    stations_name = (
        "2021-03-24T10:33:03.462547/Democracy Club Polling Stations 24_03_21.csv"
    )
    elections = ["2021-05-06"]

    def address_record_to_dict(self, record):
        if record.postcode.strip() in [
            "WF2 6QY",
            "WF4 1PU",
            "WF4 6DL",
            "WF5 0RT",
            "WF8 4EB",
            "WF2 6JA",
        ]:
            return None  # split

        if record.postcode.strip() in [
            # spurious distance for one property, would be unsplit if removed alone
            "WF9 3AB",
            "WF10 2SR",
            # two properties at same point, different polling stations
            "WF10 2RH",
        ]:
            return None

        return super().address_record_to_dict(record)

    def station_record_to_dict(self, record):
        # Council sent through various amendments:
        if record.stationcode == "12NF":
            record = record._replace(placename="Kings Croft")

        if record.stationcode == "15MG":
            record = record._replace(
                placename="Temporary Polling Station",
                add1="Land Opposite Lofthouse Gate Working Men's Club",
                add2="Canal Lane",
                add3="Lofthouse Gate",
                add4="Wakefield",
                postcode="WF3 3HN",
                xordinate="433449",
                yordinate="424608",
            )
        if record.stationcode == "03NE":
            record = record._replace(
                placename="Ackton Pastures Primary",
                add1="College Grove",
                add2="Whitwood",
                add3="Castleford",
                add4="",
                postcode="WF10 5NS",
                xordinate="441485",
                yordinate="424563",
            )

        return super().station_record_to_dict(record)
