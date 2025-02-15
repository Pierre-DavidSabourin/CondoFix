from datetime import datetime
from pytz import timezone
from dateutil.relativedelta import relativedelta

utcnow = timezone('utc').localize(datetime.utcnow()) # generic time
here = utcnow.astimezone(timezone('America/Montreal')).replace(tzinfo=None)
there = utcnow.astimezone(timezone('utc')).replace(tzinfo=None)

offset = relativedelta(here, there)
time_diff=offset.hours
print(offset, time_diff)

