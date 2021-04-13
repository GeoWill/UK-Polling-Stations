from data_importers.ems_importers import BaseHalaroseCsvImporter


class Command(BaseHalaroseCsvImporter):

    council_id = "GRT"
    addresses_name = "2021-03-05T15:09:15.797593/polling_station_export-2021-03-05.csv"
    stations_name = "2021-03-05T15:09:15.797593/polling_station_export-2021-03-05.csv"
    elections = ["2021-05-06"]

    def address_record_to_dict(self, record):
        if record.housepostcode in ["GU1 1AD", "GU23 7JL"]:
            return None
        return super().address_record_to_dict(record)

    def station_record_to_dict(self, record):
        # Update from Council
        if (
            record.pollingstationnumber == "39"
            and record.pollingstationname == "The Green Room"
        ):
            record = record._replace(
                pollingstationname="East Horsley Village Hall",
                pollingstationaddress_1="Kingston Avenue",
                pollingstationaddress_2="East Horsley",
                pollingstationaddress_3="Leatherhead",
                pollingstationaddress_4="",
                pollingstationpostcode="KT24 6QT",
            )

        return super().station_record_to_dict(record)
