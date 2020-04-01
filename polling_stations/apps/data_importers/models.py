from django.db import models

from councils.models import Council


class DataQuality(models.Model):
    class Meta:
        verbose_name_plural = "Data Quality"

    def __unicode__(self):
        return "Data quality for %s" % self.council

    council = models.OneToOneField(Council, primary_key=True, on_delete=models.CASCADE,)
    report = models.TextField(blank=True)
    num_stations = models.IntegerField(default=0)
    num_districts = models.IntegerField(default=0)
    num_addresses = models.IntegerField(default=0)
