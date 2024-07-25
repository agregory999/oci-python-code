import requests
import json

# set up the request parameters
params = {
  'api_key': '0CDF38F80D7A4B26820466C5B957B08A',
  'q': 'pizza',
  'location': 'Bedford,New Hampshire,United States'
}

# make the http GET request to Scale SERP
api_result = requests.get('https://api.scaleserp.com/search', params)

# print the JSON response from Scale SERP
print(json.dumps(api_result.json()))