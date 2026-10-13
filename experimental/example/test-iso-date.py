from datetime import datetime, timedelta

end_time = datetime.now()
start_time = end_time - timedelta(hours = 1)
print (start_time.isoformat(sep='T'))